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
_LOCK = threading.RLock()
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


def card_dedup_key(user_handle: str, created_at_ts: int) -> str:
    h = str(user_handle or "").strip().lower()
    ts = int(created_at_ts or 0)
    if h and ts > 0:
        return f"{h}:{ts}"
    return ""


def _merge_cards(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    from signals.labels import is_trade_signal

    out = dict(existing)
    for key in ("url", "text", "author", "time_label", "display_time", "created_at", "parsed_at"):
        val = incoming.get(key)
        if val:
            out[key] = val
    if incoming.get("tweet_id"):
        out["tweet_id"] = incoming["tweet_id"]
    if incoming.get("user_handle"):
        out["user_handle"] = str(incoming["user_handle"]).strip().lower()
    elif not out.get("user_handle"):
        out["user_handle"] = _card_user_handle(out)

    lids: set[str] = set()
    for src in (existing, incoming):
        lid = str(src.get("list_id") or "").strip()
        if lid:
            lids.add(lid)
        for x in src.get("list_ids") or []:
            xs = str(x or "").strip()
            if xs:
                lids.add(xs)
    numeric = sorted(x for x in lids if x and not x.startswith("user:"))
    if numeric:
        out["list_id"] = numeric[0]
    elif lids:
        out["list_id"] = sorted(lids)[0]
    if len(lids) > 1:
        out["list_ids"] = sorted(lids)

    modes: set[str] = set()
    for src in (existing, incoming):
        sm = str(src.get("source_mode") or "").strip()
        if sm:
            modes.add(sm)
        for x in src.get("source_modes") or []:
            xs = str(x or "").strip()
            if xs:
                modes.add(xs)
    if modes:
        out["source_modes"] = sorted(modes)
        out["source_mode"] = str(incoming.get("source_mode") or out.get("source_mode") or sorted(modes)[-1])

    ex_sig = existing.get("signal") if isinstance(existing.get("signal"), dict) else {}
    in_sig = incoming.get("signal") if isinstance(incoming.get("signal"), dict) else {}
    if is_trade_signal(in_sig) and not is_trade_signal(ex_sig):
        out["signal"] = in_sig
    elif is_trade_signal(ex_sig):
        out["signal"] = ex_sig
    else:
        out["signal"] = in_sig or ex_sig

    if incoming.get("images"):
        out["images"] = incoming["images"]
    if incoming.get("cards_api_id"):
        out["cards_api_id"] = incoming["cards_api_id"]
    elif existing.get("cards_api_id"):
        out["cards_api_id"] = existing["cards_api_id"]
    if incoming.get("id"):
        out["id"] = incoming["id"]
    return out


def dedup_cards_by_user_time(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for card in cards:
        handle = _card_user_handle(card)
        ts = _card_created_ts(card)
        key = card_dedup_key(handle, ts) or str(card.get("tweet_id") or card.get("id") or id(card))
        if key not in merged:
            merged[key] = dict(card)
            order.append(key)
        else:
            merged[key] = _merge_cards(merged[key], card)
    out = [merged[k] for k in order]
    out.sort(key=lambda c: (_card_created_ts(c), str(c.get("tweet_id") or "")), reverse=True)
    return out


def _split_card_fields(card: Dict[str, Any]) -> Dict[str, Any]:
    extra_keys = (
        "id",
        "cards_api_id",
        "cache_only",
        "channel",
        "time_label",
        "source_mode",
        "source_modes",
        "list_ids",
        "user_handle",
        "value_eval",
        "category",
        "key_takeaways",
    )
    extra = {k: card[k] for k in extra_keys if k in card}
    vs = card.get("value_score")
    try:
        value_score = float(vs) if vs is not None and vs != "" else None
    except Exception:
        value_score = None
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
        "value_score": value_score,
        "value_recommended": 1 if card.get("value_recommended") else 0,
        "expires_at": str(card.get("expires_at") or "").strip(),
        "archived": 1 if card.get("archived") else 0,
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
    if "value_score" in d and d.get("value_score") is not None:
        try:
            card["value_score"] = float(d["value_score"])
        except Exception:
            pass
    if "value_recommended" in d:
        card["value_recommended"] = int(d.get("value_recommended") or 0)
    if d.get("expires_at"):
        card["expires_at"] = d.get("expires_at") or ""
    if "archived" in d:
        card["archived"] = int(d.get("archived") or 0)
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
        _ensure_value_columns(conn)
    return DB_PATH


def _ensure_value_columns(conn: sqlite3.Connection) -> None:
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(signal_cards)").fetchall()}
    alters = []
    if "value_score" not in cols:
        alters.append("ALTER TABLE signal_cards ADD COLUMN value_score REAL")
    if "value_recommended" not in cols:
        alters.append(
            "ALTER TABLE signal_cards ADD COLUMN value_recommended INTEGER NOT NULL DEFAULT 0"
        )
    if "expires_at" not in cols:
        alters.append(
            "ALTER TABLE signal_cards ADD COLUMN expires_at TEXT NOT NULL DEFAULT ''"
        )
    if "archived" not in cols:
        alters.append(
            "ALTER TABLE signal_cards ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
        )
    for sql in alters:
        try:
            conn.execute(sql)
        except Exception:
            pass


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


def _upsert_fields(conn: sqlite3.Connection, fields: Dict[str, Any], now: str) -> int:
    row_id = _find_row_id(conn, fields)
    if row_id:
        conn.execute(
            """
            UPDATE signal_cards SET
                tweet_id=?, list_id=?, user_handle=?, author=?, url=?, text=?,
                created_at=?, created_at_ts=?, time_label=?, display_time=?,
                parsed_at=?, signal_json=?, images_json=?, extra_json=?,
                card_uid=?, updated_at=?,
                value_score=?, value_recommended=?, expires_at=?, archived=?
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
                fields.get("value_score"),
                int(fields.get("value_recommended") or 0),
                fields.get("expires_at") or "",
                int(fields.get("archived") or 0),
                row_id,
            ),
        )
        return row_id
    conn.execute(
        """
        INSERT INTO signal_cards (
            tweet_id, list_id, user_handle, author, url, text,
            created_at, created_at_ts, time_label, display_time,
            parsed_at, signal_json, images_json, extra_json,
            card_uid, updated_at,
            value_score, value_recommended, expires_at, archived
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            fields.get("value_score"),
            int(fields.get("value_recommended") or 0),
            fields.get("expires_at") or "",
            int(fields.get("archived") or 0),
        ),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def db_upsert_card(card: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    now = _now_iso()
    with _LOCK:
        with connect() as conn:
            fields = _split_card_fields(card)
            row_id = _find_row_id(conn, fields)
            if row_id:
                row = conn.execute("SELECT * FROM signal_cards WHERE id=?", (row_id,)).fetchone()
                if row:
                    card = _merge_cards(_row_to_card(row), card)
                    fields = _split_card_fields(card)
            row_id = _upsert_fields(conn, fields, now)
            row = conn.execute("SELECT * FROM signal_cards WHERE id=?", (row_id,)).fetchone()
    return _row_to_card(row) if row else dict(card)


def db_get_card_by_user_time(user_handle: str, created_at_ts: int) -> Optional[Dict[str, Any]]:
    h = _parse_user_handle(user_handle) or str(user_handle or "").strip().lstrip("@")
    ts = int(created_at_ts or 0)
    if not h or ts <= 0:
        return None
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM signal_cards WHERE user_handle=? AND created_at_ts=? LIMIT 1",
            (h.lower(), ts),
        ).fetchone()
    return _row_to_card(row) if row else None


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
    merge_sources: bool = False,
    source_mode: str = "",
    min_score: Optional[float] = None,
    recommended_only: bool = False,
    hide_expired: bool = True,
) -> List[Dict[str, Any]]:
    from signals.crawl import normalize_twimg_url
    from signals.labels import is_trade_signal
    from signals.value.store_policy import is_expired_card

    init_db()
    lid = _parse_list_id(list_id) if list_id and not str(list_id).startswith("user:") else str(list_id or "").strip()
    handle = _parse_user_handle(user_handle) or ""
    if str(list_id).startswith("user:"):
        handle = _parse_user_handle(list_id.split(":", 1)[-1]) or handle

    clauses: List[str] = []
    params: List[Any] = []

    if not merge_sources and lid and not lid.startswith("user:"):
        clauses.append("(list_id=? OR list_id='')")
        params.append(lid)
    if handle:
        scope = _user_scope_id(handle)
        hlow = handle.lower()
        if merge_sources:
            clauses.append("(user_handle=? OR list_id=? OR lower(author) LIKE ?)")
            params.extend([hlow, scope, f"@{hlow}"])
        elif not lid or lid.startswith("user:"):
            clauses.append("(user_handle=? OR list_id=? OR lower(author) LIKE ?)")
            params.extend([hlow, scope, f"@{hlow}"])

    if from_ts is not None:
        clauses.append("created_at_ts>=?")
        params.append(int(from_ts))
    if to_ts is not None:
        clauses.append("created_at_ts<=?")
        params.append(int(to_ts))

    if min_score is not None:
        clauses.append("(value_score IS NOT NULL AND value_score>=?)")
        params.append(float(min_score))
    if recommended_only:
        clauses.append("value_recommended=1")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    lim = max(1, min(int(limit or 100), 500))
    # 多取一些再内存过滤 source_mode / TTL
    fetch_lim = lim * 3 if (source_mode or hide_expired) else lim
    sql = f"SELECT * FROM signal_cards {where} ORDER BY created_at_ts DESC, id DESC LIMIT ?"
    params.append(fetch_lim)

    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    want_mode = str(source_mode or "").strip()
    out: List[Dict[str, Any]] = []
    for row in rows:
        card = _row_to_card(row)
        modes = card.get("source_modes") if isinstance(card.get("source_modes"), list) else []
        mode = str(card.get("source_mode") or "")
        is_value = mode == "value_return" or "value_return" in modes
        is_value_only = is_value and mode == "value_return" and (
            not modes or set(modes) == {"value_return"}
        )

        if want_mode == "value_return":
            if not is_value:
                continue
        elif want_mode:
            if want_mode not in modes and mode != want_mode:
                continue
        else:
            # 未指定 source：列表/博主默认视图排除「仅价值」卡
            if is_value_only:
                continue

        if hide_expired and is_expired_card(card):
            continue
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
        if len(out) >= lim:
            break
    if merge_sources:
        out = dedup_cards_by_user_time(out)
    return out


def db_archive_card(tweet_id: str) -> Optional[Dict[str, Any]]:
    tid = str(tweet_id or "").strip()
    if not tid:
        return None
    init_db()
    card = db_get_card_by_tweet_id(tid)
    if not card:
        return None
    card["archived"] = 1
    card["expires_at"] = ""
    return db_upsert_card(card)


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
    now = _now_iso()
    n = 0
    with _LOCK:
        with connect() as conn:
            for c in cards:
                if not isinstance(c, dict):
                    continue
                try:
                    fields = _split_card_fields(c)
                    _upsert_fields(conn, fields, now)
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
        cnt = db_count()
        if cnt == 0 and state_cards:
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
