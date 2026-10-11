# coding=utf-8
"""币安 Square bapi 试探（同步，无登录时可能 401）。"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List
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
