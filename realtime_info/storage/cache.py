# coding=utf-8
"""防抖 / 冷却（SQLite；接口可日后换 Redis）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from realtime_info.storage.db import connect, init_db


def _parse_iso(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_cooled(key: str, *, db_path: Optional[Path] = None) -> bool:
    """True = 仍在冷却，应跳过。"""
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT cooled_until FROM debounce WHERE key=?", (key,)
        ).fetchone()
    if not row:
        return False
    until = _parse_iso(str(row["cooled_until"] or ""))
    if not until:
        return False
    return _now() < until


def mark_cooldown(
    key: str,
    hours: float,
    *,
    db_path: Optional[Path] = None,
) -> str:
    init_db(db_path)
    until = _now() + timedelta(hours=float(hours or 0))
    until_s = until.replace(microsecond=0).isoformat()
    now_s = _now().replace(microsecond=0).isoformat()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO debounce (key, cooled_until, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                cooled_until=excluded.cooled_until,
                updated_at=excluded.updated_at
            """,
            (key, until_s, now_s),
        )
        conn.commit()
    return until_s


def clear_cooldown(key: str, *, db_path: Optional[Path] = None) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute("DELETE FROM debounce WHERE key=?", (key,))
        conn.commit()
