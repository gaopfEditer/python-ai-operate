# coding=utf-8
"""卡片/入库统一使用发布时间（非相对文案、非抓取时刻）。"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

_RELATIVE_RE = re.compile(
    r"(\d+\s*(?:分钟|小时|天)(?:前)?|刚刚|昨天|"
    r"\d+\s*(?:minutes?|hours?|days?)\s*ago)",
    re.I,
)


def _parse_iso(raw: str) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text or _RELATIVE_RE.search(text):
        return None
    try:
        s = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def tweet_item_publish_iso(item: Dict[str, Any]) -> str:
    """X 推文：GraphQL legacy.created_at → ISO。"""
    from signals.x_api import twitter_created_to_iso

    for key in ("created_at", "published_iso"):
        raw = str(item.get(key) or "").strip()
        if not raw:
            continue
        iso = _parse_iso(raw)
        if iso:
            return iso.astimezone().isoformat(timespec="seconds")
        conv = twitter_created_to_iso(raw)
        if conv and _parse_iso(conv):
            return conv
    return ""


def normalize_tweet_item_times(item: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(item)
    iso = tweet_item_publish_iso(out)
    if iso:
        out["created_at"] = iso
        out["published_iso"] = iso
        out.pop("time_label", None)
    return out


def square_post_publish_iso(post: Dict[str, Any]) -> str:
    for key in ("published_iso", "created_at", "firstReleaseTime"):
        raw = post.get(key)
        if isinstance(raw, (int, float)):
            from signals.binance_square.bapi import _ms_to_iso

            iso = _ms_to_iso(raw)
            if iso:
                return iso
        iso = _parse_iso(str(raw or ""))
        if iso:
            return iso.astimezone().isoformat(timespec="seconds")
    return ""


def normalize_square_post_times(post: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(post)
    iso = square_post_publish_iso(out)
    if iso:
        out["published_iso"] = iso
        out["created_at"] = iso
        if str(out.get("time_label") or "").strip() and _RELATIVE_RE.search(str(out["time_label"])):
            out["time_label"] = ""
    return out
