# coding=utf-8
"""X 列表信号卡片 — 本地 SQLite 存储（按用户/时间筛选，发帖时间去重）。"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORE_DIR = PROJECT_ROOT / "output" / "signals"
DB_PATH = STORE_DIR / "cards.db"
_LOCK = threading.Lock()
_MIGRATED = False

_USER_PATH_SKIP = frozenset(
    {"i", "home", "search", "explore", "notifications", "messages", "settings", "compose", "intent", "hashtag", "lists"}
)


def _parse_user_handle(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    m = re.search(r"(?:x\.com|twitter\.com)/([^/?#]+)", text, re.I)
    if m:
        handle = m.group(1).strip().lstrip("@")
        if handle.lower() in _USER_PATH_SKIP:
            return ""
        return handle
    if text.startswith("@"):
        return text[1:].split("/")[0].strip()
    if re.match(r"^[A-Za-z0-9_]{1,15}$", text):
        return text
    return ""


def _user_scope_id(handle: str) -> str:
    h = _parse_user_handle(handle) or (handle or "").strip().lstrip("@")
    return f"user:{h.lower()}" if h else ""


def _parse_list_id(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    m = re.search(r"/lists/(\d+)", text)
    if m:
        return m.group(1)
    m = re.search(r"^(\d{6,})$", text)
    return m.group(1) if m else ""


def _parse_dt(raw: str) -> Optional[datetime]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _dumps(v: Any) -> str:
    return json.dumps(v if v is not None else {}, ensure_ascii=False)


def _loads(raw: Any, default: Any = None) -> Any:
    if default is None:
        default = {}
    if raw is None or raw == "":
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return default


def _card_user_handle(card: Dict[str, Any]) -> str:
    lid = str(card.get("list_id") or "")
    if lid.startswith("user:"):
        return lid.split(":", 1)[-1].strip().lower()
    h = _parse_user_handle(str(card.get("author") or ""))
    return h.lower() if h else ""


def _card_created_ts(card: Dict[str, Any]) -> int:
    for key in ("created_at", "display_time", "parsed_at"):
        dt = _parse_dt(str(card.get(key) or ""))
        if dt is not None:
            return int(dt.timestamp())
    return 0


def _split_card_fields(card: Dict[str, Any]) -> Dict[str, Any]:
    extra_keys = (
        "id",
        "cards_api_id",
        "cache_only",
        "channel",
        "time_label",
    )
    extra = {k: card[k] for k in extra_keys if k in card}
    return {
        "tweet_id": str(card.get("tweet_id") or "").strip(),
        "list_id": str(card.get("list_id") or "").strip(),
        "user_handle": _card_user_handle(card),
        "author": str(card.get("author") or "").strip(),
        "url": str(card.get("url") or "").strip(),
        "text": str(card.get("text") or ""),
        "created_at": str(card.get("created_at") or "").strip(),
        "created_at_ts": _card_created_ts(card),
        "time_label": str(card.get("time_label") or "").strip(),
        "display_time": str(card.get("display_time") or "").strip(),
        "parsed_at": str(card.get("parsed_at") or "").strip(),
        "signal_json": _dumps(card.get("signal") if isinstance(card.get("signal"), dict) else {}),
        "images_json": _dumps(card.get("images") if isinstance(card.get("images"), list) else []),
        "extra_json": _dumps(extra),
        "card_uid": str(card.get("id") or "").strip(),
    }


def _row_to_card(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    card: Dict[str, Any] = {
        "tweet_id": d.get("tweet_id") or "",
        "list_id": d.get("list_id") or "",
        "author": d.get("author") or "",
        "url": d.get("url") or "",
        "text": d.get("text") or "",
        "created_at": d.get("created_at") or "",
        "time_label": d.get("time_label") or "",
        "display_time": d.get("display_time") or "",
        "parsed_at": d.get("parsed_at") or "",
        "signal": _loads(d.get("signal_json"), {}),
        "images": _loads(d.get("images_json"), []),
    }
    extra = _loads(d.get("extra_json"), {})
    if isinstance(extra, dict):
        for k, v in extra.items():
            if k not in card:
                card[k] = v
    if d.get("card_uid") and not card.get("id"):
        card["id"] = d["card_uid"]
    return card


@contextmanager
def connect():
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> Path:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS signal_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tweet_id TEXT NOT NULL DEFAULT '',
                list_id TEXT NOT NULL DEFAULT '',
                user_handle TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '',
                created_at_ts INTEGER NOT NULL DEFAULT 0,
                time_label TEXT NOT NULL DEFAULT '',
                display_time TEXT NOT NULL DEFAULT '',
                parsed_at TEXT NOT NULL DEFAULT '',
                signal_json TEXT NOT NULL DEFAULT '{}',
                images_json TEXT NOT NULL DEFAULT '[]',
                extra_json TEXT NOT NULL DEFAULT '{}',
                card_uid TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_signal_cards_tweet
                ON signal_cards(tweet_id);
            CREATE INDEX IF NOT EXISTS idx_signal_cards_list
                ON signal_cards(list_id);
            CREATE INDEX IF NOT EXISTS idx_signal_cards_user
                ON signal_cards(user_handle);
            CREATE INDEX IF NOT EXISTS idx_signal_cards_created
                ON signal_cards(created_at_ts DESC);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_signal_cards_user_time
                ON signal_cards(user_handle, created_at_ts)
                WHERE user_handle != '' AND created_at_ts > 0;
            CREATE UNIQUE INDEX IF NOT EXISTS idx_signal_cards_tweet_unique
                ON signal_cards(tweet_id)
                WHERE tweet_id != '';
            """
        )
    return DB_PATH


