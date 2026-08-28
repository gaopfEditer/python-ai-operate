# coding=utf-8
"""博主回溯 / 卡片筛选 — 时间范围预设。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

BACKFILL_RANGE_LABELS = {
    "last_7d": "近7天",
    "last_14d": "近14天",
    "last_2w": "两周内",
    "last_30d": "近30天",
    "last_90d": "近90天",
    "this_week": "本周",
    "this_month": "本月",
    "this_quarter": "本季度",
}

DEFAULT_BACKFILL_RANGE = "last_7d"
VALID_BACKFILL_RANGES = frozenset(BACKFILL_RANGE_LABELS)


def normalize_backfill_range(raw: object, *, fallback: str = DEFAULT_BACKFILL_RANGE) -> str:
    key = str(raw or "").strip().lower()
    if key in VALID_BACKFILL_RANGES:
        return key
    fb = fallback if fallback in VALID_BACKFILL_RANGES else DEFAULT_BACKFILL_RANGE
    return fb


def weeks_to_backfill_range(weeks: object) -> str:
    try:
        w = max(1, min(int(weeks or 1), 52))
    except Exception:
        return DEFAULT_BACKFILL_RANGE
    if w <= 1:
        return "last_7d"
    if w <= 2:
        return "last_14d"
    if w <= 4:
        return "last_30d"
    return "last_90d"


def resolve_backfill_range(raw: object, *, cfg: Optional[dict] = None) -> str:
    if raw is not None and str(raw).strip():
        return normalize_backfill_range(raw)
    if cfg:
        if cfg.get("user_backfill_range"):
            return normalize_backfill_range(cfg.get("user_backfill_range"))
        if cfg.get("user_weeks") is not None:
            return weeks_to_backfill_range(cfg.get("user_weeks"))
    return DEFAULT_BACKFILL_RANGE


def resolve_backfill_since(
    range_key: str,
    *,
    now: Optional[datetime] = None,
) -> Tuple[datetime, str]:
    now = now or datetime.now(timezone.utc).astimezone()
    key = normalize_backfill_range(range_key)
    label = BACKFILL_RANGE_LABELS[key]

    if key == "last_7d":
        since = now - timedelta(days=7)
    elif key in ("last_14d", "last_2w"):
        since = now - timedelta(days=14)
    elif key == "last_30d":
        since = now - timedelta(days=30)
    elif key == "last_90d":
        since = now - timedelta(days=90)
    elif key == "this_week":
        since = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif key == "this_month":
        since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif key == "this_quarter":
        qm = ((now.month - 1) // 3) * 3 + 1
        since = now.replace(month=qm, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        since = now - timedelta(days=7)
        label = BACKFILL_RANGE_LABELS[DEFAULT_BACKFILL_RANGE]
    return since, label


def backfill_range_span_days(range_key: str, *, now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc).astimezone()
    since, _ = resolve_backfill_since(range_key, now=now)
    return max(1, (now - since).days + 1)


def resolve_backfill_time_range(
    range_key: str,
    *,
    now: Optional[datetime] = None,
) -> Tuple[Optional[int], Optional[int]]:
    """将回溯预设转为 Unix 时间戳区间（from_ts 含，to_ts 默认不限）。"""
    since, _ = resolve_backfill_since(range_key, now=now)
    return int(since.timestamp()), None
