# coding=utf-8
"""对外 CDP 发布 API：文本 + 多图，供控制台以外的调用方使用。"""

from __future__ import annotations

import base64
import os
import threading
import uuid
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_MAX_FILES = 12
_MAX_BYTES = 12 * 1024 * 1024
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v"}
_MEDIA_EXTS = _IMAGE_EXTS | _VIDEO_EXTS


def _json_bytes(data: Any, status: int = 200) -> tuple[bytes, int, str]:
    from console.app import _json_bytes as _jb

    return _jb(data, status)


def _truthy(val: Any, default: bool = False) -> bool:
    if val is None or val == "":
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() not in ("0", "false", "no", "off")


def _as_list(val: Any) -> List[str]:
    if val is None or val == "":
        return []
    if isinstance(val, list):
        out: List[str] = []
        for x in val:
            if isinstance(x, str):
                out.extend(p.strip() for p in x.split(",") if p.strip())
            elif x:
                out.append(str(x).strip())
        return [x for x in out if x]
    return [p.strip() for p in str(val).split(",") if p.strip()]


def expected_token() -> str:
    env = (os.environ.get("PUBLISH_API_TOKEN") or "").strip()
    if env:
        return env
    try:
        from public.index import load_publish_config

        return str((load_publish_config() or {}).get("api_token") or "").strip()
    except Exception:
        return ""


def _request_token(headers: Optional[Any], query: Dict[str, List[str]], body: Dict[str, Any]) -> str:
    if headers is not None and hasattr(headers, "get"):
        auth = str(headers.get("Authorization") or headers.get("authorization") or "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        tok = str(headers.get("X-Publish-Token") or headers.get("x-publish-token") or "").strip()
        if tok:
            return tok
    q = ((query.get("token") or [""])[0] or "").strip()
    if q:
        return q
    return str(body.get("token") or "").strip()


def require_token(
    headers: Optional[Any],
    query: Dict[str, List[str]],
    body: Dict[str, Any],
) -> Optional[tuple[bytes, int, str]]:
    need = expected_token()
    if not need:
        return None
    got = _request_token(headers, query, body)
    if got != need:
        return _json_bytes({"success": False, "error": "未授权：缺少或错误的 PUBLISH_API_TOKEN"}, 401)
    return None


def parse_multipart(raw: bytes, content_type: str) -> Dict[str, Any]:
    """把 multipart/form-data 收成普通字段 + `_files`。"""
    header = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8", errors="replace")
    msg = BytesParser(policy=policy.default).parsebytes(header + raw)
    fields: Dict[str, Any] = {}
    files: List[Dict[str, Any]] = []
    if not msg.is_multipart():
        return fields

    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True)
        if payload is None:
            payload = b""
        if filename:
            files.append(
                {
                    "name": Path(str(filename)).name or "upload.bin",
                    "data": payload,
                    "type": part.get_content_type() or "",
                }
            )
            continue
        text = payload.decode("utf-8", errors="replace")
        if name in fields:
            prev = fields[name]
            fields[name] = (prev if isinstance(prev, list) else [prev]) + [text]
        else:
            fields[name] = text
    if files:
        fields["_files"] = files
    return fields


def _guess_ext(name: str, mime: str, data: bytes) -> str:
    ext = Path(name).suffix.lower()
    if ext in _MEDIA_EXTS:
        return name
    mime = (mime or "").lower()
    mapping = (
        ("png", ".png"),
        ("jpeg", ".jpg"),
        ("jpg", ".jpg"),
        ("gif", ".gif"),
        ("webp", ".webp"),
        ("mp4", ".mp4"),
        ("quicktime", ".mov"),
        ("webm", ".webm"),
    )
    for needle, suf in mapping:
        if needle in mime:
            return name + suf
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return name + ".png"
    if data[:3] == b"\xff\xd8\xff":
        return name + ".jpg"
    if data[:4] == b"GIF8":
        return name + ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return name + ".webp"
    return name + ".jpg"


def _download_image(url: str) -> Tuple[str, bytes]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不支持的图片地址: {url}")
    req = Request(url, headers={"User-Agent": "TrendRadar-PublishAPI/1"})
    with urlopen(req, timeout=30) as resp:
        data = resp.read(_MAX_BYTES + 1)
        mime = str(resp.headers.get("Content-Type") or "")
    if len(data) > _MAX_BYTES:
        raise ValueError(f"远程图片超过 {_MAX_BYTES // (1024 * 1024)}MB")
    name = Path(parsed.path).name or "remote"
    return _guess_ext(name, mime, data), data