def _find_row_id(conn: sqlite3.Connection, fields: Dict[str, Any]) -> Optional[int]:
    tid = fields["tweet_id"]
    if tid:
        row = conn.execute(
            "SELECT id FROM signal_cards WHERE tweet_id=? LIMIT 1",
            (tid,),
        ).fetchone()
        if row:
            return int(row["id"])
    handle = fields["user_handle"]
    ts = int(fields["created_at_ts"] or 0)
    if handle and ts > 0:
        row = conn.execute(
            "SELECT id FROM signal_cards WHERE user_handle=? AND created_at_ts=? LIMIT 1",
            (handle, ts),
        ).fetchone()
        if row:
            return int(row["id"])
    return None


def db_upsert_card(card: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    fields = _split_card_fields(card)
    now = _now_iso()
    with _LOCK:
        with connect() as conn:
            row_id = _find_row_id(conn, fields)
            if row_id:
                conn.execute(
                    """
                    UPDATE signal_cards SET
                        tweet_id=?, list_id=?, user_handle=?, author=?, url=?, text=?,
                        created_at=?, created_at_ts=?, time_label=?, display_time=?,
                        parsed_at=?, signal_json=?, images_json=?, extra_json=?,
                        card_uid=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        fields["tweet_id"],
                        fields["list_id"],
                        fields["user_handle"],
                        fields["author"],
                        fields["url"],
                        fields["text"],
                        fields["created_at"],
                        fields["created_at_ts"],
                        fields["time_label"],
                        fields["display_time"],
                        fields["parsed_at"],
                        fields["signal_json"],
                        fields["images_json"],
                        fields["extra_json"],
                        fields["card_uid"],
                        now,
                        row_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO signal_cards (
                        tweet_id, list_id, user_handle, author, url, text,
                        created_at, created_at_ts, time_label, display_time,
                        parsed_at, signal_json, images_json, extra_json,
                        card_uid, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fields["tweet_id"],
                        fields["list_id"],
                        fields["user_handle"],
                        fields["author"],
                        fields["url"],
                        fields["text"],
                        fields["created_at"],
                        fields["created_at_ts"],
                        fields["time_label"],
                        fields["display_time"],
                        fields["parsed_at"],
                        fields["signal_json"],
                        fields["images_json"],
                        fields["extra_json"],
                        fields["card_uid"],
                        now,
                    ),
                )
                row_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            row = conn.execute("SELECT * FROM signal_cards WHERE id=?", (row_id,)).fetchone()
    return _row_to_card(row) if row else dict(card)


def db_get_card_by_tweet_id(tweet_id: str) -> Optional[Dict[str, Any]]:
    tid = str(tweet_id or "").strip()
    if not tid:
        return None
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM signal_cards WHERE tweet_id=? LIMIT 1",
            (tid,),
        ).fetchone()
    return _row_to_card(row) if row else None


def db_save_card_remote_id(tweet_id: str, cards_api_id: int) -> None:
    tid = str(tweet_id or "").strip()
    if not tid or not cards_api_id:
        return
    card = db_get_card_by_tweet_id(tid)
    if not card:
        return
    card["cards_api_id"] = int(cards_api_id)
    db_upsert_card(card)


def db_list_cards(
    *,
    list_id: str = "",
    user_handle: str = "",
    only_trade: bool = False,
    limit: int = 100,
    from_ts: Optional[int] = None,
    to_ts: Optional[int] = None,
) -> List[Dict[str, Any]]:
    from signals.crawl import normalize_twimg_url
    from signals.labels import is_trade_signal

    init_db()
    lid = _parse_list_id(list_id) if list_id and not str(list_id).startswith("user:") else str(list_id or "").strip()
    handle = _parse_user_handle(user_handle) or ""
    if str(list_id).startswith("user:"):
        handle = _parse_user_handle(list_id.split(":", 1)[-1]) or handle

    clauses: List[str] = []
    params: List[Any] = []

    if lid and not lid.startswith("user:"):
        clauses.append("(list_id=? OR list_id='')")
        params.append(lid)
    if handle:
        scope = _user_scope_id(handle)
        hlow = handle.lower()
        clauses.append("(user_handle=? OR list_id=? OR lower(author) LIKE ?)")
        params.extend([hlow, scope, f"@{hlow}"])

    if from_ts is not None:
        clauses.append("created_at_ts>=?")
        params.append(int(from_ts))
    if to_ts is not None:
        clauses.append("created_at_ts<=?")
        params.append(int(to_ts))

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    lim = max(1, min(int(limit or 100), 500))
    sql = f"SELECT * FROM signal_cards {where} ORDER BY created_at_ts DESC, id DESC LIMIT ?"
    params.append(lim)

    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    out: List[Dict[str, Any]] = []
    for row in rows:
        card = _row_to_card(row)
        sig = card.get("signal") if isinstance(card.get("signal"), dict) else {}
        if only_trade and not is_trade_signal(sig):
            continue
        imgs = card.get("images")
        if isinstance(imgs, list) and imgs:
            fixed = []
            for im in imgs:
                if not isinstance(im, dict):
                    continue
                item = dict(im)
                item["url"] = normalize_twimg_url(str(item.get("url") or "")) or str(item.get("url") or "")
                fixed.append(item)
            card["images"] = fixed
        out.append(card)
    return out


def db_delete_user_cards(handle: str) -> List[str]:
    h = _parse_user_handle(handle) or (handle or "").strip().lstrip("@")
    if not h:
        return []
    scope = _user_scope_id(h)
    hlow = h.lower()
    init_db()
    removed: List[str] = []
    with _LOCK:
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT tweet_id FROM signal_cards
                WHERE user_handle=? OR list_id=? OR lower(author) LIKE ?
                """,
                (hlow, scope, f"@{hlow}"),
            ).fetchall()
            removed = [str(r["tweet_id"] or "").strip() for r in rows if str(r["tweet_id"] or "").strip()]
            conn.execute(
                """
                DELETE FROM signal_cards
                WHERE user_handle=? OR list_id=? OR lower(author) LIKE ?
                """,
                (hlow, scope, f"@{hlow}"),
            )
    return removed


def db_count() -> int:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM signal_cards").fetchone()
    return int(row["c"]) if row else 0


def migrate_from_state_cards(cards: List[Dict[str, Any]]) -> int:
    """一次性从 state.json cards 数组导入 SQLite。"""
    if not cards:
        return 0
    init_db()
    n = 0
    for c in cards:
        if not isinstance(c, dict):
            continue
        try:
            db_upsert_card(c)
            n += 1
        except Exception:
            continue
    return n


def ensure_migrated(state_cards: Optional[List[Dict[str, Any]]]) -> bool:
    global _MIGRATED
    if _MIGRATED:
        return False
    init_db()
    with _LOCK:
        if _MIGRATED:
            return False
        migrated = False
        if db_count() == 0 and state_cards:
            migrated = migrate_from_state_cards(state_cards) > 0
        _MIGRATED = True
        return migrated


def resolve_time_range(
    *,
    days: Optional[int] = None,
    from_raw: str = "",
    to_raw: str = "",
) -> tuple[Optional[int], Optional[int]]:
    from_ts: Optional[int] = None
    to_ts: Optional[int] = None
    if from_raw:
        dt = _parse_dt(from_raw)
        if dt:
            from_ts = int(dt.timestamp())
    if to_raw:
        dt = _parse_dt(to_raw)
        if dt:
            to_ts = int(dt.timestamp())
    if days is not None and days > 0 and from_ts is None:
        from_ts = int((datetime.now(timezone.utc) - timedelta(days=int(days))).timestamp())
    return from_ts, to_ts
