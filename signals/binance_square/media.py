# coding=utf-8
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from signals.binance_square.profile_js import DETAIL_MEDIA_EXTRACT_JS

ProgressCb = Optional[Callable[[str], None]]


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)


def _needs_detail_media(p: Dict[str, Any]) -> bool:
    imgs = p.get("image_urls") or []
    vid = str(p.get("video_url") or "").strip()
    if isinstance(imgs, list) and imgs:
        return False
    if vid:
        return False
    href = str(p.get("href") or "").strip()
    return bool(href) and "/square/" in href


def enrich_posts_media_from_detail(
    driver,
    posts: List[Dict[str, Any]],
    *,
    limit: int = 12,
    progress: ProgressCb = None,
) -> List[Dict[str, Any]]:
    """列表卡片无媒体时，打开详情页补抓配图/视频 URL。"""
    want = [p for p in posts if isinstance(p, dict) and _needs_detail_media(p)]
    if not want:
        return posts
    cap = max(0, min(int(limit or 0), len(want)))
    if cap <= 0:
        return posts
    out: List[Dict[str, Any]] = []
    by_href = {str(p.get("href") or ""): dict(p) for p in posts if isinstance(p, dict)}
    done = 0
    for p in want[:cap]:
        href = str(p.get("href") or "").strip()
        if not href:
            continue
        done += 1
        _log(progress, f"详情补媒体 [{done}/{cap}] …")
        try:
            driver.get(href)
        except Exception as e:
            _log(progress, f"  打开失败: {e}")
            continue
        time.sleep(1.8)
        try:
            pack = driver.execute_script(DETAIL_MEDIA_EXTRACT_JS) or {}
        except Exception as e:
            _log(progress, f"  解析失败: {e}")
            continue
        if not isinstance(pack, dict):
            continue
        row = by_href.get(href) or dict(p)
        imgs = pack.get("image_urls") if isinstance(pack.get("image_urls"), list) else []
        row["image_urls"] = list(dict.fromkeys([str(x) for x in imgs if str(x).strip()]))[:20]
        v = str(pack.get("video_url") or "").strip()
        if v:
            row["video_url"] = v
        by_href[href] = row
    for p in posts:
        if not isinstance(p, dict):
            continue
        h = str(p.get("href") or "")
        out.append(by_href.get(h) or dict(p))
    return out