def _files_from_multipart(body: Dict[str, Any]) -> List[Tuple[str, bytes]]:
    out: List[Tuple[str, bytes]] = []
    for row in body.get("_files") or []:
        if not isinstance(row, dict):
            continue
        data = row.get("data") or b""
        if not data:
            continue
        if len(data) > _MAX_BYTES:
            raise ValueError(f"文件过大（>{_MAX_BYTES // (1024 * 1024)}MB）: {row.get('name')}")
        name = _guess_ext(str(row.get("name") or "upload"), str(row.get("type") or ""), data)
        out.append((name, data))
        if len(out) >= _MAX_FILES:
            break
    return out


def _files_from_images_field(raw: Any) -> List[Tuple[str, bytes]]:
    if not raw:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: List[Tuple[str, bytes]] = []
    for i, item in enumerate(items):
        if len(out) >= _MAX_FILES:
            break
        if isinstance(item, str):
            s = item.strip()
            if not s:
                continue
            if s.startswith("data:"):
                header, _, b64 = s.partition(",")
                data = base64.b64decode(b64, validate=False)
                mime = header.split(";")[0].replace("data:", "")
                out.append((_guess_ext(f"image_{i + 1}", mime, data), data))
            elif s.startswith(("http://", "https://")):
                out.append(_download_image(s))
            continue
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("href") or "").strip()
        if url.startswith(("http://", "https://")):
            out.append(_download_image(url))
            continue
        name = str(item.get("name") or item.get("filename") or f"image_{i + 1}").strip()
        b64 = item.get("data_b64") or item.get("content_base64") or item.get("data") or ""
        if isinstance(b64, str) and "," in b64 and b64.strip().startswith("data:"):
            b64 = b64.split(",", 1)[1]
        if not b64:
            continue
        data = base64.b64decode(b64, validate=False)
        if len(data) > _MAX_BYTES:
            raise ValueError(f"文件过大（>{_MAX_BYTES // (1024 * 1024)}MB）: {name}")
        out.append((_guess_ext(name, str(item.get("type") or item.get("mime") or ""), data), data))
    return out


def resolve_external_media(body: Dict[str, Any]) -> List[str]:
    from console import publish_queue as pq

    try:
        pq.cache_root()
    except RuntimeError:
        pq.init(
            PROJECT_ROOT / "output" / "publish_queue.json",
            cache_root=PROJECT_ROOT / "output" / "publish_cache",
        )

    uploads = list(_files_from_multipart(body))
    uploads.extend(_files_from_images_field(body.get("images") or body.get("image")))
    extra = dict(body)
    if uploads:
        extra["media_files"] = [
            {"name": name, "data_b64": base64.b64encode(data).decode("ascii")}
            for name, data in uploads
        ] + list(extra.get("media_files") or [])
    return pq.resolve_publish_media(extra)


def _list_platforms() -> List[Dict[str, Any]]:
    fallback = [
        {"id": "binance_square", "name": "币安广场", "enabled": True, "type": "binance_square"},
        {"id": "okx", "name": "OKX", "enabled": True, "type": "okx"},
        {"id": "bitget", "name": "Bitget", "enabled": True, "type": "bitget"},
        {"id": "gate", "name": "Gate 广场", "enabled": True, "type": "gate"},
        {"id": "x", "name": "X / Twitter", "enabled": True, "type": "x"},
    ]
    try:
        from public.index import list_platforms

        rows = [p for p in (list_platforms() or []) if (p.get("type") or "") != "typecho"]
        return rows or fallback
    except Exception:
        return fallback


