# coding=utf-8
"""币安 Square 博主帖列表：Cookie + bapi HTTP，失败时静默 CDP 页内 fetch（不 Selenium 滚主页）。"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from signals.binance_square.session import (
    bapi_headers,
    default_cookie_path,
    ensure_binance_cookies,
    profile_referer,
)
from signals.binance_square.store import parse_post_time, post_content_id

logger = logging.getLogger(__name__)

ProgressCb = Optional[Callable[[str], None]]

_CONTENT_ID_RE = re.compile(r"/square/(?:post|video|article)/(\d+)", re.I)
_DETAIL_API = os.environ.get(
    "BINANCE_SQUARE_DETAIL_API",
    "https://www.binance.com/bapi/composite/v3/friendly/pgc/special/content/detail/{id}",
).strip()

# 可通过环境变量覆盖（DevTools 抓到的真实列表接口）
_PROFILE_LIST_URL = os.environ.get("BINANCE_PROFILE_LIST_URL", "").strip()
_PROFILE_LIST_METHOD = os.environ.get("BINANCE_PROFILE_LIST_METHOD", "POST").strip().upper()

_PROFILE_HTTP_CANDIDATES: list[tuple[str, str, dict[str, Any]]] = [
    (
        "POST",
        "https://www.binance.com/bapi/composite/v1/friendly/pgc/content/querySquareProfileArticleList",
        {"pageKey": "page", "sizeKey": "pageSize", "profileKey": "profileId"},
    ),
    (
        "POST",
        "https://www.binance.com/bapi/composite/v1/friendly/pgc/content/queryCreatorContentList",
        {"pageKey": "page", "sizeKey": "pageSize", "profileKey": "profileId"},
    ),
    (
        "POST",
        "https://www.binance.com/bapi/composite/v2/friendly/pgc/content/queryCreatorContentList",
        {"pageKey": "page", "sizeKey": "pageSize", "profileKey": "profileId"},
    ),
    (
        "POST",
        "https://www.binance.com/bapi/composite/v1/friendly/pgc/special/content/queryProfileContentList",
        {"pageKey": "page", "sizeKey": "pageSize", "profileKey": "profileId"},
    ),
    (
        "GET",
        "https://www.binance.com/bapi/composite/v1/friendly/pgc/content/querySquareProfileArticleList",
        {"pageKey": "page", "sizeKey": "pageSize", "profileKey": "profileId"},
    ),
]


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)


def _ms_to_iso(raw: Any) -> str:
    if raw is None or raw == "":
        return ""
    from signals.binance_square.store import _parse_iso_time

    if isinstance(raw, str) and not raw.strip().isdigit():
        dt = _parse_iso_time(raw.strip())
        if dt is not None:
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        return raw.strip()
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return str(raw).strip()
    if v > 1e12:
        v /= 1000.0
    if v <= 0:
        return ""
    return (
        datetime.fromtimestamp(v, tz=timezone.utc)
        .astimezone()
        .isoformat(timespec="seconds")
    )


_TIME_RAW_KEYS = (
    "fabricTime",
    "fabric",
    "fabricCreateTime",

    "createTime",
    "publishTime",
    "publishedAt",
    "postTime",
    "createDate",
    "gmtCreate",
    "releaseTime",
    "postCreateTime",
    "firstReleaseTime",
)


def _pick_time_raw(*nodes: dict) -> Any:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        for key in _TIME_RAW_KEYS:
            val = node.get(key)
            if val is not None and val != "":
                return val
    return None


def _extract_items(data: Any) -> List[dict]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("voList", "list", "contents", "data", "result", "rows"):
        node = data.get(key)
        if isinstance(node, list):
            return [x for x in node if isinstance(x, dict)]
        if isinstance(node, dict):
            for k2 in ("voList", "list", "contents", "data", "rows"):
                sub = node.get(k2)
                if isinstance(sub, list):
                    return [x for x in sub if isinstance(x, dict)]
    return []


def _pick_body(row: dict) -> dict:
    for key in ("contentDetail", "content", "squareContent", "body"):
        node = row.get(key)
        if isinstance(node, dict):
            return node
    return row


def _row_to_post(row: dict, *, profile_id: str, profile_name: str = "") -> Optional[dict]:
    if not isinstance(row, dict):
        return None
    body = _pick_body(row)
    cid = str(
        body.get("contentId")
        or body.get("id")
        or row.get("contentId")
        or row.get("id")
        or ""
    ).strip()
    href = str(body.get("shareUrl") or body.get("url") or row.get("shareUrl") or "").strip()
    if not href and cid.isdigit():
        href = f"https://www.binance.com/zh-CN/square/post/{cid}"
    if not cid and href:
        m = _CONTENT_ID_RE.search(href)
        if m:
            cid = m.group(1)
    if not href and not cid:
        return None
    title = str(body.get("title") or body.get("contentTitle") or row.get("title") or "").strip()
    text = str(
        body.get("content")
        or body.get("body")
        or body.get("text")
        or body.get("summary")
        or row.get("content")
        or title
    ).strip()
    time_raw = _pick_time_raw(body, row)
    published_iso = _ms_to_iso(time_raw)
    time_label = str(body.get("time") or body.get("timeLabel") or row.get("timeLabel") or "").strip()
    images: list[str] = []
    for key in ("imageList", "images", "imageUrls", "coverUrl"):
        val = body.get(key)
        if isinstance(val, str) and val.startswith("http"):
            images.append(val)
        elif isinstance(val, list):
            for x in val:
                if isinstance(x, str) and x.startswith("http"):
                    images.append(x)
                elif isinstance(x, dict) and x.get("url"):
                    images.append(str(x["url"]))
    replay = str(
        body.get("spaceLiveReplayLink")
        or body.get("replayUrl")
        or row.get("spaceLiveReplayLink")
        or ""
    ).strip()
    video = str(body.get("videoUrl") or body.get("videoLink") or "").strip()
    return {
        "href": href.split("#")[0],
        "title": title or text[:80],
        "raw": text or title,
        "content_id": cid,
        "time_label": time_label,
        "published_iso": published_iso,
        "image_urls": images[:16],
        "video_url": video,
        "replay_url": replay,
        "profile_id": profile_id,
        "profile_name": profile_name,
        "source": "profile_bapi",
    }


def _http_json(
    *,
    method: str,
    url: str,
    body: Optional[dict],
    headers: dict[str, str],
    timeout: float = 18.0,
) -> tuple[int, Any]:
    data = None
    hdr = dict(headers)
    if body is not None and method.upper() != "GET":
        data = json.dumps(body).encode("utf-8")
        hdr["Content-Type"] = "application/json"
    if method.upper() == "GET" and body:
        q = urllib.parse.urlencode({k: v for k, v in body.items() if v is not None})
        url = f"{url}?{q}" if q else url
        body = None
        data = None
    req = urllib.request.Request(url, data=data, headers=hdr, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", errors="replace")
            return e.code, json.loads(raw) if raw else {}
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def _payload_ok(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    code = str(payload.get("code") or "")
    if code and code != "000000":
        return False
    if payload.get("success") is False:
        return False
    return payload.get("data") is not None


def _fetch_page_http(
    profile_id: str,
    *,
    page: int,
    page_size: int,
    headers: dict[str, str],
) -> tuple[list[dict], Optional[str]]:
    pid = str(profile_id or "").strip()
    candidates: list[tuple[str, str, dict[str, Any]]] = list(_PROFILE_HTTP_CANDIDATES)
    if _PROFILE_LIST_URL:
        candidates.insert(
            0,
            (_PROFILE_LIST_METHOD, _PROFILE_LIST_URL, {"pageKey": "page", "sizeKey": "pageSize", "profileKey": "profileId"}),
        )
    for method, url, keys in candidates:
        body = {
            keys.get("profileKey") or "profileId": pid,
            keys.get("pageKey") or "page": page,
            keys.get("sizeKey") or "pageSize": page_size,
        }
        status, payload = _http_json(method=method, url=url, body=body, headers=headers)
        if status == 401:
            raise PermissionError("bapi 401：Cookie 失效，请保持 9223 Chrome 已登录币安")
        if not _payload_ok(payload):
            continue
        items = _extract_items(payload.get("data"))
        if items:
            return items, url
    return [], None


def fetch_content_detail(content_id: str, *, headers: Optional[dict[str, str]] = None) -> dict:
    cid = str(content_id or "").strip()
    if not cid.isdigit():
        return {}
    url = _DETAIL_API.format(id=cid)
    hdr = headers or bapi_headers(referer=f"https://www.binance.com/zh-CN/square/post/{cid}")
    _, payload = _http_json(method="GET", url=url, body=None, headers=hdr)
    if not _payload_ok(payload):
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _enrich_time_from_detail(post: dict, *, headers: dict[str, str]) -> None:
    from signals.binance_square.store import _parse_iso_time, remember_content_post_snapshot

    if _parse_iso_time(str(post.get("published_iso") or "")):
        return
    cid = post_content_id(post)
    if not cid:
        return
    detail = fetch_content_detail(cid, headers=headers)
    if not detail:
        return
    time_raw = _pick_time_raw(detail)
    if time_raw is None and isinstance(detail.get("contentDetail"), dict):
        time_raw = _pick_time_raw(detail["contentDetail"])
    iso = _ms_to_iso(time_raw) if time_raw is not None else ""
    if iso and _parse_iso_time(iso):
        post["published_iso"] = iso
        remember_content_post_snapshot(post)


def _enrich_replay_from_detail(post: dict, *, headers: dict[str, str]) -> None:
    if str(post.get("replay_url") or "").strip():
        return
    cid = post_content_id(post)
    if not cid:
        return
    detail = fetch_content_detail(cid, headers=headers)
    if not detail:
        return
    replay = str(detail.get("spaceLiveReplayLink") or detail.get("replayUrl") or "").strip()
    if replay:
        post["replay_url"] = replay
    if not post.get("video_url"):
        vo = detail.get("videoVO") if isinstance(detail.get("videoVO"), dict) else {}
        v = str(vo.get("videoUrl") or detail.get("videoUrl") or "").strip()
        if v:
            post["video_url"] = v


def _fetch_via_cdp_inpage(
    profile_id: str,
    *,
    max_items: int,
    page_size: int,
    progress: ProgressCb,
) -> List[dict]:
    from allnews_mornitor.cdp_browser import BackgroundTarget, _CdpClient, _browser_ws_url, _http_json

    pid = str(profile_id or "").strip()
    profile_url = profile_referer(pid)
    custom_url = json.dumps(_PROFILE_LIST_URL or "")

    all_rows: list[dict] = []
    working_url: Optional[str] = None
    page = 1
    max_pages = max(3, (max_items + page_size - 1) // page_size + 2)

    try:
        _http_json("/json/version")
    except Exception as e:
        raise RuntimeError(f"CDP 不可用（页内 bapi）: {e}") from e

    client = _CdpClient(_browser_ws_url())
    bg = BackgroundTarget.create(client, profile_url)
    try:
        bg.silent_navigate(profile_url)
        time.sleep(4.0)
        _log(progress, f"  bapi 页内探测 @{pid}（后台 tab，不滚主页）…")
        custom_url = json.dumps(_PROFILE_LIST_URL or "")
        while len(all_rows) < max_items and page <= max_pages:
            script = f"""
