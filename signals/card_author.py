# coding=utf-8
"""卡片作者 handle 归一：author / user_handle / 推文 URL。"""
from __future__ import annotations

from typing import Any, Dict

from signals.store import parse_user_handle
from signals.tweet_author_cache import lookup_tweet_author

_UNMAPPED_LABELS = frozenset({"未映射", "未映射推特源", ""})


def stored_author_handle(card: Dict[str, Any]) -> str:
    """仅看卡片已入库字段（不含 tweet 作者缓存）。"""
    h = parse_user_handle(str(card.get("author") or ""))
    if not h:
        raw = str(card.get("user_handle") or "").strip().lstrip("@")
        if raw:
            h = parse_user_handle(raw) or raw.lower()
    if not h:
        h = parse_user_handle(str(card.get("url") or ""))
    lid = str(card.get("list_id") or "")
    if not h and lid.startswith("user:"):
        h = lid.split(":", 1)[-1].strip().lower()
    return (h or "").lower()


def effective_author_handle(card: Dict[str, Any]) -> str:
    h = parse_user_handle(str(card.get("author") or ""))
    if not h:
        raw = str(card.get("user_handle") or "").strip().lstrip("@")
        if raw:
            h = parse_user_handle(raw) or raw.lower()
    if not h:
        h = parse_user_handle(str(card.get("url") or ""))
    if not h:
        h = lookup_tweet_author(str(card.get("tweet_id") or ""))
    lid = str(card.get("list_id") or "")
    if not h and lid.startswith("user:"):
        h = lid.split(":", 1)[-1].strip().lower()
    return (h or "").lower()


def normalize_card_author_fields(card: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(card)
    h = effective_author_handle(out)
    if not h:
        return out
    out["user_handle"] = h
    if not str(out.get("author") or "").strip():
        out["author"] = f"@{h}"
    url = str(out.get("url") or "")
    tid = str(out.get("tweet_id") or "").strip()
    if tid and (not url or "/i/web/status/" in url):
        out["url"] = f"https://x.com/{h}/status/{tid}"
    return out


def is_unmapped_channel_label(name: str) -> bool:
    return str(name or "").strip() in _UNMAPPED_LABELS