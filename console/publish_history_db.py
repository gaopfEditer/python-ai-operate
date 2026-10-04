# coding=utf-8
"""CDP 发布历史：正文 + 图片落盘 + SQLite 索引。"""

from __future__ import annotations

import json
import shutil
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HISTORY_ROOT = PROJECT_ROOT / "output" / "publish_history"
DB_PATH = PROJECT_ROOT / "output" / "publish_history.db"
_LOCK = threading.RLock()
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _resolve_publish_debugger_url(raw: Any) -> str:
    from utils.crawl_cdp import resolve_publish_debugger_url

    s = str(raw or "").strip()
    return resolve_publish_debugger_url(s or None)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    HISTORY_ROOT.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> Path:
    with _LOCK:
        with connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS publish_history (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    platforms_json TEXT NOT NULL DEFAULT '[]',
                    media_rels_json TEXT NOT NULL DEFAULT '[]',
                    media_paths_json TEXT NOT NULL DEFAULT '[]',
                    debugger_url TEXT NOT NULL DEFAULT '',
                    submit INTEGER NOT NULL DEFAULT 1,
                    job_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    success_count INTEGER NOT NULL DEFAULT 0,
                    total_count INTEGER NOT NULL DEFAULT 0,
                    results_json TEXT NOT NULL DEFAULT '[]',
                    message TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_publish_history_created
                    ON publish_history(created_at DESC)
                """
            )
            conn.commit()
            _migrate(conn)
    return DB_PATH


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(publish_history)").fetchall()}
    if "entry_kind" not in cols:
        conn.execute(
            "ALTER TABLE publish_history ADD COLUMN entry_kind TEXT NOT NULL DEFAULT 'run'"
        )
    if "tags" not in cols:
        conn.execute("ALTER TABLE publish_history ADD COLUMN tags TEXT NOT NULL DEFAULT ''")
    if "series_note" not in cols:
        conn.execute(
            "ALTER TABLE publish_history ADD COLUMN series_note TEXT NOT NULL DEFAULT ''"
        )
    if "scheduled_at" not in cols:
        conn.execute(
            "ALTER TABLE publish_history ADD COLUMN scheduled_at TEXT NOT NULL DEFAULT ''"
        )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_publish_history_kind
            ON publish_history(entry_kind, created_at DESC)
        """
    )
    conn.commit()


