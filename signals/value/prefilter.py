# coding=utf-8
"""规则预过滤：水贴 / 极低互动废话。"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

_URL_RE = re.compile(r"https?://|www\.|t\.co/", re.I)
_EVERGREEN_RE = re.compile(
    r"(框架|清单|步骤|复盘|原则|方法论|checklist|how to|为什么|底层|系统|"
    r"模板|笔记|教程|指南|总结|要点|takeaway)",
    re.I,
)


def _text_len(text: str) -> int:
    # 粗算：去空白后字符数
    return len(re.sub(r"\s+", "", text or ""))


def _has_link(text: str) -> bool:
    return bool(_URL_RE.search(text or ""))


def _has_images(tweet: Dict[str, Any]) -> bool:
    imgs = tweet.get("images")
    if isinstance(imgs, list) and imgs:
        return True
    return bool(tweet.get("has_media"))


def _engagement_ratio(tweet: Dict[str, Any]) -> Optional[float]:
    """Views/Likes 的近似：likes/views；缺字段则 None（不因互动过滤）。"""
    likes = tweet.get("likes") or tweet.get("favorite_count") or tweet.get("like_count")
    views = tweet.get("views") or tweet.get("view_count") or tweet.get("impressions")
    try:
        l = float(likes)
        v = float(views)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return l / v


def prefilter_tweet(tweet: Dict[str, Any]) -> Tuple[bool, str]:
    """
    返回 (keep, reason)。
    keep=False 表示丢弃。
    """
    text = str(tweet.get("text") or "").strip()
    n = _text_len(text)
    has_media = _has_images(tweet)
    has_link = _has_link(text)

    # 字数 < 50 且无链接/图片 → 纯水贴
    if n < 50 and not has_media and not has_link:
        return False, "短文无链接无图"

    ratio = _engagement_ratio(tweet)
    evergreen = bool(_EVERGREEN_RE.search(text))
    # 相对互动极低且无长青特征
    if ratio is not None and ratio < 0.002 and not evergreen and n < 120 and not has_media:
        return False, f"互动极低({ratio:.4f})且无长青特征"

    return True, "ok"