def _run_publish(payload: Dict[str, Any]) -> Dict[str, Any]:
    import time

    from console.app import _publish_lock_acquire, _publish_lock_release
    from public.index import publish_content_with_retry

    lock_key = "v1-publish|{platforms}|{text}|{media}".format(
        platforms=",".join(payload["platforms"] or []),
        text=(payload["content"] or "")[:64],
        media=",".join(payload["media_paths"]),
    )
    if not _publish_lock_acquire(lock_key):
        return {"success": False, "error": "另一个发布任务正在进行，请稍候再试", "elapsed_ms": 0}
    t0 = time.perf_counter()
    try:
        result = publish_content_with_retry(
            content={"title": payload["title"], "content": payload["content"]},
            platform_ids=payload["platforms"] or None,
            tags=payload.get("tags"),
            use_cdp=True,
            debugger_url=payload.get("debugger_url") or None,
            media_paths=payload["media_paths"],
            submit=payload["submit"],
        )
        result["media_count"] = len(payload["media_paths"])
        if "elapsed_ms" not in result:
            result["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        return result
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {"success": False, "error": str(e), "elapsed_ms": elapsed_ms}
    finally:
        _publish_lock_release()


def _start_job(payload: Dict[str, Any]) -> tuple[bytes, int, str]:
    import time

    from console.app import _set_job

    job_id = uuid.uuid4().hex
    _set_job(
        job_id,
        status="queued",
        type="cdp_publish",
        message="排队中…",
        platforms=payload["platforms"],
        media_count=len(payload["media_paths"]),
    )

    def _worker() -> None:
        from console.app import _set_job as set_job

        set_job(job_id, status="running", message="正在 CDP 发布…")
        t0 = time.perf_counter()
        try:
            result = _run_publish(payload)
            ok = bool(result.get("success"))
            elapsed_ms = int(result.get("elapsed_ms") or (time.perf_counter() - t0) * 1000)
            set_job(
                job_id,
                status="done" if ok else "error",
                message=(
                    f"{'发布完成' if ok else str(result.get('error') or '发布失败')}"
                    f" · {elapsed_ms}ms"
                ),
                result=result,
                elapsed_ms=elapsed_ms,
            )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            set_job(
                job_id,
                status="error",
                message=f"{e} · {elapsed_ms}ms",
                elapsed_ms=elapsed_ms,
            )

    threading.Thread(target=_worker, daemon=True, name=f"publish-api-{job_id[:8]}").start()
    return _json_bytes(
        {
            "success": True,
            "job_id": job_id,
            "status": "queued",
            "poll": f"/api/v1/publish/jobs/{job_id}",
        }
    )


def handle(
    method: str,
    path: str,
    query: Dict[str, List[str]],
    body: Dict[str, Any],
    headers: Optional[Any] = None,
) -> tuple[bytes, int, str]:
    denied = require_token(headers, query, body or {})
    if denied:
        return denied

    if path == "/api/v1/publish/platforms" and method == "GET":
        return _json_bytes({"success": True, "platforms": _list_platforms()})

    if path.startswith("/api/v1/publish/jobs/") and method == "GET":
        from console.app import _get_job

        job_id = path[len("/api/v1/publish/jobs/") :].strip("/")
        job = _get_job(job_id)
        if not job:
            return _json_bytes({"success": False, "error": "任务不存在"}, 404)
        return _json_bytes({"success": True, "job": job})

    if path != "/api/v1/publish" or method != "POST":
        return _json_bytes({"success": False, "error": "Not Found"}, 404)

    title = str(body.get("title") or "").strip()
    content = str(body.get("content") or body.get("text") or "").strip()
    platforms = _as_list(body.get("platforms") or body.get("platform"))
    tags = str(body.get("tags") or "").strip() or None
    debugger_url = str(body.get("debugger_url") or "").strip()
    submit = _truthy(body.get("submit"), True)
    async_mode = _truthy(body.get("async"), True)

    try:
        media_paths = resolve_external_media(body)
    except ValueError as e:
        return _json_bytes({"success": False, "error": str(e)}, 400)
    except Exception as e:
        return _json_bytes({"success": False, "error": f"媒体处理失败: {e}"}, 500)

    if not content and not media_paths:
        return _json_bytes({"success": False, "error": "请提供 text/content 或至少一张图片"}, 400)

    payload = {
        "title": title,
        "content": content,
        "platforms": platforms,
        "tags": tags,
        "debugger_url": debugger_url,
        "submit": submit,
        "media_paths": media_paths,
    }
    if async_mode:
        return _start_job(payload)
    result = _run_publish(payload)
    status = 200 if result.get("success") else 500
    if result.get("error") and "正在进行" in str(result.get("error")):
        status = 429
    return _json_bytes(result, status)
