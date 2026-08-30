# coding=utf-8
"""SQLite 事件存储。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from realtime_info.config import DB_PATH, ensure_output_dir, load_settings
from realtime_info.models import Event, row_to_event, utc_now_iso


def _resolve_db_path(db_path: Optional[Path] = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    cfg = load_settings()
    storage = cfg.get("storage") if isinstance(cfg.get("storage"), dict) else {}
    custom = str(storage.get("db_path") or "").strip()
    if custom:
        return Path(custom)
    ensure_output_dir()
    return DB_PATH


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = _resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None) -> Path:
    path = _resolve_db_path(db_path)
    with connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'info',
                title TEXT NOT NULL DEFAULT '',
                draft_text TEXT NOT NULL DEFAULT '',
                raw_json TEXT NOT NULL DEFAULT '{}',
                extracted_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                note TEXT NOT NULL DEFAULT '',
                cooled_until TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(module, fingerprint)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_status ON events(status, created_at DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS debounce (
                key TEXT PRIMARY KEY,
                cooled_until TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    return path


def insert_event(event: Event, db_path: Optional[Path] = None) -> Optional[Event]:
    init_db(db_path)
    row = event.to_row()
    with connect(db_path) as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO events (
                    module, fingerprint, severity, title, draft_text,
                    raw_json, extracted_json, status, note, cooled_until,
                    created_at, updated_at
                ) VALUES (
                    :module, :fingerprint, :severity, :title, :draft_text,
                    :raw_json, :extracted_json, :status, :note, :cooled_until,
                    :created_at, :updated_at
                )
                """,
                row,
            )
            conn.commit()
            eid = int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None
    return get_event(eid, db_path=db_path)


def get_event(event_id: int, db_path: Optional[Path] = None) -> Optional[Event]:
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM events WHERE id=?", (int(event_id),)
        ).fetchone()
    return row_to_event(row) if row else None


def list_events(
    *,
    status: str = "",
    module: str = "",
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[Path] = None,
) -> List[Event]:
    init_db(db_path)
    clauses: List[str] = []
    params: List[Any] = []
    if status:
        clauses.append("status=?")
        params.append(status)
    if module:
        clauses.append("module=?")
        params.append(module)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM events{where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([int(limit), int(offset)])
    with connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [row_to_event(r) for r in rows]


def count_events(
    *,
    status: str = "",
    module: str = "",
    db_path: Optional[Path] = None,
) -> int:
    init_db(db_path)
    clauses: List[str] = []
    params: List[Any] = []
    if status:
        clauses.append("status=?")
        params.append(status)
    if module:
        clauses.append("module=?")
        params.append(module)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect(db_path) as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS c FROM events{where}", params
        ).fetchone()
    return int(row["c"] if row else 0)


def update_event_status(
    event_id: int,
    status: str,
    *,
    note: str = "",
    db_path: Optional[Path] = None,
) -> Optional[Event]:
    init_db(db_path)
    now = utc_now_iso()
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE events
            SET status=?, note=CASE WHEN ?!='' THEN ? ELSE note END, updated_at=?
            WHERE id=?
            """,
            (status, note, note, now, int(event_id)),
        )
        conn.commit()
    return get_event(event_id, db_path=db_path)


def stats(db_path: Optional[Path] = None) -> Dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM events GROUP BY status"
        ).fetchall()
        by_mod = conn.execute(
            "SELECT module, COUNT(*) AS c FROM events GROUP BY module"
        ).fetchall()
    return {
        "by_status": {str(r["status"]): int(r["c"]) for r in rows},
        "by_module": {str(r["module"]): int(r["c"]) for r in by_mod},
        "pending": count_events(status="pending", db_path=db_path),
    }
