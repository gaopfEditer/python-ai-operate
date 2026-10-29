# coding=utf-8
"""币安 Square bapi 试探（同步，无登录时可能 401）。"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib import request as urlrequest

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

_CONTENT_ID_RE = re.compile(r"/square/post/(\d+)", re.I)


def _headers() -> Dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "clienttype": "web",
        "lang": "zh-CN",
        "Referer": "https://www.binance.com/zh-CN/square",
        "Origin": "https://www.binance.com",
    }


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
                for k2 in ("list", "voList", "contents", "data"):
                    sub = node.get(k2)
                    if isinstance(sub, list):
                        items = sub
                        break
            if items:
                break
    out: List[Dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or row.get("contentTitle") or "").strip()
        body = str(row.get("content") or row.get("body") or row.get("text") or "").strip()
        cid = str(row.get("contentId") or row.get("id") or "").strip()
        href = str(row.get("shareUrl") or row.get("url") or "").strip()
        if not href and cid:
            href = f"https://www.binance.com/zh-CN/square/post/{cid}"
        if not href:
            continue
        out.append(
            {
                "href": href.split("#")[0],
                "title": title or body[:80],
                "raw": body or title,
                "content_id": cid or (_CONTENT_ID_RE.search(href).group(1) if _CONTENT_ID_RE.search(href) else ""),
                "source": "bapi",
            }
        )
    return out


_DETAIL_URL = (
    "https://www.binance.com/bapi/composite/v3/friendly/pgc/special/content/detail/{content_id}"
)


def _ms_to_published_iso(ms: Any) -> str:
    try:
        n = int(ms)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    sec = n / 1000.0 if n > 1_000_000_000_000 else float(n)
    dt = datetime.fromtimestamp(sec, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _pick_release_ms(row: Dict[str, Any]) -> Optional[int]:
    for key in ("firstReleaseTime", "latestReleaseTime", "createTime"):
        raw = row.get(key)
        if raw is None or raw == "":
            continue
        try:
            n = int(raw)
        except (TypeError, ValueError):
            continue
        if n > 0:
            return n
    return None


def fetch_content_detail(content_id: str, *, timeout_sec: float = 12.0) -> Optional[Dict[str, Any]]:
    """
    轻量拉取 Square 帖详情，优先 firstReleaseTime → latestReleaseTime → createTime。
    返回 None 表示请求失败或无 data。
    """
    cid = str(content_id or "").strip()
    if not cid.isdigit():
        return None
    url = _DETAIL_URL.format(content_id=cid)
    try:
        req = urlrequest.Request(url, headers=_headers(), method="GET")
        with urlrequest.urlopen(req, timeout=timeout_sec) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        logger.debug("content detail 失败 %s: %s", cid, e)
        return None
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    ms = _pick_release_ms(data)
    published_iso = _ms_to_published_iso(ms) if ms else ""
    return {
        "content_id": cid,
        "published_iso": published_iso,
        "first_release_ms": data.get("firstReleaseTime"),
        "latest_release_ms": data.get("latestReleaseTime"),
        "create_ms": data.get("createTime"),
        "content_type": data.get("contentType"),
        "body_text": str(data.get("bodyTextOnly") or data.get("body") or "").strip(),
    }


def apply_detail_time_to_post(
    post: Dict[str, Any],
    detail: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """将 detail 中的绝对发帖时间写入帖 dict（含 created_at）。"""
    out = dict(post)
    if not detail or not isinstance(detail, dict):
        return out
    iso = str(detail.get("published_iso") or "").strip()
    if iso:
        out["published_iso"] = iso
        out["created_at"] = iso
    body = str(detail.get("body_text") or "").strip()
    if body and not str(out.get("raw") or "").strip():
        out["raw"] = body
    return out


def fetch_trending(limit: int = 40) -> List[Dict[str, Any]]:
    for url, params in _LIST_CANDIDATES:
        try:
            q = "&".join(f"{k}={v}" for k, v in params.items())
            full = f"{url}?{q}" if q else url
            req = urlrequest.Request(full, headers=_headers(), method="GET")
            with urlrequest.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            posts = _parse_list_payload(data)
            if posts:
                logger.info("币安 bapi 成功: %s · %s 条", url.split("/")[-1], len(posts))
                return posts[:limit]
        except Exception as e:
            logger.debug("bapi 失败 %s: %s", url, e)
    return []
