# coding=utf-8
"""推文卡片 SQLite 存储。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "output" / "tweet_cards.db"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _dumps(v: Any) -> str:
    return json.dumps(v if v is not None else [], ensure_ascii=False)


def _loads(raw: Any, default: Any = None) -> Any:
    if default is None:
        default = []
    if raw is None or raw == "":
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return default


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
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


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(tweet_cards)").fetchall()
    }
    if "favorited" not in cols:
        conn.execute(
            "ALTER TABLE tweet_cards ADD COLUMN favorited INTEGER NOT NULL DEFAULT 0"
        )
    if "user_category" not in cols:
        conn.execute(
            "ALTER TABLE tweet_cards ADD COLUMN user_category TEXT NOT NULL DEFAULT ''"
        )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tweet_cards_favorited
            ON tweet_cards(favorited);
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tweet_cards_user_category
            ON tweet_cards(user_category);
        """
    )


def init_db() -> Path:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tweet_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tweet_id TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL DEFAULT '',
                author_name TEXT NOT NULL DEFAULT '',
                author_handle TEXT NOT NULL DEFAULT '',
                author_avatar TEXT NOT NULL DEFAULT '',
                text TEXT NOT NULL DEFAULT '',
                created_at_tweet TEXT NOT NULL DEFAULT '',
                likes INTEGER NOT NULL DEFAULT 0,
                replies INTEGER NOT NULL DEFAULT 0,
                retweets INTEGER NOT NULL DEFAULT 0,
                bookmarks INTEGER NOT NULL DEFAULT 0,
                views INTEGER NOT NULL DEFAULT 0,
                images_json TEXT NOT NULL DEFAULT '[]',
                media_json TEXT NOT NULL DEFAULT '{}',
                summary TEXT NOT NULL DEFAULT '',
                core_points_json TEXT NOT NULL DEFAULT '[]',
                emotion TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                category TEXT NOT NULL DEFAULT '',
                llm_json TEXT NOT NULL DEFAULT '{}',
                source TEXT NOT NULL DEFAULT '',
                raw_json TEXT NOT NULL DEFAULT '{}',
                favorited INTEGER NOT NULL DEFAULT 0,
                user_category TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tweet_cards_updated
                ON tweet_cards(updated_at);
            CREATE INDEX IF NOT EXISTS idx_tweet_cards_handle
                ON tweet_cards(author_handle);
            """
        )
        _migrate(conn)
    return DB_PATH


def _effective_category_expr() -> str:
    return "CASE WHEN user_category != '' THEN user_category ELSE category END"


def _row_to_card(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["images"] = _loads(d.pop("images_json", "[]"), [])
    d["media"] = _loads(d.pop("media_json", "{}"), {})
    d["core_points"] = _loads(d.pop("core_points_json", "[]"), [])
    d["tags"] = _loads(d.pop("tags_json", "[]"), [])
    d["llm"] = _loads(d.pop("llm_json", "{}"), {})
    d["raw"] = _loads(d.pop("raw_json", "{}"), {})
    d["favorited"] = bool(int(d.get("favorited") or 0))
    user_cat = str(d.get("user_category") or "").strip()
    ai_cat = str(d.get("category") or "").strip()
    d["user_category"] = user_cat
    d["display_category"] = user_cat or ai_cat
    return d


def upsert_card(payload: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    now = _now()
    tweet_id = str(payload.get("tweet_id") or "").strip()
    if not tweet_id:
        raise ValueError("缺少 tweet_id")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO tweet_cards (
                tweet_id, url, author_name, author_handle, author_avatar,
                text, created_at_tweet,
                likes, replies, retweets, bookmarks, views,
                images_json, media_json,
                summary, core_points_json, emotion, tags_json, category,
                llm_json, source, raw_json,
                favorited, user_category,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '', ?, ?)
            ON CONFLICT(tweet_id) DO UPDATE SET
                url=excluded.url,
                author_name=excluded.author_name,
                author_handle=excluded.author_handle,
                author_avatar=excluded.author_avatar,
                text=excluded.text,
                created_at_tweet=excluded.created_at_tweet,
                likes=excluded.likes,
                replies=excluded.replies,
                retweets=excluded.retweets,
                bookmarks=excluded.bookmarks,
                views=excluded.views,
                images_json=excluded.images_json,
                media_json=excluded.media_json,
                summary=excluded.summary,
                core_points_json=excluded.core_points_json,
                emotion=excluded.emotion,
                tags_json=excluded.tags_json,
                category=excluded.category,
                llm_json=excluded.llm_json,
                source=excluded.source,
                raw_json=excluded.raw_json,
                updated_at=excluded.updated_at
            """,
            (
                tweet_id,
                str(payload.get("url") or ""),
                str(payload.get("author_name") or ""),
                str(payload.get("author_handle") or ""),
                str(payload.get("author_avatar") or ""),
                str(payload.get("text") or ""),
                str(payload.get("created_at_tweet") or ""),
                int(payload.get("likes") or 0),
                int(payload.get("replies") or 0),
                int(payload.get("retweets") or 0),
                int(payload.get("bookmarks") or 0),
                int(payload.get("views") or 0),
                _dumps(payload.get("images") or []),
                _dumps(payload.get("media") or {}),
                str(payload.get("summary") or ""),
                _dumps(payload.get("core_points") or []),
                str(payload.get("emotion") or ""),
                _dumps(payload.get("tags") or []),
                str(payload.get("category") or ""),
                _dumps(payload.get("llm") or {}),
                str(payload.get("source") or ""),
                _dumps(payload.get("raw") or {}),
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM tweet_cards WHERE tweet_id=?", (tweet_id,)
        ).fetchone()
    return _row_to_card(row)


