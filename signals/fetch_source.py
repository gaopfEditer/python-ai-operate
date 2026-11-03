# coding=utf-8
"""抓取路径标签：cookie+api（HTTP GraphQL/bapi）与 cdp（DOM 回退）。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

FETCH_COOKIE_API = "cookie+api"
FETCH_CDP = "cdp"
_VALID = frozenset({FETCH_COOKIE_API, FETCH_CDP})

_LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "signals_fetch_routes.jsonl"

_SECRET_RE = re.compile(
    r"(auth_token|ct0|csrftoken|cookie|bearer|token|password|secret)[\"']?\s*[:=]\s*[\"']?[\w\-./%+]{8,}",
    re.I,
)


def normalize_fetch_source(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in ("cookie+api", "cookie_api", "bapi", "x_api", "api", "http", "graphql"):
        return FETCH_COOKIE_API
    if raw in ("cdp", "dom", "scroll", "profile_cdp"):
        return FETCH_CDP
    if raw == FETCH_COOKIE_API or raw == FETCH_CDP:
        return raw
    return ""


def square_post_source_to_fetch_source(source: Any) -> str:
    s = str(source or "").strip().lower()
    if s in ("profile_cdp", "cdp"):
        return FETCH_CDP
    if s in ("bapi", "bapi_profile", "bapi_trending"):
        return FETCH_COOKIE_API
    return ""


def x_crawl_route_to_fetch_source(route: Any) -> str:
    r = str(route or "").strip().lower()
    if r in ("x_api", "cookie+api", "api"):
        return FETCH_COOKIE_API
    if r in ("cdp", "x_cdp"):
        return FETCH_CDP
    return ""


def stamp_items(items: List[Dict[str, Any]], fetch_source: str) -> List[Dict[str, Any]]:
    fs = normalize_fetch_source(fetch_source)
    if not fs:
        return items
    for it in items:
        if isinstance(it, dict):
            it["fetch_source"] = fs
    return items


def fetch_source_for_item(item: Dict[str, Any], crawl_default: str = "") -> str:
    if not isinstance(item, dict):
        return normalize_fetch_source(crawl_default)
    direct = normalize_fetch_source(item.get("fetch_source"))
    if direct:
        return direct
    sq = square_post_source_to_fetch_source(item.get("source"))
    if sq:
        return sq
    return normalize_fetch_source(crawl_default)


def crawl_default_fetch_source(crawled: Dict[str, Any]) -> str:
    if not isinstance(crawled, dict):
        return ""
    fr = normalize_fetch_source(crawled.get("fetch_route"))
    if fr:
        return fr
    return x_crawl_route_to_fetch_source(crawled.get("route"))


def _sanitize_reason(text: Any, *, max_len: int = 240) -> str:
    s = str(text or "").strip()
    if not s:
        return ""
    s = _SECRET_RE.sub(r"\1=<redacted>", s)
    s = re.sub(r"(auth_token|ct0|csrftoken)=[^;\s]+", r"\1=<redacted>", s, flags=re.I)
    return s[:max_len]


def append_fetch_route_log(record: Dict[str, Any]) -> Path:
    """追加一行 JSON（无密钥）；供联调与周期任务排查 cookie+api vs cdp。"""
    row = dict(record)
    row.setdefault("ts", datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"))
    if "reason" in row:
        row["reason"] = _sanitize_reason(row.get("reason"))
    if isinstance(row.get("cookie_api"), dict):
        ca = dict(row["cookie_api"])
        if "reason" in ca:
            ca["reason"] = _sanitize_reason(ca.get("reason"))
        row["cookie_api"] = ca
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return _LOG_PATH


def log_x_list_crawl(
    crawled: Dict[str, Any],
    *,
    list_id: str = "",
    realtime: bool = False,
    api_attempt: Optional[Dict[str, Any]] = None,
) -> None:
    final_fs = crawl_default_fetch_source(crawled) or FETCH_CDP
    attempted: List[str] = [FETCH_COOKIE_API]
    if final_fs == FETCH_CDP or (api_attempt and not api_attempt.get("ok")):
        attempted.append(FETCH_CDP)
    ca: Dict[str, Any] = {"attempted": True, "ok": final_fs == FETCH_COOKIE_API}
    if api_attempt:
        ca["ok"] = bool(api_attempt.get("ok"))
        if api_attempt.get("reason"):
            ca["reason"] = api_attempt.get("reason")
    elif final_fs == FETCH_CDP:
        ca["ok"] = False
        ca["reason"] = _sanitize_reason(crawled.get("error") or "回退 CDP")
    append_fetch_route_log(
        {
            "platform": "x_list",
            "list_id": str(list_id or crawled.get("list_id") or ""),
            "realtime": bool(realtime),
            "attempted_routes": attempted,
            "cookie_api": ca,
            "final_fetch_source": final_fs,
            "sample_count": int(crawled.get("count") or len(crawled.get("items") or [])),
            "route": str(crawled.get("route") or ""),
        }
    )


def log_x_user_crawl(
    crawled: Dict[str, Any],
    *,
    handle: str = "",
    realtime: bool = False,
    api_attempt: Optional[Dict[str, Any]] = None,
) -> None:
    final_fs = crawl_default_fetch_source(crawled) or FETCH_CDP
    attempted: List[str] = [FETCH_COOKIE_API]
    if final_fs == FETCH_CDP or (api_attempt and not api_attempt.get("ok")):
        attempted.append(FETCH_CDP)
    ca: Dict[str, Any] = {"attempted": True, "ok": final_fs == FETCH_COOKIE_API}
    if api_attempt:
        ca["ok"] = bool(api_attempt.get("ok"))
        if api_attempt.get("reason"):
            ca["reason"] = api_attempt.get("reason")
    elif final_fs == FETCH_CDP:
        ca["ok"] = False
        ca["reason"] = _sanitize_reason(crawled.get("error") or "回退 CDP")
    append_fetch_route_log(
        {
            "platform": "x_user",
            "handle": str(handle or crawled.get("handle") or "").lstrip("@"),
            "realtime": bool(realtime),
            "attempted_routes": attempted,
            "cookie_api": ca,
            "final_fetch_source": final_fs,
            "sample_count": int(crawled.get("count") or len(crawled.get("items") or [])),
            "route": str(crawled.get("route") or ""),
        }
    )


def log_binance_square_crawl(
    result: Dict[str, Any],
    *,
    realtime: bool = False,
) -> None:
    routes = [str(x) for x in (result.get("routes") or []) if x]
    api_routes = [r for r in routes if r.startswith("bapi")]
    used_api = bool(api_routes)
    used_cdp = "profile_cdp" in routes
    if used_api and not used_cdp:
        final_fs = FETCH_COOKIE_API
    elif used_cdp and not used_api:
        final_fs = FETCH_CDP
    elif used_api:
        final_fs = FETCH_COOKIE_API
    else:
        final_fs = ""
    attempted: List[str] = []
    if used_api or result.get("try_bapi") is not False:
        attempted.append(FETCH_COOKIE_API)
    if used_cdp or (not used_api and routes):
        attempted.append(FETCH_CDP)
    if not attempted:
        attempted = [FETCH_COOKIE_API, FETCH_CDP]
    ca_ok = used_api
    ca_reason = ""
    if not ca_ok:
        ca_reason = _sanitize_reason(result.get("error") or "bapi 无数据或未启用")
    posts = result.get("posts") or []
    sample = len(posts)
    by_fs: Dict[str, int] = {}
    for p in posts:
        if not isinstance(p, dict):
            continue
        fs = fetch_source_for_item(p, final_fs)
        if fs:
            by_fs[fs] = by_fs.get(fs, 0) + 1
    append_fetch_route_log(
        {
            "platform": "binance_square",
            "realtime": bool(realtime),
            "attempted_routes": attempted,
            "routes": routes,
            "cookie_api": {"attempted": True, "ok": ca_ok, "reason": ca_reason or None},
            "final_fetch_source": final_fs or (FETCH_CDP if used_cdp else FETCH_COOKIE_API),
            "sample_count": sample,
            "items_by_fetch_source": by_fs,
            "new_count": int(result.get("new_count") or 0),
        }
    )