const profileId = {json.dumps(pid)};
const page = {page};
const pageSize = {page_size};
const customUrl = {custom_url};
const tries = [
  ['POST', 'https://www.binance.com/bapi/composite/v1/friendly/pgc/content/querySquareProfileArticleList', {{ profileId, page, pageSize }}],
  ['POST', 'https://www.binance.com/bapi/composite/v1/friendly/pgc/content/queryCreatorContentList', {{ profileId, page, pageSize }}],
  ['POST', 'https://www.binance.com/bapi/composite/v2/friendly/pgc/content/queryCreatorContentList', {{ profileId, page, pageSize }}],
  ['POST', 'https://www.binance.com/bapi/composite/v1/friendly/pgc/special/content/queryProfileContentList', {{ profileId, page, pageSize }}],
];
if (customUrl) tries.unshift(['POST', customUrl, {{ profileId, page, pageSize }}]);
let hit = null;
for (const [method, url, body] of tries) {{
  try {{
    const resp = await fetch(url, {{
      method,
      credentials: 'include',
      headers: {{ clienttype: 'web', lang: 'zh-CN', Accept: 'application/json', 'Content-Type': 'application/json' }},
      body: JSON.stringify(body),
    }});
    const text = await resp.text();
    const data = JSON.parse(text);
    if (data && data.code === '000000' && data.data != null) {{
      hit = {{ url, payload: data }};
      break;
    }}
  }} catch (e) {{}}
}}
return hit;
"""
            result = bg.eval_js(script)
            if not isinstance(result, dict) or not result.get("payload"):
                break
            payload = result.get("payload") or {}
            if working_url is None:
                working_url = str(result.get("url") or "")
                _log(progress, f"  页内 bapi 命中: …/{working_url.split('/')[-1][:48]}")
            items = _extract_items(payload.get("data") if isinstance(payload, dict) else payload)
            if not items:
                break
            all_rows.extend(items)
            if len(items) < page_size:
                break
            page += 1
            time.sleep(0.35)
    finally:
        try:
            bg.close()
        except Exception:
            pass
        try:
            client.close()
        except Exception:
            pass
    return all_rows[: max_items * 2]


def fetch_profile_posts(
    profile_id: str,
    *,
    profile_name: str = "",
    max_items: int = 40,
    page_size: int = 20,
    known_ids: Optional[Set[str]] = None,
    stop_before: Optional[datetime] = None,
    enrich_replay: bool = True,
    progress: ProgressCb = None,
    allow_cdp_inpage: bool = True,
) -> tuple[List[Dict[str, Any]], str]:
    """
    返回 (posts, route)，route 为 profile_bapi_http | profile_bapi_inpage | profile_bapi_empty。
    """
    pid = str(profile_id or "").strip()
    if not pid:
        return [], "profile_bapi_empty"

    ensure_binance_cookies(on_log=progress)
    headers = bapi_headers(referer=profile_referer(pid))
    if not headers.get("Cookie"):
        _log(progress, ">>> 警告：无 binance_cookies.txt，bapi 可能失败")

    known = known_ids or set()
    collected: list[dict] = []
    route = "profile_bapi_http"
    page = 1
    max_pages = max(5, (max_items + page_size - 1) // page_size + 3)
    hit_url: Optional[str] = None

    while len(collected) < max_items and page <= max_pages:
        try:
            rows, hit_url = _fetch_page_http(pid, page=page, page_size=page_size, headers=headers)
        except PermissionError as e:
            _log(progress, f"  {e}")
            rows, hit_url = [], None
            break
        if not rows:
            if page == 1:
                break
            break
        if page == 1 and hit_url:
            _log(progress, f"  bapi HTTP 命中 …/{hit_url.split('/')[-1][:56]}")
        stop_paging = False
        for row in rows:
            post = _row_to_post(row, profile_id=pid, profile_name=profile_name)
            if not post:
                continue
            cid = post_content_id(post)
            if cid and cid in known:
                continue
            dt = parse_post_time(post)
            if stop_before and dt and dt < stop_before:
                stop_paging = True
                continue
            collected.append(post)
            if len(collected) >= max_items:
                stop_paging = True
                break
        if stop_paging or len(rows) < page_size:
            break
        page += 1
        time.sleep(0.2)

    if not collected and allow_cdp_inpage:
        route = "profile_bapi_inpage"
        try:
            raw_rows = _fetch_via_cdp_inpage(
                pid, max_items=max_items, page_size=page_size, progress=progress
            )
            for row in raw_rows:
                post = _row_to_post(row, profile_id=pid, profile_name=profile_name)
                if not post:
                    continue
                cid = post_content_id(post)
                if cid and cid in known:
                    continue
                dt = parse_post_time(post)
                if stop_before and dt and dt < stop_before:
                    continue
                collected.append(post)
                if len(collected) >= max_items:
                    break
        except Exception as e:
            _log(progress, f"  页内 bapi 失败: {e}")
            route = "profile_bapi_empty"

    for p in collected:
        if not parse_post_time(p):
            try:
                _enrich_time_from_detail(p, headers=headers)
            except Exception:
                pass

    if enrich_replay:
        for p in collected:
            if str(p.get("replay_url") or "").strip():
                continue
            try:
                _enrich_replay_from_detail(p, headers=headers)
            except Exception:
                pass

    return collected[:max_items], route if collected else "profile_bapi_empty"