def get_card(tweet_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM tweet_cards WHERE tweet_id=?",
            (str(tweet_id).strip(),),
        ).fetchone()
    return _row_to_card(row) if row else None


def _build_list_query(
    *,
    keyword: str = "",
    category: str = "",
    favorited: Optional[bool] = None,
) -> Tuple[str, List[Any]]:
    where: List[str] = []
    params: List[Any] = []
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        where.append(
            """
            (text LIKE ? OR summary LIKE ? OR author_handle LIKE ?
             OR author_name LIKE ? OR tags_json LIKE ?)
            """
        )
        params.extend([like, like, like, like, like])
    cat = (category or "").strip()
    if cat:
        where.append(f"({_effective_category_expr()}) = ?")
        params.append(cat)
    if favorited is True:
        where.append("favorited = 1")
    elif favorited is False:
        where.append("favorited = 0")
    sql_where = f"WHERE {' AND '.join(where)}" if where else ""
    return sql_where, params


def list_cards(
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    category: str = "",
    favorited: Optional[bool] = None,
) -> Dict[str, Any]:
    init_db()
    pg = max(1, int(page or 1))
    size = max(1, min(int(page_size or 20), 100))
    offset = (pg - 1) * size
    sql_where, params = _build_list_query(
        keyword=keyword, category=category, favorited=favorited
    )
    with connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM tweet_cards {sql_where}",
            params,
        ).fetchone()["c"]
        rows = conn.execute(
            f"""
            SELECT * FROM tweet_cards
            {sql_where}
            ORDER BY favorited DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, size, offset],
        ).fetchall()
    items = [_row_to_card(r) for r in rows]
    pages = max(1, (int(total) + size - 1) // size) if total else 1
    return {
        "items": items,
        "total": int(total),
        "page": pg,
        "page_size": size,
        "pages": pages,
        "has_prev": pg > 1,
        "has_next": pg < pages,
    }


def list_categories() -> List[str]:
    init_db()
    expr = _effective_category_expr()
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT DISTINCT {expr} AS cat
            FROM tweet_cards
            WHERE {expr} != ''
            ORDER BY cat COLLATE NOCASE
            """
        ).fetchall()
    return [str(r["cat"]) for r in rows if r["cat"]]


def update_card(tweet_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    init_db()
    tid = str(tweet_id or "").strip()
    if not tid:
        return None
    sets: List[str] = []
    params: List[Any] = []
    if "favorited" in fields:
        sets.append("favorited = ?")
        params.append(1 if fields["favorited"] else 0)
    if "user_category" in fields:
        sets.append("user_category = ?")
        params.append(str(fields.get("user_category") or "").strip())
    if not sets:
        return get_card(tid)
    sets.append("updated_at = ?")
    params.append(_now())
    params.append(tid)
    with connect() as conn:
        cur = conn.execute(
            f"UPDATE tweet_cards SET {', '.join(sets)} WHERE tweet_id = ?",
            params,
        )
        if cur.rowcount <= 0:
            return None
        row = conn.execute(
            "SELECT * FROM tweet_cards WHERE tweet_id=?", (tid,)
        ).fetchone()
    return _row_to_card(row) if row else None


def delete_card(tweet_id: str) -> bool:
    init_db()
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM tweet_cards WHERE tweet_id=?",
            (str(tweet_id).strip(),),
        )
        return cur.rowcount > 0


def stats() -> Dict[str, Any]:
    init_db()
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM tweet_cards").fetchone()["c"]
        favorited = conn.execute(
            "SELECT COUNT(*) AS c FROM tweet_cards WHERE favorited = 1"
        ).fetchone()["c"]
    return {
        "total": total,
        "favorited": favorited,
        "db": str(DB_PATH).replace("\\", "/"),
    }
