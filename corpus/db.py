# coding=utf-8
"""
SQLite 语料库 CRUD。

表：
- templates：拆解后的梗骨架 / 元数据
- generations：基于模板再生成的内容与取材路径
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "output" / "corpus.db"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def _json_loads(raw: Any, default: Any = None) -> Any:
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
def connect(db_path: Optional[Path] = None):
    path = Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None) -> Path:
    path = Path(db_path or DEFAULT_DB_PATH)
    with connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_platform TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                source_key TEXT NOT NULL DEFAULT '',
                source_title TEXT NOT NULL DEFAULT '',
                raw_text TEXT NOT NULL DEFAULT '',
                pattern TEXT NOT NULL DEFAULT '',
                emotion TEXT NOT NULL DEFAULT '',
                tension TEXT NOT NULL DEFAULT '',
                keywords TEXT NOT NULL DEFAULT '[]',
                hooks TEXT NOT NULL DEFAULT '',
                weight REAL NOT NULL DEFAULT 1.0,
                quality TEXT NOT NULL DEFAULT 'unrated',
                tags TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'active',
                provenance TEXT NOT NULL DEFAULT '{}',
                factors_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(source_platform, source_key)
            );

            CREATE INDEX IF NOT EXISTS idx_templates_emotion
                ON templates(emotion);
            CREATE INDEX IF NOT EXISTS idx_templates_status
                ON templates(status);
            CREATE INDEX IF NOT EXISTS idx_templates_quality
                ON templates(quality);
            CREATE INDEX IF NOT EXISTS idx_templates_updated
                ON templates(updated_at);

            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER,
                topic TEXT NOT NULL DEFAULT '',
                platform_style TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                path_json TEXT NOT NULL DEFAULT '{}',
                meta_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(template_id) REFERENCES templates(id)
            );

            CREATE INDEX IF NOT EXISTS idx_generations_template
                ON generations(template_id);
            CREATE INDEX IF NOT EXISTS idx_generations_created
                ON generations(created_at);

            CREATE TABLE IF NOT EXISTS template_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER NOT NULL,
                snapshot_json TEXT NOT NULL DEFAULT '{}',
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(template_id) REFERENCES templates(id)
            );
            CREATE INDEX IF NOT EXISTS idx_template_history_tid
                ON template_history(template_id);
            CREATE INDEX IF NOT EXISTS idx_template_history_created
                ON template_history(created_at);
            """
        )
    return path


