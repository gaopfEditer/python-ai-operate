# coding=utf-8
"""TTL / 归档策略。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def resolve_expires_at(
    *,
    score: float,
    threshold: float,
    archived: bool = False,
    low_ttl_days: int = 2,
) -> Optional[str]:
    """
    达标或归档 → 不过期 (None)；
    否则 now + 2 天。
    """
    if archived or score >= threshold:
        return None
    exp = _now() + timedelta(days=max(1, int(low_ttl_days)))
    return exp.isoformat(timespec="seconds")


def apply_store_policy(
    card: Dict[str, Any],
    *,
    score: float,
    threshold: float,
    recommended: bool,
) -> Dict[str, Any]:
    out = dict(card)
    archived = bool(out.get("archived"))
    expires = resolve_expires_at(
        score=score, threshold=threshold, archived=archived
    )
    out["value_score"] = float(score)
    out["value_recommended"] = 1 if recommended or score >= threshold else 0
    out["expires_at"] = expires or ""
    if archived:
        out["archived"] = 1
        out["expires_at"] = ""
    return out


def is_expired_card(card: Dict[str, Any], *, now: Optional[datetime] = None) -> bool:
    if card.get("archived"):
        return False
    raw = str(card.get("expires_at") or "").strip()
    if not raw:
        return False
    try:
        text = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except Exception:
        return False
    n = now or _now()
    if n.tzinfo is None:
        n = n.replace(tzinfo=timezone.utc)
    return dt <= n
