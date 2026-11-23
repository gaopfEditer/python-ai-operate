# coding=utf-8
"""补全 signal_cards 中缺失的 author（依赖列表 API + tweet 作者缓存）。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from signals.card_author import normalize_card_author_fields, stored_author_handle
from signals.store import get_card_by_tweet_id, upsert_card
from signals.tweet_author_cache import record_tweet_authors


def backfill_cards_missing_authors(
    list_id: str,
    *,
    max_tweets: int = 250,
    days: int = 14,
    progress=None,
) -> Dict[str, Any]:
    from signals.x_api import fetch_list_timeline_api

    since = datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))
    res = fetch_list_timeline_api(
        list_id,
        since=since,
        max_tweets=max_tweets,
        progress=progress,
    )
    items: List[Dict[str, Any]] = list(res.get("items") or [])
    record_tweet_authors(items)
    updated = 0
    skipped = 0
    for it in items:
        tid = str(it.get("tweet_id") or "").strip()
        if not tid:
            continue
        card = get_card_by_tweet_id(tid)
        if not card:
            skipped += 1
            continue
        if stored_author_handle(card):
            continue
        merged = normalize_card_author_fields({**dict(card), **it})
        if not stored_author_handle(merged):
            continue
        upsert_card(merged)
        updated += 1
    return {
        "success": bool(res.get("success")),
        "list_id": list_id,
        "fetched": len(items),
        "updated": updated,
        "skipped_no_card": skipped,
        "error": res.get("error"),
    }