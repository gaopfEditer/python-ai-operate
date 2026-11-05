# coding=utf-8
"""CDP 发布可诊断日志：按平台写入 output/publish_logs/，并同步到标准 logging。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("public.publish")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR = _PROJECT_ROOT / "output" / "publish_logs"
_FILE_LOCK = threading.Lock()

_trace_job_id: ContextVar[str] = ContextVar("publish_trace_job_id", default="")
_trace_content_ref: ContextVar[str] = ContextVar("publish_trace_content_ref", default="")

_SECRET_PATTERNS = (
    re.compile(r"(?i)(cookie|set-cookie|authorization|bearer\s+)[^\s,;]{8,}"),
    re.compile(r"(?i)(password|passwd|api[_-]?token|secret)[\"'\s:=]+[^\s\"']{4,}"),
    re.compile(r"(?i)(sessionid|csrf)[\"'\s:=]+[^\s\"']{8,}"),
)


def publish_log_dir() -> Path:
    return _LOG_DIR


def default_log_file(for_day: Optional[datetime] = None) -> Path:
    day = (for_day or datetime.now()).strftime("%Y-%m-%d")
    return _LOG_DIR / f"publish_{day}.log"


def set_trace_context(*, job_id: str = "", content_ref: str = "") -> None:
    if job_id is not None:
        _trace_job_id.set(str(job_id or "").strip())
    if content_ref is not None:
        _trace_content_ref.set(str(content_ref or "").strip())


def clear_trace_context() -> None:
    _trace_job_id.set("")
    _trace_content_ref.set("")


def content_ref_from_body(title: str, content: str) -> str:
    raw = f"{title or ''}\n{content or ''}".strip()
    if not raw:
        return ""
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"body:{digest}"


def sanitize_message(text: Any, *, max_len: int = 500) -> str:
    s = str(text or "").strip()
    for pat in _SECRET_PATTERNS:
        s = pat.sub(r"\1[redacted]", s)
    s = re.sub(r"\s+", " ", s)
    if len(s) > max_len:
        s = s[: max_len - 3] + "..."
    return s


def sanitize_url(url: Any) -> str:
    s = str(url or "").strip()
    if not s:
        return ""
    # 去掉 query 里可能的长 token
    if "?" in s:
        base, q = s.split("?", 1)
        if any(k in q.lower() for k in ("token", "sig", "auth", "key=")):
            return base + "?[redacted]"
    return s[:400]


def classify_failure_category(
    message: str,
    *,
    exc_type: Optional[str] = None,
) -> str:
    msg = (message or "").lower()
    et = (exc_type or "").lower()
    if "publishaborted" in et or "已终止" in message:
        return "aborted"
    if et.endswith("timeouterror") or "timeout" in msg or "timed out" in msg or "超时" in message:
        return "timeout"
    if any(k in msg for k in ("cdp", "chromedriver", "debugger", "9222", "9223", "attach", "session not created")):
        return "network"
    if any(k in message for k in ("登录", "sign in", "log in", "未登录")):
        return "login"
    if any(k in message for k in ("未找到", "无法点击", "selector", "编辑框", "编辑区", "按钮")):
        return "selector"
    if any(k in msg for k in ("connection", "refused", "network", "urlopen", "errno")):
        return "network"
    if et:
        return "error"
    return "error"


def resolve_failed_step(error: str, steps: Optional[Sequence[str]]) -> str:
    steps = list(steps or [])
    err = error or ""
    if "CDP" in err or "ChromeDriver" in err or "连接失败" in err:
        return "connect_cdp"
    if "没有打开" in err or "离开了" in err:
        return "open_compose" if steps else "navigate"
    if "编辑" in err or "editor" in err.lower():
        return "find_editor"
    if "发帖" in err or "Tweet" in err or "submit" in err.lower():
        return "click_post"
    if "innerText" in err or "换行" in err:
        return "validate_text"
    if "发出" in err or "unconfirmed" in err.lower():
        return "confirm_post"
    if steps:
        return f"after:{steps[-1]}"
    return "unknown"


def enrich_failure_diagnostics(
    result: Dict[str, Any],
    *,
    driver: Any = None,
    exc: Optional[BaseException] = None,
) -> Dict[str, Any]:
    if result.get("success"):
        return result
    out = dict(result)
    steps = out.get("steps") if isinstance(out.get("steps"), list) else []
    err = str(out.get("error") or "")
    if exc is not None and not out.get("exception_type"):
        out["exception_type"] = type(exc).__name__
    if not out.get("failed_step"):
        out["failed_step"] = resolve_failed_step(err, steps)
    if driver is not None and not out.get("last_url"):
        try:
            out["last_url"] = sanitize_url(getattr(driver, "current_url", "") or "")
        except Exception:
            pass
    if not out.get("failure_category"):
        out["failure_category"] = classify_failure_category(
            err,
            exc_type=str(out.get("exception_type") or ""),
        )
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _append_record(record: Dict[str, Any]) -> Path:
    path = default_log_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with _FILE_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    return path


def _emit(record: Dict[str, Any]) -> None:
    rec = dict(record)
    rec.setdefault("ts", _now_iso())
    if "message" in rec:
        rec["message"] = sanitize_message(rec["message"])
    if "last_url" in rec:
        rec["last_url"] = sanitize_url(rec.get("last_url"))
    path = _append_record(rec)
    rec["log_file"] = str(path.relative_to(_PROJECT_ROOT))
    level = logging.INFO if rec.get("event") not in ("platform_fail", "run_fail", "cdp_connect_fail") else logging.WARNING
    logger.log(
        level,
        "[publish] %s",
        " · ".join(
            str(rec.get(k) or "")
            for k in (
                "event",
                "platform",
                "step",
                "failure_category",
                "message",
            )
            if rec.get(k)
        ),
    )


def log_event(event: str, **fields: Any) -> None:
    job_id = str(fields.pop("job_id", None) or _trace_job_id.get() or "")
    content_ref = str(fields.pop("content_ref", None) or _trace_content_ref.get() or "")
    payload: Dict[str, Any] = {"event": event}
    if job_id:
        payload["job_id"] = job_id
    if content_ref:
        payload["content_ref"] = content_ref
    payload.update(fields)
    _emit(payload)


def log_run_start(
    *,
    platform_ids: Sequence[str],
    debugger_url: str = "",
    submit: bool = True,
    media_count: int = 0,
    job_id: str = "",
    content_ref: str = "",
) -> None:
    set_trace_context(job_id=job_id, content_ref=content_ref)
    dbg = sanitize_message(debugger_url or "127.0.0.1:9222")
    log_event(
        "run_start",
        job_id=job_id,
        content_ref=content_ref,
        platforms=list(platform_ids),
        debugger_url=dbg,
        submit=bool(submit),
        media_count=int(media_count or 0),
        message=f"开始发布 {len(platform_ids)} 个平台",
    )


def log_cdp_connect(*, ok: bool, debugger_url: str, error: str = "", exc_type: str = "") -> None:
    if ok:
        log_event(
            "cdp_connect_ok",
            step="connect_cdp",
            debugger_url=sanitize_message(debugger_url),
            message="CDP 已连接",
        )
        return
    log_event(
        "cdp_connect_fail",
        step="connect_cdp",
        debugger_url=sanitize_message(debugger_url),
        failure_category=classify_failure_category(error, exc_type=exc_type),
        exception_type=exc_type or "",
        message=sanitize_message(error or "CDP 连接失败"),
    )


def log_platform_start(
    *,
    platform_id: str,
    platform_name: str,
    index: int,
    total: int,
) -> None:
    log_event(
        "platform_start",
        platform=platform_id,
        platform_name=platform_name,
        index=index,
        total=total,
        step="start",
        message=f"({index}/{total}) {platform_name}",
    )


def log_platform_result(
    *,
    platform_id: str,
    platform_name: str,
    result: Dict[str, Any],
    elapsed_ms: int = 0,
    driver: Any = None,
    exc: Optional[BaseException] = None,
) -> None:
    row = enrich_failure_diagnostics(result, driver=driver, exc=exc)
    steps = row.get("steps") if isinstance(row.get("steps"), list) else []
    base = {
        "platform": platform_id,
        "platform_name": platform_name,
        "elapsed_ms": int(elapsed_ms or 0),
        "steps": steps,
    }
    if row.get("success"):
        log_event(
            "platform_ok",
            **base,
            step="done",
            post_url=sanitize_url(row.get("url") or ""),
            message=sanitize_message(row.get("message") or "发布成功"),
        )
        return
    log_event(
        "platform_fail",
        **base,
        step=str(row.get("failed_step") or "unknown"),
        failure_category=str(row.get("failure_category") or "error"),
        exception_type=str(row.get("exception_type") or ""),
        last_url=sanitize_url(row.get("last_url") or ""),
        message=sanitize_message(row.get("error") or "发布失败"),
        aborted=bool(row.get("aborted")),
    )


def log_run_end(
    *,
    success_count: int,
    total: int,
    elapsed_ms: int,
    aborted: bool = False,
) -> None:
    log_event(
        "run_end",
        success_count=int(success_count),
        total=int(total),
        elapsed_ms=int(elapsed_ms),
        aborted=bool(aborted),
        message=f"发布结束 成功 {success_count}/{total}",
    )
    clear_trace_context()


def format_failure_line(record: Dict[str, Any]) -> str:
    """供单元测试与 UI 展示的简短单行摘要。"""
    parts = [
        record.get("ts") or "",
        str(record.get("platform") or record.get("platform_name") or "?"),
        str(record.get("step") or ""),
        str(record.get("failure_category") or ("ok" if record.get("event") == "platform_ok" else "")),
        sanitize_message(record.get("message") or ""),
    ]
    return " | ".join(p for p in parts if p)
