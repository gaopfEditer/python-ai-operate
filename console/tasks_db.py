# coding=utf-8
"""任务系统 SQLite 存储（console/data/tasks.db）。"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

CONSOLE_DIR = Path(__file__).resolve().parent
DATA_DIR = CONSOLE_DIR / "data"
DB_PATH = DATA_DIR / "tasks.db"

STATE_KEYS = (
    "store",
    "months",
    "notes",
    "day_notes",
    "period",
    "tpl_cfg",
    "tpl_custom",
    "prefs",
)

_LOCK = threading.RLock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> Path:
    with _LOCK:
        with connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
    return DB_PATH


def _default_value(key: str) -> Any:
    if key == "store":
        return {
            "tasks": [],
            "templateApplied": {},
            "catalogDismissed": {},
            "instanceDismissed": {},
        }
    if key == "tpl_custom":
        return []
    if key == "prefs":
        return {"mode": "home", "board": {}}
    return {}


def get_state(keys: Optional[List[str]] = None) -> Dict[str, Any]:
    init_db()
    wanted = list(keys) if keys else list(STATE_KEYS)
    out: Dict[str, Any] = {k: _default_value(k) for k in wanted}
    with _LOCK:
        with connect() as conn:
            placeholders = ",".join("?" for _ in wanted)
            rows = conn.execute(
                f"SELECT key, value FROM task_state WHERE key IN ({placeholders})",
                wanted,
            ).fetchall()
            for row in rows:
                key = row["key"]
                try:
                    out[key] = json.loads(row["value"])
                except json.JSONDecodeError:
                    out[key] = _default_value(key)
    return out


def patch_state(patch: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(patch, dict) or not patch:
        return get_state()

    init_db()
    now = _utc_now()
    with _LOCK:
        with connect() as conn:
            for key, value in patch.items():
                if key not in STATE_KEYS:
                    continue
                conn.execute(
                    """
                    INSERT INTO task_state (key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (key, json.dumps(value, ensure_ascii=False), now),
                )
            conn.commit()
    return get_state(list(patch.keys()))
