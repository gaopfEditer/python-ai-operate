# coding=utf-8
"""币安 Square bapi：Cookie/指纹头 + REST（主页、博主帖、详情）。"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from urllib import request as urlrequest

from signals.binance_square.session import load_binance_session, session_ready

logger = logging.getLogger(__name__)

_LIST_CANDIDATES = [
    (
        "https://www.binance.com/bapi/composite/v1/friendly/pgc/content/home/squareList",
        {"page": 1, "rows": 40},
    ),
    (
        "https://www.binance.com/bapi/composite/v1/public/pgc/content/home/squareList",
        {"page": 1, "rows": 40},
    ),
    (
        "https://www.binance.com/bapi/composite/v1/friendly/pgc/content/square/list",
        {"page": 1, "pageSize": 40, "contentType": "ALL"},
    ),
]

_USER_CLIENT_URL = "https://www.binance.com/bapi/composite/v3/friendly/pgc/user/client"
_PROFILE_POSTS_URL = (
    "https://www.binance.com/bapi/composite/v2/friendly/pgc/content/queryUserProfilePageContentsWithFilter"
)
_DETAIL_URL_TMPL = (
    "https://www.binance.com/bapi/composite/v3/friendly/pgc/special/content/detail/{content_id}"
)

_CONTENT_ID_RE = re.compile(r"/square/post/(\d+)", re.I)
_LOCALE = "zh-CN"


def _base_headers(*, referer: str = "") -> Dict[str, str]:
    h = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "clienttype": "web",
        "lang": "zh-CN",
        "Referer": referer or f"https://www.binance.com/{_LOCALE}/square",
        "Origin": "https://www.binance.com",
    }
    sess = load_binance_session()
    if sess:
        extra = sess.get("headers") if isinstance(sess.get("headers"), dict) else {}
        for k, v in extra.items():
            if str(v).strip():
                h[str(k)] = str(v).strip()
        ck = str(sess.get("cookie_header") or "").strip()
        if ck:
            h["Cookie"] = ck
    return h


def _http_json(
    url: str,
    *,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    referer: str = "",
    timeout: float = 18,
) -> Any:
    full = url
    if params:
        q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        full = f"{url}?{q}" if q else url
    headers = _base_headers(referer=referer)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urlrequest.Request(full, data=data, headers=headers, method=method.upper())
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"HTTP {e.code}: {err}") from e


def _ms_to_iso(ms: Any) -> str:
    try:
        n = int(ms)
    except (TypeError, ValueError):
        return ""
    if n < 10_000_000_000:
        n *= 1000
    dt = datetime.fromtimestamp(n / 1000.0, tz=timezone.utc)
    return dt.astimezone().isoformat(timespec="seconds")


def _pick_release_iso(row: Dict[str, Any]) -> str:
    for key in ("firstReleaseTime", "latestReleaseTime", "createTime", "date", "publishTime"):
        if key in row and row.get(key) not in (None, "", 0):
            iso = _ms_to_iso(row.get(key))
            if iso:
                return iso
    return ""


def _body_text_only(row: Dict[str, Any]) -> str:
    for key in ("bodyTextOnly", "content", "body", "text", "title", "contentTitle"):
        val = str(row.get(key) or "").strip()
        if val and not val.startswith("{"):
            return val
    body = row.get("body")
    if isinstance(body, str) and body.strip().startswith("{"):
        try:
            blob = json.loads(body)
        except Exception:
            return body[:8000]
        return _extract_layout_text(blob)
    if isinstance(body, dict):
        return _extract_layout_text(body)
    return ""


def _extract_layout_text(node: Any) -> str:
    parts: List[str] = []
    if isinstance(node, dict):
        for k in ("text", "bodyTextOnly", "content", "title"):
            if isinstance(node.get(k), str) and node[k].strip():
                parts.append(node[k].strip())
        for v in node.values():
            sub = _extract_layout_text(v)
            if sub:
                parts.append(sub)
    elif isinstance(node, list):
        for x in node:
            sub = _extract_layout_text(x)
            if sub:
                parts.append(sub)
    text = "\n".join(dict.fromkeys(p for p in parts if p))
    return text[:8000]


def _image_urls(row: Dict[str, Any]) -> List[str]:
    urls: List[str] = []
    for key in ("imageList", "images", "imageUrls", "coverUrl"):
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            urls.append(val.strip())
        elif isinstance(val, list):
            for x in val:
                if isinstance(x, str) and x.strip():
                    urls.append(x.strip())
                elif isinstance(x, dict):
                    u = str(x.get("url") or x.get("imageUrl") or "").strip()
                    if u:
                        urls.append(u)
    return list(dict.fromkeys(urls))[:24]


def row_to_post(
    row: Dict[str, Any],
    *,
    profile_slug: str = "",
    profile_name: str = "",
) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None
    cid = str(row.get("contentId") or row.get("id") or "").strip()
    href = str(row.get("shareUrl") or row.get("webLink") or row.get("url") or "").strip()
    if not href and cid:
        href = f"https://www.binance.com/{_LOCALE}/square/post/{cid}"
    if not cid and href:
        m = _CONTENT_ID_RE.search(href)
        if m:
            cid = m.group(1)
    if not cid and not href:
        return None
    body = _body_text_only(row)
    published = _pick_release_iso(row)
    title = str(row.get("title") or row.get("contentTitle") or body[:80] or cid).strip()
    from signals.publish_time import normalize_square_post_times

    return normalize_square_post_times(
        {
            "href": href.split("#")[0],
            "title": title,
            "raw": body or title,
            "content_id": cid,
            "published_iso": published,
            "created_at": published,
            "time_label": "",
            "image_urls": _image_urls(row),
            "video_url": str(row.get("videoUrl") or row.get("video_url") or "").strip(),
            "profile_id": profile_slug,
            "profile_name": profile_name or profile_slug,
            "source": "bapi",
            "is_pinned": bool(row.get("isPin") or row.get("pinned")),
        }
    )


def _parse_list_payload(data: Any) -> List[Dict[str, Any]]:
    items: List[Any] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("data", "list", "voList", "contents", "result"):
            node = data.get(key)
            if isinstance(node, list):
                items = node
                break
            if isinstance(node, dict):
                for k2 in ("list", "voList", "contents", "data", "rows"):
                    sub = node.get(k2)
                    if isinstance(sub, list):
                        items = sub
                        break
            if items:
                break
    out: List[Dict[str, Any]] = []
    for row in items:
        p = row_to_post(row if isinstance(row, dict) else {})
        if p:
            out.append(p)
    return out


def fetch_trending(limit: int = 40) -> List[Dict[str, Any]]:
    for url, params in _LIST_CANDIDATES:
        try:
            data = _http_json(url, params=params)
            posts = _parse_list_payload(data)
            if posts:
                logger.info("币安 bapi 成功: %s · %s 条", url.split("/")[-1], len(posts))
                return posts[:limit]
        except Exception as e:
            logger.debug("bapi 失败 %s: %s", url, e)
    return []


def resolve_square_uid(profile_slug: str) -> str:
    slug = str(profile_slug or "").strip().strip("/")
    if not slug:
        raise ValueError("缺少 profile slug")
    referer = f"https://www.binance.com/{_LOCALE}/square/profile/{slug}"
    data = _http_json(
        _USER_CLIENT_URL,
        method="POST",
        body={"username": slug, "getFollowCount": False},
        referer=referer,
    )
    node = data.get("data") if isinstance(data, dict) else {}
    if isinstance(node, dict):
        uid = str(node.get("squareUid") or node.get("squareUserId") or node.get("userId") or "").strip()
        if uid:
            return uid
    raise RuntimeError(f"无法解析 Square UID: {slug}")


def fetch_profile_posts_page(
    square_uid: str,
    *,
    time_offset: int = 0,
    filter_type: str = "all",
    profile_slug: str = "",
) -> Tuple[List[Dict[str, Any]], int]:
    referer = f"https://www.binance.com/{_LOCALE}/square/profile/{profile_slug or square_uid}"
    params = {
        "squareUid": square_uid,
        "timeOffset": int(time_offset or 0),
        "filterType": filter_type or "all",
    }
    data = _http_json(_PROFILE_POSTS_URL, params=params, referer=referer)
    rows = _parse_list_payload(data)
    next_offset = 0
    if isinstance(data, dict):
        d = data.get("data")
        if isinstance(d, dict):
            next_offset = int(d.get("timeOffset") or d.get("nextTimeOffset") or 0)
        elif isinstance(d, list) and rows:
            last = rows[-1]
            iso = str(last.get("published_iso") or "")
            try:
                next_offset = int(datetime.fromisoformat(iso).timestamp() * 1000)
            except Exception:
                next_offset = 0
    return rows, next_offset


def fetch_profile_posts(
    profile_slug: str,
    *,
    max_items: int = 40,
    since: Optional[datetime] = None,
    profile_name: str = "",
    progress: Optional[Callable[[str], None]] = None,
    realtime_incremental: bool = False,
    is_known: Optional[Callable[[str], bool]] = None,
) -> List[Dict[str, Any]]:
    slug = str(profile_slug or "").strip()
    uid = resolve_square_uid(slug)
    since_cmp = None
    if since is not None:
        since_cmp = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
    merged: List[Dict[str, Any]] = []
    seen_ids: set = set()
    offset = 0
    stale_pages = 0
    for page_i in range(40):
        rows, next_off = fetch_profile_posts_page(uid, time_offset=offset, profile_slug=slug)
        if not rows:
            break
        from signals.incremental import filter_newest_until_known, square_id_from_post

        stop_page = False
        if realtime_incremental and is_known:
            rows, stop_page = filter_newest_until_known(
                rows,
                id_fn=square_id_from_post,
                is_known=is_known,
                enabled=True,
            )
        new_in_page = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            p = dict(row)
            if slug:
                p.setdefault("profile_id", slug)
            if profile_name:
                p.setdefault("profile_name", profile_name)
            p.setdefault("source", "bapi_profile")
            cid = str(p.get("content_id") or "")
            if cid and cid in seen_ids:
                continue
            if cid:
                seen_ids.add(cid)
            dt_iso = str(p.get("published_iso") or "")
            dt = None
            if dt_iso:
                try:
                    dt = datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                except Exception:
                    dt = None
            if since_cmp and dt and dt < since_cmp and not p.get("is_pinned"):
                stale_pages += 1
                continue
            merged.append(p)
            new_in_page += 1
        if progress:
            progress(f"  bapi @{slug} 页 {page_i + 1} · 累计 {len(merged)}")
        if len(merged) >= max_items:
            break
        if stop_page:
            if progress:
                progress(f"  bapi @{slug} 命中已存帖，停止翻页")
            break
        if new_in_page == 0:
            stale_pages += 1
        if stale_pages >= 2:
            break
        if not next_off or next_off == offset:
            break
        offset = next_off
        time.sleep(0.25)
    return merged[: max(max_items, 1)]


def fetch_content_detail(content_id: str) -> Dict[str, Any]:
    cid = str(content_id or "").strip()
    if not cid.isdigit():
        return {}
    url = _DETAIL_URL_TMPL.format(content_id=cid)
    referer = f"https://www.binance.com/{_LOCALE}/square/post/{cid}"
    data = _http_json(url, referer=referer)
    node = data.get("data") if isinstance(data, dict) else {}
    if not isinstance(node, dict):
        return {}
    post = row_to_post(node) or {}
    post["content_id"] = cid
    post["href"] = f"https://www.binance.com/{_LOCALE}/square/post/{cid}"
    return post


def api_available() -> bool:
    return session_ready() or bool(fetch_trending(limit=1))