def _loads(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


def _row_to_item(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    platforms = _loads(d.pop("platforms_json", "[]"), [])
    media_rels = _loads(d.pop("media_rels_json", "[]"), [])
    media_paths = _loads(d.pop("media_paths_json", "[]"), [])
    results = _loads(d.pop("results_json", "[]"), [])
    content = str(d.get("content") or "")
    snippet = content.replace("\n", " ").strip()[:160]
    d["platforms"] = platforms
    d["media_rels"] = media_rels
    d["media_paths"] = media_paths
    d["results"] = results
    d["submit"] = bool(int(d.get("submit") or 0))
    d["entry_kind"] = str(d.get("entry_kind") or "run").strip() or "run"
    d["tags"] = str(d.get("tags") or "")
    d["series_note"] = str(d.get("series_note") or "")
    d["scheduled_at"] = str(d.get("scheduled_at") or "")
    d["source"] = "archive"
    d["snippet"] = snippet
    return d


def _copy_media(record_id: str, media_paths: List[str]) -> tuple[List[str], List[str]]:
    """复制媒体到 history 目录，返回 (绝对路径列表, 相对 rel 列表)。"""
    media_dir = HISTORY_ROOT / record_id / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    abs_out: List[str] = []
    rel_out: List[str] = []
    idx = 1
    for src in media_paths or []:
        src_path = Path(str(src)).expanduser()
        if not src_path.is_file():
            continue
        try:
            if src_path.resolve().parent == media_dir.resolve():
                rel = f"{record_id}/media/{src_path.name}"
                abs_out.append(str(src_path.resolve()))
                rel_out.append(rel)
                continue
        except Exception:
            pass
        ext = src_path.suffix.lower() or ".jpg"
        name = f"{idx:02d}{ext}"
        dest = media_dir / name
        shutil.copy2(src_path, dest)
        rel = f"{record_id}/media/{name}"
        abs_out.append(str(dest.resolve()))
        rel_out.append(rel)
        idx += 1
    return abs_out, rel_out


def _insert_entry(
    *,
    entry_kind: str,
    title: str = "",
    content: str = "",
    platforms: Optional[List[str]] = None,
    media_paths: Optional[List[str]] = None,
    debugger_url: str = "",
    submit: bool = True,
    job_id: str = "",
    status: str = "",
    success_count: int = 0,
    total_count: int = 0,
    results: Optional[List[Dict[str, Any]]] = None,
    message: str = "",
    tags: str = "",
    series_note: str = "",
    scheduled_at: str = "",
    record_id: Optional[str] = None,
) -> Dict[str, Any]:
    init_db()
    rid = str(record_id or "").strip() or uuid.uuid4().hex[:12]
    abs_paths, rels = _copy_media(rid, list(media_paths or []))
    now = _now()
    kind = str(entry_kind or "run").strip() or "run"
    with _LOCK:
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO publish_history (
                    id, title, content, platforms_json, media_rels_json, media_paths_json,
                    debugger_url, submit, job_id, status, success_count, total_count,
                    results_json, message, created_at,
                    entry_kind, tags, series_note, scheduled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rid,
                    str(title or "").strip(),
                    str(content or ""),
                    json.dumps(list(platforms or []), ensure_ascii=False),
                    json.dumps(rels, ensure_ascii=False),
                    json.dumps(abs_paths, ensure_ascii=False),
                    str(debugger_url or "").strip(),
                    1 if submit else 0,
                    str(job_id or ""),
                    str(status or ""),
                    int(success_count or 0),
                    int(total_count or 0),
                    json.dumps(results or [], ensure_ascii=False),
                    str(message or "")[:500],
                    now,
                    kind,
                    str(tags or ""),
                    str(series_note or ""),
                    str(scheduled_at or ""),
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM publish_history WHERE id=?", (rid,)).fetchone()
    return _row_to_item(row) if row else {"id": rid}


def save_draft_from_body(body: Dict[str, Any]) -> Dict[str, Any]:
    """存草稿：与发布记录同一库、同一目录。"""
    from console.app import _publish_queue_module

    pq = _publish_queue_module()
    media_paths = pq.resolve_publish_media(body)
    content = str(body.get("content") or body.get("text") or "").strip()
    if not content and not media_paths:
        raise ValueError("正文与图片不能同时为空")
    platforms = body.get("platforms") or []
    if isinstance(platforms, str):
        platforms = [p.strip() for p in platforms.split(",") if p.strip()]
    series_note = str(body.get("series_note") or body.get("series") or "").strip()
    tags = str(body.get("tags") or "").strip()
    if series_note and series_note not in tags:
        tags = f"{tags} · {series_note}".strip(" ·") if tags else series_note
    scheduled = str(body.get("scheduled_at") or body.get("schedule_at") or "").strip()
    return _insert_entry(
        entry_kind="draft",
        title=str(body.get("title") or "").strip(),
        content=content,
        platforms=[str(p) for p in platforms if str(p).strip()],
        media_paths=media_paths,
        debugger_url=_resolve_publish_debugger_url(body.get("debugger_url")),
        submit=bool(body.get("submit", True)),
        status="draft",
        tags=tags,
        series_note=series_note,
        scheduled_at=scheduled,
    )


def record_publish(
    *,
    title: str = "",
    content: str = "",
    platforms: Optional[List[str]] = None,
    media_paths: Optional[List[str]] = None,
    debugger_url: str = "",
    submit: bool = True,
    job_id: str = "",
    status: str = "",
    success_count: int = 0,
    total_count: int = 0,
    results: Optional[List[Dict[str, Any]]] = None,
    message: str = "",
) -> Dict[str, Any]:
    return _insert_entry(
        entry_kind="run",
        title=title,
        content=content,
        platforms=platforms,
        media_paths=media_paths,
        debugger_url=debugger_url,
        submit=submit,
        job_id=job_id,
        status=status,
        success_count=success_count,
        total_count=total_count,
        results=results,
        message=message,
    )


def _legacy_queue_drafts() -> List[Dict[str, Any]]:
    """旧版队列里的 draft 条目，合并展示直至用户删除。"""
    try:
        from console.app import _publish_queue_module

        pq = _publish_queue_module()
        rows = pq.list_items(include_done=False, include_draft=True)
        out: List[Dict[str, Any]] = []
        for it in rows:
            if str(it.get("status") or "") != "draft":
                continue
            content = str(it.get("content") or "")
            out.append(
                {
                    "id": it.get("id"),
                    "title": it.get("title") or "",
                    "content": content,
                    "platforms": list(it.get("platforms") or []),
                    "media_rels": list(it.get("media_rels") or []),
                    "media_paths": list(it.get("media_paths") or []),
                    "debugger_url": it.get("debugger_url") or "",
                    "submit": True,
                    "entry_kind": "draft",
                    "status": "draft",
                    "tags": it.get("tags") or "",
                    "series_note": it.get("series_note") or "",
                    "scheduled_at": it.get("scheduled_at") or "",
                    "created_at": it.get("created_at") or it.get("updated_at") or "",
                    "snippet": it.get("snippet") or content[:160],
                    "source": "queue",
                    "storage_rel": it.get("storage_rel") or "",
                }
            )
        return out
    except Exception:
        return []


def list_history(
    *,
    page: int = 1,
    page_size: int = 20,
    kind: str = "all",
) -> Dict[str, Any]:
    """草稿 + 发布记录统一列表（kind: all | draft | run）。"""
    init_db()
    pg = max(1, int(page or 1))
    size = max(1, min(int(page_size or 20), 60))
    filt = (kind or "all").strip().lower()
    with _LOCK:
        with connect() as conn:
            where = ""
            params: List[Any] = []
            if filt == "draft":
                where = "WHERE entry_kind = 'draft'"
            elif filt == "run":
                where = "WHERE entry_kind = 'run'"
            rows = conn.execute(
                f"""
                SELECT * FROM publish_history
                {where}
                ORDER BY created_at DESC, id DESC
                """,
                params,
            ).fetchall()
    items = [_row_to_item(r) for r in rows]
    seen = {str(it.get("id") or "") for it in items}
    if filt in ("all", "draft"):
        for leg in _legacy_queue_drafts():
            lid = str(leg.get("id") or "")
            if lid and lid not in seen:
                items.append(leg)
                seen.add(lid)
    items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    total = len(items)
    offset = (pg - 1) * size
    page_items = items[offset : offset + size]
    pages = max(1, (total + size - 1) // size) if total else 1
    draft_n = sum(1 for it in items if it.get("entry_kind") == "draft")
    run_n = sum(1 for it in items if it.get("entry_kind") == "run")
    return {
        "items": page_items,
        "total": total,
        "page": pg,
        "page_size": size,
        "pages": pages,
        "stats": {"draft": draft_n, "run": run_n, "all": total},
    }


def get_history(record_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    rid = str(record_id or "").strip()
    if not rid:
        return None
    with _LOCK:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM publish_history WHERE id=?", (rid,)
            ).fetchone()
    return _row_to_item(row) if row else None


def delete_history(record_id: str) -> bool:
    init_db()
    rid = str(record_id or "").strip()
    if not rid:
        return False
    with _LOCK:
        with connect() as conn:
            cur = conn.execute("DELETE FROM publish_history WHERE id=?", (rid,))
            conn.commit()
            deleted = cur.rowcount > 0
    if deleted:
        folder = HISTORY_ROOT / rid
        if folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)
    return deleted


def resolve_history_path(rel: str) -> Path:
    rel = str(rel or "").strip().lstrip("/").replace("\\", "/")
    if not rel or ".." in rel.split("/"):
        raise ValueError("非法路径")
    root = HISTORY_ROOT.resolve()
    full = (HISTORY_ROOT / rel).resolve()
    if full != root and root not in full.parents:
        raise ValueError("路径越界")
    return full
