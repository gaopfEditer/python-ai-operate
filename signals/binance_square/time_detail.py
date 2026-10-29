# coding=utf-8
"""通过 bapi content/detail 补全 Square 发帖绝对时间。"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from signals.binance_square.bapi import apply_detail_time_to_post, fetch_content_detail
from signals.binance_square.store import (
    _parse_iso_time,
    post_content_id,
    remember_content_post_snapshot,
)

ProgressCb = Optional[Callable[[str], None]]

_LIVE_HOURS_RE = re.compile(r"[·•]\s*(\d+)\s*小时")


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)


def _post_needs_detail_time(post: Dict[str, Any]) -> bool:
    if not isinstance(post, dict):
        return False
    cid = post_content_id(post)
    if not cid:
        return False
    if str(post.get("published_iso") or "").strip():
        if _parse_iso_time(str(post.get("published_iso") or "")) is not None:
            return False
    if str(post.get("created_at") or "").strip():
        if _parse_iso_time(str(post.get("created_at") or "")) is not None:
            return False
    return True


def _live_hours_fallback(post: Dict[str, Any]) -> None:
    """直播帖正文「· N小时」兜底（无 detail 时）。"""
    if str(post.get("published_iso") or "").strip():
        return
    blob = " ".join(
        str(post.get(k) or "")
        for k in ("raw", "title", "time_label")
    )
    m = _LIVE_HOURS_RE.search(blob)
    if not m:
        return
    try:
        hours = int(m.group(1))
    except ValueError:
        return
    from datetime import datetime, timedelta, timezone

    dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    iso = dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    post["published_iso"] = iso
    post["created_at"] = iso


def enrich_posts_publish_time_from_detail(
    posts: List[Dict[str, Any]],
    *,
    limit: int = 12,
    workers: int = 3,
    progress: ProgressCb = None,
) -> List[Dict[str, Any]]:
    """
    对缺 published_iso/created_at 的帖请求 detail API；失败保留相对文案解析。
    """
    rows = [dict(p) for p in (posts or []) if isinstance(p, dict)]
    need: List[Dict[str, Any]] = [p for p in rows if _post_needs_detail_time(p)]
    if not need:
        for p in rows:
            _live_hours_fallback(p)
        return rows

    cap = max(1, min(int(limit or 12), len(need)))
    targets = need[:cap]
    _log(progress, f"detail API 补发帖时间 {len(targets)} 条…")

    detail_by_cid: Dict[str, Dict[str, Any]] = {}
    w = max(1, min(int(workers or 3), 4))

    def _fetch_one(p: Dict[str, Any]) -> tuple[str, Optional[Dict[str, Any]]]:
        cid = post_content_id(p) or ""
        if not cid:
            return "", None
        time.sleep(0.12)
        return cid, fetch_content_detail(cid)

    with ThreadPoolExecutor(max_workers=w) as pool:
        futs = [pool.submit(_fetch_one, p) for p in targets]
        for fut in as_completed(futs):
            cid, detail = fut.result()
            if cid and detail:
                detail_by_cid[cid] = detail

    out: List[Dict[str, Any]] = []
    enriched_n = 0
    for p in rows:
        cid = post_content_id(p)
        if cid and cid in detail_by_cid:
            p = apply_detail_time_to_post(p, detail_by_cid[cid])
            if str(p.get("published_iso") or "").strip():
                enriched_n += 1
        _live_hours_fallback(p)
        remember_content_post_snapshot(p)
        out.append(p)

    if enriched_n:
        _log(progress, f"detail 补时成功 {enriched_n}/{len(targets)} 条")
    return out
