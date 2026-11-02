# coding=utf-8
"""Square 发帖时间：detail API 补全 firstReleaseTime。"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from signals.binance_square.bapi import fetch_content_detail

ProgressCb = Optional[Callable[[str], None]]
_LOCK = threading.Lock()
_LAST_DETAIL_AT = 0.0
_MIN_INTERVAL = 0.12


def _throttle() -> None:
    global _LAST_DETAIL_AT
    with _LOCK:
        now = time.time()
        wait = _MIN_INTERVAL - (now - _LAST_DETAIL_AT)
        if wait > 0:
            time.sleep(wait)
        _LAST_DETAIL_AT = time.time()


def post_needs_time_detail(post: Dict[str, Any]) -> bool:
    if not str(post.get("content_id") or "").strip().isdigit():
        return False
    if str(post.get("published_iso") or "").strip():
        return False
    if str(post.get("created_at") or "").strip() and "T" in str(post.get("created_at")):
        return False
    return True


def enrich_posts_time_from_detail(
    posts: List[Dict[str, Any]],
    *,
    limit: int = 12,
    progress: ProgressCb = None,
) -> List[Dict[str, Any]]:
    need = [p for p in posts if isinstance(p, dict) and post_needs_time_detail(p)]
    if not need:
        return posts
    cap = max(1, min(int(limit or 12), len(need)))
    targets = need[:cap]
    if progress:
        progress(f"Square detail 补时间 {len(targets)} 条…")

    patches: Dict[str, Dict[str, Any]] = {}

    def _one(p: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        cid = str(p.get("content_id") or "")
        _throttle()
        detail = fetch_content_detail(cid)
        return cid, detail

    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = [pool.submit(_one, p) for p in targets]
        for fut in as_completed(futs):
            try:
                cid, detail = fut.result()
            except Exception:
                continue
            if detail.get("published_iso"):
                patches[cid] = detail

    out: List[Dict[str, Any]] = []
    for p in posts:
        if not isinstance(p, dict):
            continue
        cid = str(p.get("content_id") or "")
        patch = patches.get(cid)
        if patch:
            merged = dict(p)
            for k in ("published_iso", "created_at", "time_label", "raw", "title", "image_urls", "video_url"):
                if patch.get(k):
                    merged[k] = patch[k]
            out.append(merged)
        else:
            out.append(p)
    return out
