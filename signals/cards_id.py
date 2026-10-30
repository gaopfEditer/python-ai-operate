# coding=utf-8
"""Cards API 对外 id：博主 + 发帖时间（与 SQLite 去重键一致）。"""

from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4

from signals.card_db import _card_created_ts, card_dedup_key
from signals.store import parse_user_handle


def cards_api_external_id(card: Dict[str, Any]) -> str:
    """
    POST /api/v1/cards 的 id 字段。
    优先 tweet_id；否则 handle + 发帖 unix 时间（与 card_dedup_key 相同）。
    """
    tid = str(card.get("tweet_id") or "").strip()
    h = parse_user_handle(str(card.get("user_handle") or card.get("author") or ""))
    ts = _card_created_ts(card)
    dk = card_dedup_key(h, ts)
    if dk:
        return dk
    if tid:
        return f"x:{tid}"
    return f"sig-{uuid4().hex[:12]}"
