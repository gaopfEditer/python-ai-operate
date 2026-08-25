# coding=utf-8
"""CDP 定时发布队列：图文上传缓存（按月目录）+ 到点自动发布。"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

QUEUE_PATH: Optional[Path] = None
CACHE_ROOT: Optional[Path] = None
_LOCK = threading.RLock()
_ITEMS: Dict[str, Dict[str, Any]] = {}
_SCHEDULER_STOP = threading.Event()
_SCHEDULER_THREAD: Optional[threading.Thread] = None
_PUBLISH_LOCK = threading.Lock()

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v"}
_MEDIA_EXTS = _IMAGE_EXTS | _VIDEO_EXTS
_MAX_UPLOAD_FILES = 12
_MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def init(queue_path: Path, cache_root: Optional[Path] = None) -> int:
    global QUEUE_PATH, CACHE_ROOT
    QUEUE_PATH = Path(queue_path)
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_ROOT = Path(cache_root) if cache_root else (QUEUE_PATH.parent / "publish_cache")
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    n = _load()
    _ensure_scheduler()
    return n


def cache_root() -> Path:
    if CACHE_ROOT is None:
        raise RuntimeError("发布缓存未初始化")
    return CACHE_ROOT


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_when(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", s):
        s = s + ":00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                dt = None  # type: ignore
        else:
            return None
        if dt is None:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.isoformat(timespec="seconds")


def _month_key(dt: Optional[datetime] = None) -> str:
    d = dt or datetime.now()
    return d.strftime("%Y-%m")


def _safe_filename(name: str, fallback: str = "file") -> str:
    base = Path(str(name or fallback)).name
    base = re.sub(r"[^\w.\u4e00-\u9fff\-]+", "_", base).strip("._")
    if not base:
        base = fallback
    return base[:120]


def _normalize_media(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = re.split(r"[\n,;]+", raw)
        return [p.strip() for p in parts if p.strip()]
    if isinstance(raw, list):
        out: List[str] = []
        for x in raw:
            out.extend(_normalize_media(x))
        return out
    return []


def _normalize_platforms(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [p.strip() for p in re.split(r"[,，;；|\s]+", raw) if p.strip()]
    if isinstance(raw, list):
        return [str(p).strip() for p in raw if str(p).strip()]
    return []


def _decode_upload_files(raw: Any) -> List[Tuple[str, bytes]]:
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ValueError("media_files 须为数组")
    out: List[Tuple[str, bytes]] = []
    for i, row in enumerate(raw):
        if i >= _MAX_UPLOAD_FILES:
            break
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("filename") or f"upload_{i + 1}").strip()
        b64 = row.get("data_b64") or row.get("content_base64") or row.get("data") or ""
        if isinstance(b64, str) and "," in b64 and b64.strip().startswith("data:"):
            b64 = b64.split(",", 1)[1]
        if not b64:
            continue
        try:
            data = base64.b64decode(b64, validate=False)
        except Exception as e:
            raise ValueError(f"无法解码上传文件 {name}: {e}") from e
        if len(data) > _MAX_UPLOAD_BYTES:
            raise ValueError(f"文件过大（>{_MAX_UPLOAD_BYTES // (1024 * 1024)}MB）: {name}")
        ext = Path(name).suffix.lower()
        if ext and ext not in _MEDIA_EXTS:
            mime = str(row.get("type") or row.get("mime") or "").lower()
            if "png" in mime:
                name += ".png"
            elif "jpeg" in mime or "jpg" in mime:
                name += ".jpg"
            elif "gif" in mime:
                name += ".gif"
            elif "webp" in mime:
                name += ".webp"
            elif "mp4" in mime:
                name += ".mp4"
            else:
                name += ".jpg"
        elif not ext:
            name += ".jpg"
        out.append((_safe_filename(name), data))
    return out


def _write_content_md(dir_path: Path, title: str, content: str, meta: Dict[str, Any]) -> Path:
    lines = []
    if title:
        lines.append(f"# {title}")
        lines.append("")
    lines.append(content or "")
    lines.append("")
    lines.append("---")
    lines.append(f"id: {meta.get('id', '')}")
    lines.append(f"platforms: {', '.join(meta.get('platforms') or [])}")
    if meta.get("scheduled_at"):
        lines.append(f"scheduled_at: {meta.get('scheduled_at')}")
    if meta.get("tags"):
        lines.append(f"tags: {meta.get('tags')}")
    lines.append(f"created_at: {meta.get('created_at', '')}")
    path = dir_path / "content.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def resolve_publish_media(body: dict) -> List[str]:
    """合并 media_paths 与浏览器上传 media_files，供即时 CDP 发布使用。"""
    path_sources = _normalize_media(body.get("media_paths") or body.get("media") or [])
    uploads = _decode_upload_files(body.get("media_files"))
    if not uploads:
        return path_sources
    tmp = cache_root() / "_instant" / uuid.uuid4().hex[:12]
    tmp.mkdir(parents=True, exist_ok=True)
    return _materialize_media(tmp / "media", path_sources=path_sources, uploads=uploads)


def _materialize_media(
    media_dir: Path,
    *,
    path_sources: List[str],
    uploads: List[Tuple[str, bytes]],
) -> List[str]:
    media_dir.mkdir(parents=True, exist_ok=True)
    saved: List[str] = []
    existing = [p for p in media_dir.iterdir() if p.is_file()] if media_dir.exists() else []
    idx = len(existing) + 1

    for src in path_sources:
        src_path = Path(src).expanduser()
        if not src_path.is_file():
            logger.warning("媒体不存在，跳过: %s", src)
            continue
        # 已在目标目录则跳过复制
        try:
            if src_path.resolve().parent == media_dir.resolve():
                saved.append(str(src_path.resolve()))
                continue
        except Exception:
            pass
        name = f"{idx:02d}_{_safe_filename(src_path.name)}"
        dest = media_dir / name
        shutil.copy2(src_path, dest)
        saved.append(str(dest.resolve()))
        idx += 1

    for fname, data in uploads:
        name = f"{idx:02d}_{_safe_filename(fname)}"
        dest = media_dir / name
        dest.write_bytes(data)
        saved.append(str(dest.resolve()))
        idx += 1

    return saved


def _scan_media(storage_dir: str) -> List[str]:
    media_dir = Path(storage_dir) / "media"
    if not media_dir.is_dir():
        return []
    return sorted(
        str(p.resolve())
        for p in media_dir.iterdir()
        if p.is_file() and p.suffix.lower() in _MEDIA_EXTS
    )


def _alloc_storage_dir(item_id: str, when_iso: Optional[str] = None) -> Tuple[str, Path]:
    root = cache_root()
    dt = datetime.now()
    if when_iso:
        try:
            dt = datetime.fromisoformat(when_iso)
        except ValueError:
            pass
    month = _month_key(dt)
    folder = f"{dt.strftime('%Y%m%d_%H%M%S')}_{item_id}"
    rel = f"{month}/{folder}"
    abs_dir = root / month / folder
    abs_dir.mkdir(parents=True, exist_ok=True)
    (abs_dir / "media").mkdir(exist_ok=True)
    return rel, abs_dir


def _save_bundle_files(item: Dict[str, Any]) -> None:
    rel = item.get("storage_rel") or ""
    if not rel:
        rel, abs_dir = _alloc_storage_dir(
            item["id"], item.get("scheduled_at") or item.get("created_at")
        )
        item["storage_rel"] = rel
        item["storage_dir"] = str(abs_dir)
        item["month"] = rel.split("/", 1)[0]
    else:
        abs_dir = cache_root() / rel
        abs_dir.mkdir(parents=True, exist_ok=True)
        (abs_dir / "media").mkdir(exist_ok=True)
        item["storage_dir"] = str(abs_dir)
        item["month"] = rel.split("/", 1)[0]

    abs_path = Path(item["storage_dir"])
    _write_content_md(
        abs_path,
        item.get("title") or "",
        item.get("content") or "",
        item,
    )
    meta_path = abs_path / "meta.json"
    public = {k: v for k, v in item.items() if not str(k).startswith("_")}
    meta_path.write_text(
        json.dumps(public, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def save_draft(body: Dict[str, Any], *, enqueue: bool = False) -> Dict[str, Any]:
    title = str(body.get("title") or "").strip()
    content = str(body.get("content") or body.get("text") or "").strip()
    path_media = _normalize_media(body.get("media_paths") or body.get("media"))
    uploads = _decode_upload_files(body.get("media_files"))
    if not content and not path_media and not uploads:
        raise ValueError("正文与图片不能同时为空")

    scheduled = _parse_when(body.get("scheduled_at") or body.get("schedule_at"))
    if enqueue and not scheduled:
        raise ValueError("加入定时队列需设置预约时间")

    platforms = _normalize_platforms(body.get("platforms")) or ["x", "binance_square"]
    item_id = str(body.get("id") or "").strip() or uuid.uuid4().hex[:10]
    now = _now_iso()
    status = "pending" if enqueue else "draft"

    rel, abs_dir = _alloc_storage_dir(item_id, scheduled or now)
    media_paths = _materialize_media(
        abs_dir / "media",
        path_sources=path_media,
        uploads=uploads,
    )

    item = {
        "id": item_id,
        "title": title,
        "content": content,
        "media_paths": media_paths,
        "platforms": platforms,
        "tags": str(body.get("tags") or "").strip(),
        "scheduled_at": scheduled or "",
        "status": status,
        "enabled": bool(body.get("enabled", True)) if enqueue else False,
        "use_cdp": bool(body.get("use_cdp", True)),
        "debugger_url": str(body.get("debugger_url") or "127.0.0.1:9222").strip()
        or "127.0.0.1:9222",
        "created_at": now,
        "updated_at": now,
        "published_at": None,
        "last_error": "",
        "last_result": None,
        "storage_rel": rel,
        "storage_dir": str(abs_dir),
        "month": rel.split("/", 1)[0],
    }
    _save_bundle_files(item)

    with _LOCK:
        if enqueue:
            active_n = sum(1 for i in _ITEMS.values() if i.get("status") not in ("draft", "done", "cancelled"))
            if active_n >= 100:
                raise ValueError("队列已满（最多 100 条），请先清理已完成项")
        _ITEMS[item_id] = item
        _persist()

    return _public_item(item)


def _public_item(item: Dict[str, Any]) -> Dict[str, Any]:
    media = list(item.get("media_paths") or [])
    rels = []
    for p in media:
        try:
            rp = Path(p)
            if CACHE_ROOT:
                try:
                    rels.append(str(rp.resolve().relative_to(cache_root().resolve())))
                except Exception:
                    rels.append(rp.name)
            else:
                rels.append(rp.name)
        except Exception:
            rels.append(str(p))
    return {
        "id": item.get("id"),
        "title": item.get("title") or "",
        "content": item.get("content") or "",
        "media_paths": media,
        "media_rels": rels,
        "media_count": len(media),
        "platforms": list(item.get("platforms") or []),
        "tags": item.get("tags") or "",
        "scheduled_at": item.get("scheduled_at") or "",
        "status": item.get("status") or "pending",
        "enabled": bool(item.get("enabled", True)),
        "use_cdp": bool(item.get("use_cdp", True)),
        "debugger_url": item.get("debugger_url") or "127.0.0.1:9222",
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "published_at": item.get("published_at"),
        "last_error": item.get("last_error") or "",
        "last_result": item.get("last_result"),
        "snippet": _snippet(item),
        "month": item.get("month") or "",
        "storage_rel": item.get("storage_rel") or "",
        "storage_dir": item.get("storage_dir") or "",
        "content_md": (
            str(Path(item["storage_dir"]) / "content.md")
            if item.get("storage_dir")
            else ""
        ),
    }


def _snippet(item: Dict[str, Any], n: int = 80) -> str:
    text = (item.get("title") or "").strip()
    body = (item.get("content") or "").strip().replace("\n", " ")
    if text and body:
        s = f"{text} · {body}"
    else:
        s = text or body
    media_n = len(item.get("media_paths") or [])
    if media_n:
        s = (s + f" · 图{media_n}") if s else f"图{media_n}"
    return s[:n] + ("…" if len(s) > n else "")


def _persist() -> None:
    if QUEUE_PATH is None:
        return
    dump = []
    for item in _ITEMS.values():
        row = {k: v for k, v in item.items() if not str(k).startswith("_")}
        dump.append(row)
    dump.sort(
        key=lambda x: (x.get("scheduled_at") or x.get("created_at") or "", x.get("id") or "")
    )
    tmp = QUEUE_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "items": dump}, f, ensure_ascii=False, indent=2)
    tmp.replace(QUEUE_PATH)


def _load() -> int:
    if QUEUE_PATH is None or not QUEUE_PATH.exists():
        return 0
    try:
        with open(QUEUE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("读取发布队列失败: %s", e)
        return 0
    raw = data.get("items") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return 0
    with _LOCK:
        _ITEMS.clear()
        for row in raw:
            if not isinstance(row, dict):
                continue
            item_id = str(row.get("id") or "").strip() or uuid.uuid4().hex[:10]
            status = str(row.get("status") or "pending")
            if status == "running":
                status = "pending"
                row["last_error"] = "上次进程中断，已重置为待发布"
            item = {
                "id": item_id,
                "title": str(row.get("title") or ""),
                "content": str(row.get("content") or ""),
                "media_paths": _normalize_media(row.get("media_paths")),
                "platforms": _normalize_platforms(row.get("platforms")) or ["x"],
                "tags": str(row.get("tags") or ""),
                "scheduled_at": _parse_when(row.get("scheduled_at")) or "",
                "status": status,
                "enabled": bool(row.get("enabled", True)),
                "use_cdp": bool(row.get("use_cdp", True)),
                "debugger_url": str(row.get("debugger_url") or "127.0.0.1:9222"),
                "created_at": row.get("created_at") or _now_iso(),
                "updated_at": row.get("updated_at") or row.get("created_at") or _now_iso(),
                "published_at": row.get("published_at"),
                "last_error": str(row.get("last_error") or ""),
                "last_result": row.get("last_result"),
                "storage_rel": str(row.get("storage_rel") or ""),
                "storage_dir": str(row.get("storage_dir") or ""),
                "month": str(row.get("month") or ""),
            }
            if not item["month"] and item["storage_rel"]:
                item["month"] = item["storage_rel"].split("/", 1)[0]
            _ITEMS[item_id] = item
        return len(_ITEMS)


def list_items(
    *,
    status: Optional[str] = None,
    include_done: bool = True,
    include_draft: bool = True,
) -> List[Dict[str, Any]]:
    with _LOCK:
        rows = list(_ITEMS.values())
    if status:
        rows = [r for r in rows if r.get("status") == status]
    else:
        if not include_done:
            rows = [r for r in rows if r.get("status") not in ("done", "cancelled")]
        if not include_draft:
            rows = [r for r in rows if r.get("status") != "draft"]
    rows.sort(
        key=lambda x: (
            x.get("scheduled_at") or x.get("created_at") or "9999",
            x.get("created_at") or "",
        )
    )
    return [_public_item(r) for r in rows]


def get_item(item_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        item = _ITEMS.get(item_id)
        return _public_item(item) if item else None


def add_item(body: Dict[str, Any]) -> Dict[str, Any]:
    body = dict(body)
    if body.get("save_only") or body.get("draft_only"):
        return save_draft(body, enqueue=False)
    return save_draft(body, enqueue=True)


def update_item(item_id: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    with _LOCK:
        item = _ITEMS.get(item_id)
        if not item:
            return None
        if item.get("status") == "running":
            raise ValueError("正在发布中，暂不可修改")

        if "title" in body:
            item["title"] = str(body.get("title") or "").strip()
        if "content" in body or "text" in body:
            item["content"] = str(body.get("content") or body.get("text") or "").strip()
        if "platforms" in body:
            plats = _normalize_platforms(body.get("platforms"))
            if plats:
                item["platforms"] = plats
        if "tags" in body:
            item["tags"] = str(body.get("tags") or "").strip()
        if "scheduled_at" in body or "schedule_at" in body:
            when = _parse_when(body.get("scheduled_at") or body.get("schedule_at"))
            if when:
                item["scheduled_at"] = when
                if item.get("status") == "draft":
                    item["status"] = "pending"
                    item["enabled"] = True
        if "enabled" in body:
            item["enabled"] = bool(body.get("enabled"))
        if "use_cdp" in body:
            item["use_cdp"] = bool(body.get("use_cdp"))
        if "debugger_url" in body and str(body.get("debugger_url") or "").strip():
            item["debugger_url"] = str(body.get("debugger_url")).strip()
        if "status" in body:
            st = str(body.get("status") or "").strip()
            if st in ("pending", "cancelled", "done", "failed", "draft"):
                item["status"] = st

        uploads = _decode_upload_files(body.get("media_files")) if body.get("media_files") else []
        if uploads or "media_paths" in body:
            if not item.get("storage_dir"):
                rel, abs_dir = _alloc_storage_dir(
                    item_id, item.get("scheduled_at") or item.get("created_at")
                )
                item["storage_rel"] = rel
                item["storage_dir"] = str(abs_dir)
                item["month"] = rel.split("/", 1)[0]
            extra_paths = _normalize_media(body.get("media_paths")) if "media_paths" in body else []
            _materialize_media(
                Path(item["storage_dir"]) / "media",
                path_sources=extra_paths,
                uploads=uploads,
            )
            item["media_paths"] = _scan_media(item["storage_dir"])

        if not item.get("content") and not item.get("media_paths"):
            raise ValueError("正文与媒体不能同时为空")
        item["updated_at"] = _now_iso()
        if item.get("status") in ("failed", "cancelled") and body.get("requeue"):
            item["status"] = "pending"
            item["last_error"] = ""
            item["enabled"] = True
        _save_bundle_files(item)
        _persist()
        return _public_item(item)


def delete_item(item_id: str, *, remove_files: bool = False) -> bool:
    with _LOCK:
        item = _ITEMS.get(item_id)
        if not item:
            return False
        storage = item.get("storage_dir")
        del _ITEMS[item_id]
        _persist()
    if remove_files and storage:
        shutil.rmtree(storage, ignore_errors=True)
    return True


def clear_done() -> int:
    with _LOCK:
        ids = [
            i
            for i, it in _ITEMS.items()
            if it.get("status") in ("done", "cancelled")
        ]
        for i in ids:
            del _ITEMS[i]
        if ids:
            _persist()
        return len(ids)


def list_months() -> List[Dict[str, Any]]:
    root = cache_root()
    if not root.exists():
        return []
    months = []
    for p in sorted(root.iterdir(), reverse=True):
        if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}", p.name):
            entries = [x for x in p.iterdir() if x.is_dir()]
            months.append(
                {"month": p.name, "count": len(entries), "path": str(p.resolve())}
            )
    return months


def list_cache_month(month: str) -> List[Dict[str, Any]]:
    month = str(month or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError("月份格式应为 YYYY-MM")
    month_dir = cache_root() / month
    if not month_dir.is_dir():
        return []
    rows: List[Dict[str, Any]] = []
    for folder in sorted(month_dir.iterdir(), reverse=True):
        if not folder.is_dir():
            continue
        meta_path = folder / "meta.json"
        content_path = folder / "content.md"
        media_dir = folder / "media"
        meta: Dict[str, Any] = {}
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        media_files = []
        if media_dir.is_dir():
            media_files = sorted(p.name for p in media_dir.iterdir() if p.is_file())
        text = ""
        if content_path.is_file():
            try:
                text = content_path.read_text(encoding="utf-8")
            except Exception:
                text = ""
        item_id = str(meta.get("id") or folder.name.split("_")[-1])
        rows.append(
            {
                "id": item_id,
                "folder": folder.name,
                "month": month,
                "storage_rel": f"{month}/{folder.name}",
                "storage_dir": str(folder.resolve()),
                "title": meta.get("title") or "",
                "content": meta.get("content") or "",
                "content_md": text,
                "snippet": ((meta.get("content") or text or "").replace("\n", " "))[:80],
                "media_files": media_files,
                "media_count": len(media_files),
                "scheduled_at": meta.get("scheduled_at") or "",
                "status": meta.get("status") or "",
                "platforms": meta.get("platforms") or [],
                "created_at": meta.get("created_at") or "",
            }
        )
    return rows


def read_content_md(storage_rel: str) -> str:
    path = resolve_cache_path(storage_rel)
    md = path / "content.md" if path.is_dir() else path
    if not md.is_file():
        raise FileNotFoundError("content.md 不存在")
    return md.read_text(encoding="utf-8")


def resolve_cache_path(rel: str) -> Path:
    rel = str(rel or "").replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError("非法路径")
    root = cache_root().resolve()
    target = (root / rel).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError("路径越界")
    return target


def reveal_in_finder(storage_rel_or_dir: str) -> Dict[str, Any]:
    raw = str(storage_rel_or_dir or "").strip()
    if not raw:
        raise ValueError("缺少路径")
    path = Path(raw)
    if not path.is_absolute():
        path = resolve_cache_path(raw)
    if not path.exists():
        raise FileNotFoundError(f"目录不存在: {path}")
    target = path if path.is_dir() else path.parent
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    elif sys.platform.startswith("win"):
        os.startfile(str(target))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(target)])
    return {"success": True, "path": str(target)}


def _due_items(now: Optional[datetime] = None) -> List[str]:
    now = now or datetime.now()
    due: List[str] = []
    with _LOCK:
        for item_id, item in _ITEMS.items():
            if not item.get("enabled"):
                continue
            if item.get("status") != "pending":
                continue
            when = item.get("scheduled_at") or ""
            if not when:
                continue
            try:
                dt = datetime.fromisoformat(when)
            except ValueError:
                continue
            if dt <= now:
                due.append(item_id)
    due.sort(key=lambda i: _ITEMS[i].get("scheduled_at") or "")
    return due


def publish_now(item_id: str) -> Dict[str, Any]:
    return _run_publish(item_id, force=True)


def _run_publish(item_id: str, *, force: bool = False) -> Dict[str, Any]:
    with _LOCK:
        item = _ITEMS.get(item_id)
        if not item:
            return {"success": False, "error": "条目不存在"}
        if item.get("status") == "running":
            return {"success": False, "error": "正在发布中"}
        if not force and item.get("status") != "pending":
            return {"success": False, "error": f"状态不可发: {item.get('status')}"}
        if not force and not item.get("enabled"):
            return {"success": False, "error": "条目已停用"}
        media = list(item.get("media_paths") or [])
        if item.get("storage_dir"):
            scanned = _scan_media(item["storage_dir"])
            if scanned:
                media = scanned
                item["media_paths"] = media
        snapshot = {
            "id": item["id"],
            "title": item.get("title") or "",
            "content": item.get("content") or "",
            "media_paths": media,
            "platforms": list(item.get("platforms") or []),
            "tags": item.get("tags") or "",
            "use_cdp": bool(item.get("use_cdp", True)),
            "debugger_url": item.get("debugger_url") or "127.0.0.1:9222",
        }
        item["status"] = "running"
        item["updated_at"] = _now_iso()
        item["last_error"] = ""
        _save_bundle_files(item)
        _persist()

    if not _PUBLISH_LOCK.acquire(timeout=300):
        with _LOCK:
            it = _ITEMS.get(item_id)
            if it and it.get("status") == "running":
                it["status"] = "pending"
                it["last_error"] = "等待发布锁超时"
                it["updated_at"] = _now_iso()
                _persist()
        return {"success": False, "error": "发布通道繁忙，请稍后"}

    try:
        from public.index import publish_content

        result = publish_content(
            content={
                "title": snapshot["title"],
                "content": snapshot["content"],
            },
            platform_ids=snapshot["platforms"],
            tags=snapshot["tags"] or None,
            use_cdp=snapshot["use_cdp"],
            debugger_url=snapshot["debugger_url"],
            media_paths=snapshot["media_paths"],
            submit=True,
        )
        ok = bool(result.get("success"))
        with _LOCK:
            it = _ITEMS.get(item_id)
            if it:
                it["status"] = "done" if ok else "failed"
                it["published_at"] = _now_iso() if ok else None
                it["last_result"] = result
                it["last_error"] = "" if ok else (
                    result.get("error")
                    or "; ".join(
                        str(r.get("error") or "")
                        for r in (result.get("results") or [])
                        if not r.get("success")
                    )
                    or "发布失败"
                )
                it["updated_at"] = _now_iso()
                _save_bundle_files(it)
                _persist()
        return {"success": ok, "item": get_item(item_id), "result": result}
    except Exception as e:
        logger.exception("定时发布失败 %s", item_id)
        with _LOCK:
            it = _ITEMS.get(item_id)
            if it:
                it["status"] = "failed"
                it["last_error"] = str(e)
                it["updated_at"] = _now_iso()
                _save_bundle_files(it)
                _persist()
        return {"success": False, "error": str(e), "item": get_item(item_id)}
    finally:
        _PUBLISH_LOCK.release()


def _scheduler_loop() -> None:
    while not _SCHEDULER_STOP.is_set():
        try:
            due = _due_items()
            for item_id in due:
                if _SCHEDULER_STOP.is_set():
                    break
                logger.info("定时发布触发: %s", item_id)
                _run_publish(item_id, force=False)
        except Exception:
            logger.exception("发布队列调度异常")
        _SCHEDULER_STOP.wait(5.0)


def _ensure_scheduler() -> None:
    global _SCHEDULER_THREAD
    if _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
        return
    _SCHEDULER_STOP.clear()
    _SCHEDULER_THREAD = threading.Thread(
        target=_scheduler_loop, name="publish-queue", daemon=True
    )
    _SCHEDULER_THREAD.start()


def stop_scheduler() -> None:
    _SCHEDULER_STOP.set()


def stats() -> Dict[str, int]:
    with _LOCK:
        counts = {
            "all": len(_ITEMS),
            "pending": 0,
            "running": 0,
            "done": 0,
            "failed": 0,
            "cancelled": 0,
            "draft": 0,
        }
        for it in _ITEMS.values():
            st = str(it.get("status") or "pending")
            if st in counts:
                counts[st] += 1
        return counts
