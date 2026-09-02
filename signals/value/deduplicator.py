# coding=utf-8
"""去重：已评估过的价值卡跳过。"""

from __future__ import annotations

from typing import Any, Dict, Optional


def already_evaluated(
    tweet: Dict[str, Any],
    *,
    reparse: bool = False,
) -> Optional[Dict[str, Any]]:
    """若库中已有 value_return 评估结果则返回该卡，否则 None。"""
    if reparse:
        return None
    from signals.store import get_card_by_dedup

    tid = str(tweet.get("tweet_id") or "").strip()
    author = str(tweet.get("author") or "")
    created = str(tweet.get("created_at") or "")
    card = get_card_by_dedup(tweet_id=tid, author=author, created_at=created)
    if not card:
        return None
    modes = card.get("source_modes") if isinstance(card.get("source_modes"), list) else []
    mode = str(card.get("source_mode") or "")
    if "value_return" in modes or mode == "value_return":
        if card.get("value_score") is not None or isinstance(card.get("value_eval"), dict):
            return card
    # extra 里也可能嵌了评估
    extra_eval = card.get("value_eval")
    if isinstance(extra_eval, dict) and extra_eval.get("score") is not None:
        return card
    return None