def _row_to_template(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["keywords"] = _json_loads(d.get("keywords"), [])
    d["tags"] = _json_loads(d.get("tags"), [])
    d["provenance"] = _json_loads(d.get("provenance"), {})
    d["factors"] = _json_loads(d.get("factors_json"), {})
    d.pop("factors_json", None)
    return d


def _row_to_generation(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["path"] = _json_loads(d.get("path_json"), {})
    d["meta"] = _json_loads(d.get("meta_json"), {})
    d.pop("path_json", None)
    d.pop("meta_json", None)
    return d


def create_template(
    *,
    source_platform: str = "",
    source_url: str = "",
    source_key: str = "",
    source_title: str = "",
    raw_text: str = "",
    pattern: str = "",
    emotion: str = "",
    tension: str = "",
    keywords: Optional[Iterable[str]] = None,
    hooks: str = "",
    weight: float = 1.0,
    quality: str = "unrated",
    tags: Optional[Iterable[str]] = None,
    status: str = "active",
    provenance: Optional[Dict[str, Any]] = None,
    factors: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    init_db(db_path)
    now = _now()
    key = (source_key or source_url or source_title or now).strip()
    platform = (source_platform or "unknown").strip()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO templates (
                source_platform, source_url, source_key, source_title, raw_text,
                pattern, emotion, tension, keywords, hooks,
                weight, quality, tags, status, provenance, factors_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_platform, source_key) DO UPDATE SET
                source_url=excluded.source_url,
                source_title=excluded.source_title,
                raw_text=excluded.raw_text,
                pattern=excluded.pattern,
                emotion=excluded.emotion,
                tension=excluded.tension,
                keywords=excluded.keywords,
                hooks=excluded.hooks,
                weight=excluded.weight,
                quality=excluded.quality,
                tags=excluded.tags,
                status=excluded.status,
                provenance=excluded.provenance,
                factors_json=excluded.factors_json,
                updated_at=excluded.updated_at
            """,
            (
                platform,
                source_url or "",
                key,
                source_title or "",
                raw_text or "",
                pattern or "",
                emotion or "",
                tension or "",
                _json_dumps(list(keywords or [])),
                hooks or "",
                float(weight or 1.0),
                quality or "unrated",
                _json_dumps(list(tags or [])),
                status or "active",
                _json_dumps(provenance or {}),
                _json_dumps(factors or {}),
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM templates WHERE source_platform=? AND source_key=?",
            (platform, key),
        ).fetchone()
    return _row_to_template(row)


def get_template(template_id: int, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM templates WHERE id=?", (int(template_id),)
        ).fetchone()
    return _row_to_template(row) if row else None


def list_templates(
    *,
    emotion: str = "",
    tag: str = "",
    quality: str = "",
    status: str = "active",
    keyword: str = "",
    platform: str = "",
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    init_db(db_path)
    clauses: List[str] = []
    args: List[Any] = []
    if status:
        clauses.append("status=?")
        args.append(status)
    if emotion:
        clauses.append("emotion LIKE ?")
        args.append(f"%{emotion.strip()}%")
    if quality:
        clauses.append("quality=?")
        args.append(quality)
    if platform:
        clauses.append("source_platform=?")
        args.append(platform)
    if keyword:
        kw = f"%{keyword.strip()}%"
        clauses.append(
            "(pattern LIKE ? OR source_title LIKE ? OR raw_text LIKE ? OR keywords LIKE ? OR tension LIKE ?)"
        )
        args.extend([kw, kw, kw, kw, kw])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = (
        f"SELECT * FROM templates{where} "
        "ORDER BY weight DESC, updated_at DESC LIMIT ? OFFSET ?"
    )
    args.extend([max(1, int(limit)), max(0, int(offset))])
    with connect(db_path) as conn:
        rows = conn.execute(sql, args).fetchall()
    items = [_row_to_template(r) for r in rows]
    if tag:
        tag_l = tag.strip().lower()
        items = [
            it
            for it in items
            if tag_l in [str(t).lower() for t in (it.get("tags") or [])]
        ]
    return items


def snapshot_template(
    template_id: int,
    *,
    reason: str = "update",
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """写入模板历史快照，用于留存与回滚。"""
    cur = get_template(template_id, db_path=db_path)
    if not cur:
        return None
    now = _now()
    with connect(db_path) as conn:
        cur_ins = conn.execute(
            """
            INSERT INTO template_history (template_id, snapshot_json, reason, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (int(template_id), _json_dumps(cur), reason or "update", now),
        )
        hid = cur_ins.lastrowid
    return {"id": hid, "template_id": int(template_id), "reason": reason, "created_at": now, "snapshot": cur}


def list_template_history(
    template_id: int,
    *,
    limit: int = 30,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, template_id, snapshot_json, reason, created_at
            FROM template_history
            WHERE template_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(template_id), max(1, int(limit))),
        ).fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["snapshot"] = _json_loads(d.pop("snapshot_json", None), {})
        out.append(d)
    return out


def get_templates_by_ids(
    ids: Iterable[int],
    *,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    init_db(db_path)
    id_list = [int(x) for x in ids if x is not None]
    if not id_list:
        return []
    placeholders = ",".join("?" for _ in id_list)
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM templates WHERE id IN ({placeholders}) AND status!='deleted'",
            id_list,
        ).fetchall()
    by_id = {_row_to_template(r)["id"]: _row_to_template(r) for r in rows}
    # 保持入参顺序
    return [by_id[i] for i in id_list if i in by_id]


def update_template(
    template_id: int,
    fields: Dict[str, Any],
    db_path: Optional[Path] = None,
    *,
    keep_history: bool = True,
    history_reason: str = "update",
) -> Optional[Dict[str, Any]]:
    init_db(db_path)
    if keep_history and fields:
        snapshot_template(template_id, reason=history_reason, db_path=db_path)
    allowed = {
        "source_title",
        "raw_text",
        "pattern",
        "emotion",
        "tension",
        "hooks",
        "weight",
        "quality",
        "status",
        "source_url",
        "source_platform",
        "source_key",
    }
    sets: List[str] = []
    args: List[Any] = []
    for k, v in (fields or {}).items():
        if k == "keywords":
            sets.append("keywords=?")
            args.append(_json_dumps(v if isinstance(v, list) else [v]))
        elif k == "tags":
            sets.append("tags=?")
            args.append(_json_dumps(v if isinstance(v, list) else [v]))
        elif k == "provenance":
            sets.append("provenance=?")
            args.append(_json_dumps(v if isinstance(v, dict) else {}))
        elif k in ("factors", "factors_json"):
            sets.append("factors_json=?")
            args.append(_json_dumps(v if isinstance(v, dict) else {}))
        elif k in allowed:
            sets.append(f"{k}=?")
            args.append(v)
    if not sets:
        return get_template(template_id, db_path=db_path)
    sets.append("updated_at=?")
    args.append(_now())
    args.append(int(template_id))
    with connect(db_path) as conn:
        conn.execute(
            f"UPDATE templates SET {', '.join(sets)} WHERE id=?",
            args,
        )
    return get_template(template_id, db_path=db_path)


def archive_template(template_id: int, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    return update_template(template_id, {"status": "archived"}, db_path=db_path)


def delete_template(template_id: int, hard: bool = False, db_path: Optional[Path] = None) -> bool:
    init_db(db_path)
    with connect(db_path) as conn:
        if hard:
            cur = conn.execute("DELETE FROM templates WHERE id=?", (int(template_id),))
        else:
            cur = conn.execute(
                "UPDATE templates SET status=?, updated_at=? WHERE id=?",
                ("deleted", _now(), int(template_id)),
            )
        return cur.rowcount > 0


def stats(db_path: Optional[Path] = None) -> Dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM templates WHERE status!='deleted'"
        ).fetchone()["c"]
        active = conn.execute(
            "SELECT COUNT(*) AS c FROM templates WHERE status='active'"
        ).fetchone()["c"]
        archived = conn.execute(
            "SELECT COUNT(*) AS c FROM templates WHERE status='archived'"
        ).fetchone()["c"]
        good = conn.execute(
            "SELECT COUNT(*) AS c FROM templates WHERE quality='good' AND status!='deleted'"
        ).fetchone()["c"]
        generations = conn.execute("SELECT COUNT(*) AS c FROM generations").fetchone()["c"]
        emotions = conn.execute(
            """
            SELECT emotion AS name, COUNT(*) AS count
            FROM templates
            WHERE status='active' AND emotion!=''
            GROUP BY emotion
            ORDER BY count DESC
            LIMIT 20
            """
        ).fetchall()
    return {
        "total": total,
        "active": active,
        "archived": archived,
        "good": good,
        "generations": generations,
        "emotions": [dict(r) for r in emotions],
    }


def create_generation(
    *,
    template_id: Optional[int],
    topic: str,
    content: str,
    platform_style: str = "",
    path: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    init_db(db_path)
    now = _now()
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO generations (
                template_id, topic, platform_style, content, path_json, meta_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(template_id) if template_id is not None else None,
                topic or "",
                platform_style or "",
                content or "",
                _json_dumps(path or {}),
                _json_dumps(meta or {}),
                now,
            ),
        )
        gid = cur.lastrowid
        row = conn.execute("SELECT * FROM generations WHERE id=?", (gid,)).fetchone()
    return _row_to_generation(row)


def get_generation(generation_id: int, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM generations WHERE id=?", (int(generation_id),)
        ).fetchone()
    return _row_to_generation(row) if row else None


def update_generation(
    generation_id: int,
    *,
    content: Optional[str] = None,
    platform_style: Optional[str] = None,
    path: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
    merge_meta: bool = True,
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """更新 generation；默认把 meta 与原有合并。"""
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM generations WHERE id=?", (int(generation_id),)
        ).fetchone()
        if not row:
            return None
        cur_meta = _json_loads(row["meta_json"], {})
        if not isinstance(cur_meta, dict):
            cur_meta = {}
        new_meta = cur_meta
        if meta is not None:
            new_meta = {**cur_meta, **meta} if merge_meta else dict(meta)
        sets: List[str] = []
        args: List[Any] = []
        if content is not None:
            sets.append("content=?")
            args.append(content)
        if platform_style is not None:
            sets.append("platform_style=?")
            args.append(platform_style)
        if path is not None:
            sets.append("path_json=?")
            args.append(_json_dumps(path))
        if meta is not None:
            sets.append("meta_json=?")
            args.append(_json_dumps(new_meta))
        if not sets:
            return _row_to_generation(row)
        args.append(int(generation_id))
        conn.execute(
            f"UPDATE generations SET {', '.join(sets)} WHERE id=?",
            args,
        )
        row = conn.execute(
            "SELECT * FROM generations WHERE id=?", (int(generation_id),)
        ).fetchone()
    return _row_to_generation(row) if row else None


def list_generations(
    *,
    template_id: Optional[int] = None,
    featured_only: bool = False,
    limit: int = 30,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    init_db(db_path)
    lim = max(1, int(limit))
    with connect(db_path) as conn:
        clauses: List[str] = []
        args: List[Any] = []
        if template_id is not None:
            clauses.append("template_id=?")
            args.append(int(template_id))
        if featured_only:
            # SQLite json_extract：true / 1 / "true"
            clauses.append(
                "("
                "json_extract(meta_json, '$.featured') = 1 "
                "OR lower(coalesce(json_extract(meta_json, '$.featured'), '')) = 'true' "
                "OR platform_style = 'featured'"
                ")"
            )
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        args.append(lim)
        rows = conn.execute(
            f"SELECT * FROM generations{where} ORDER BY id DESC LIMIT ?",
            args,
        ).fetchall()
    return [_row_to_generation(r) for r in rows]
