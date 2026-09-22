# coding=utf-8
"""控制台 CDP 多平台发布：后台 Job + 可终止重试 + 进度可恢复。"""

from __future__ import annotations

import random
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

PUBLISH_RETRY_MAX = 5
PUBLISH_RETRY_WAIT_MIN_SEC = 180
PUBLISH_RETRY_WAIT_MAX_SEC = 300

_ACTIVE_RUN: Optional[str] = None
_ACTIVE_LOCK = threading.Lock()


def active_run_id() -> str:
    with _ACTIVE_LOCK:
        return _ACTIVE_RUN or ""


def _platform_label(pid: str) -> str:
    try:
        from public.index import list_platforms

        for row in list_platforms() or []:
            if row.get("id") == pid:
                return str(row.get("name") or pid)
    except Exception:
        pass
    return str(pid or "")


def _sleep_retry(wait_sec: float, ctl, on_tick) -> bool:
    end = time.time() + max(0.0, wait_sec)
    while time.time() < end:
        if ctl.is_stopped():
            return False
        left = max(0, int(end - time.time()))
        on_tick(left)
        time.sleep(min(1.0, max(0.0, end - time.time())))
    return True


def _publish_one(
    *,
    pid: str,
    base: Dict[str, Any],
    media_paths: List[str],
    lock_acquire,
    lock_release,
) -> Dict[str, Any]:
    from public.index import publish_content

    lock_key = f"publish|{pid}|{(base.get('content') or '')[:64]}|{','.join(map(str, media_paths))}"
    if not lock_acquire(lock_key):
        return {
            "platform": pid,
            "platform_name": _platform_label(pid),
            "success": False,
            "error": "另一个发布任务正在进行，请稍候再试",
        }
    try:
        result = publish_content(
            content={"title": base.get("title") or "", "content": base.get("content") or ""},
            platform_ids=[pid],
            tags=base.get("tags") or None,
            use_cdp=bool(base.get("use_cdp", True)),
            debugger_url=base.get("debugger_url") or None,
            media_paths=media_paths,
            submit=bool(base.get("submit", True)),
        )
        row = (result.get("results") or [{}])[0] if isinstance(result.get("results"), list) else {}
        if not row:
            row = result
        return {
            "platform": pid,
            "platform_name": row.get("platform_name") or _platform_label(pid),
            "success": bool(row.get("success") if "success" in row else result.get("success")),
            "error": row.get("error") or result.get("error") or "",
        }
    except Exception as e:
        return {
            "platform": pid,
            "platform_name": _platform_label(pid),
            "success": False,
            "error": str(e),
        }
    finally:
        lock_release()


def _run_worker(
    job_id: str,
    body: Dict[str, Any],
    media_paths: List[str],
    *,
    set_job: Callable[..., None],
    lock_acquire,
    lock_release,
) -> None:
    from signals.control import RunControl, register, unregister

    platforms = [str(p).strip() for p in (body.get("platforms") or []) if str(p).strip()]
    submit = bool(body.get("submit", True))
    base = {
        "title": str(body.get("title") or "").strip(),
        "content": str(body.get("content") or body.get("text") or "").strip(),
        "tags": str(body.get("tags") or "").strip() or None,
        "use_cdp": bool(body.get("use_cdp", True)),
        "debugger_url": str(body.get("debugger_url") or "").strip() or "127.0.0.1:9222",
        "submit": submit,
    }
    ctl = register(job_id, RunControl(job_id))
    step_results: List[Dict[str, Any]] = []
    staged_paths = list(media_paths)
    aborted = False

    def _touch_progress(**progress: Any) -> None:
        set_job(
            job_id,
            publish_progress={
                **progress,
                "results": [dict(r) for r in step_results],
            },
        )

    def _run_platform(pid: str, attempt: int) -> Dict[str, Any]:
        name = _platform_label(pid)
        label = f"{name}（重试 {attempt - 1}/{PUBLISH_RETRY_MAX}）" if attempt > 1 else name
        idx = platforms.index(pid) + 1 if pid in platforms else len(step_results) + 1
        _touch_progress(
            phase="running",
            index=idx,
            total=len(platforms),
            platform=pid,
            name=label,
        )
        set_job(job_id, status="running", message=f"正在发布 ({idx}/{len(platforms)}) {label}…")
        row = _publish_one(pid=pid, base=base, media_paths=staged_paths, lock_acquire=lock_acquire, lock_release=lock_release)
        prev = next((r for r in step_results if r.get("platform") == pid), None)
        merged = {
            "platform": pid,
            "name": row.get("platform_name") or name,
            "success": bool(row.get("success")),
            "error": row.get("error") or "",
            "attempts": (prev.get("attempts") if prev else 0) + 1,
        }
        if prev:
            prev.update(merged)
        else:
            step_results.append(merged)
        _touch_progress(
            phase="done" if merged["success"] else "fail",
            index=idx,
            total=len(platforms),
            platform=pid,
            name=name,
        )
        return merged

    try:
        set_job(
            job_id,
            status="running",
            type="publish_run",
            message="准备发布…",
            platforms=platforms,
            media_count=len(staged_paths),
            started_at=datetime.now().isoformat(timespec="seconds"),
            control_status="running",
        )
        for pid in platforms:
            if ctl.is_stopped():
                aborted = True
                break
            _run_platform(pid, 1)

        if submit and not ctl.is_stopped():
            for retry in range(1, PUBLISH_RETRY_MAX + 1):
                failed = [r for r in step_results if not r.get("success")]
                if not failed:
                    break
                names = "、".join(r.get("name") or r.get("platform") or "?" for r in failed)
                wait_sec = random.uniform(PUBLISH_RETRY_WAIT_MIN_SEC, PUBLISH_RETRY_WAIT_MAX_SEC)

                def _on_tick(left: int) -> None:
                    set_job(
                        job_id,
                        message=f"{names} 失败，{retry}/{PUBLISH_RETRY_MAX} 次重试将在 {left // 60}:{left % 60:02d} 后开始…",
                    )
                    _touch_progress(
                        phase="retry_wait",
                        index=len(platforms),
                        total=len(platforms),
                        retry=retry,
                        retryMax=PUBLISH_RETRY_MAX,
                        waitLeft=left,
                        retryNames=names,
                    )

                if not _sleep_retry(wait_sec, ctl, _on_tick):
                    aborted = True
                    _touch_progress(
                        phase="retry_abort",
                        index=len(platforms),
                        total=len(platforms),
                        retryNames=names,
                    )
                    set_job(job_id, message=f"{names} 已终止")
                    break

                for row in failed:
                    if ctl.is_stopped():
                        aborted = True
                        break
                    cur = next((r for r in step_results if r.get("platform") == row.get("platform")), None)
                    if cur and cur.get("success"):
                        continue
                    _run_platform(str(row.get("platform")), retry + 1)
                if aborted:
                    break

        success_count = sum(1 for r in step_results if r.get("success"))
        total = len(platforms)
        result = {
            "success": success_count > 0,
            "total": total,
            "success_count": success_count,
            "results": step_results,
            "aborted": aborted,
        }
        if aborted:
            status = "cancelled"
            message = f"已终止 · 成功 {success_count}/{total}"
        elif success_count == total and total > 0:
            status = "done"
            message = f"发布完成 {success_count}/{total}"
        elif success_count > 0:
            status = "done"
            message = f"部分完成 {success_count}/{total}"
        else:
            status = "error"
            message = "发布失败"
        _touch_progress(
            phase="retry_abort" if aborted else "done",
            index=total,
            total=total,
            results=step_results,
        )
        set_job(
            job_id,
            status=status,
            message=message,
            result=result,
            control_status=ctl.status(),
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
    except Exception as e:
        set_job(
            job_id,
            status="error",
            message=str(e),
            control_status=ctl.status(),
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
    finally:
        unregister(job_id)
        with _ACTIVE_LOCK:
            global _ACTIVE_RUN
            if _ACTIVE_RUN == job_id:
                _ACTIVE_RUN = None


def start_run(
    body: Dict[str, Any],
    *,
    set_job: Callable[..., None],
    get_job: Callable[[str], Optional[Dict[str, Any]]],
    lock_acquire,
    lock_release,
) -> tuple[bytes, int, str]:
    from console.app import _json_bytes
    from console import publish_queue as pq

    platforms = body.get("platforms")
    if isinstance(platforms, str):
        platforms = [p.strip() for p in platforms.split(",") if p.strip()]
    if not isinstance(platforms, list) or not [p for p in platforms if str(p).strip()]:
        return _json_bytes({"success": False, "error": "请至少选择一个平台"}, 400)

    content = str(body.get("content") or body.get("text") or "").strip()
    try:
        media_paths = pq.resolve_publish_media(body)
    except ValueError as e:
        return _json_bytes({"success": False, "error": str(e)}, 400)
    except Exception as e:
        return _json_bytes({"success": False, "error": f"媒体处理失败: {e}"}, 500)

    if not content and not media_paths:
        return _json_bytes({"success": False, "error": "请填写正文或上传图片"}, 400)

    with _ACTIVE_LOCK:
        global _ACTIVE_RUN
        if _ACTIVE_RUN:
            existing = get_job(_ACTIVE_RUN) or {}
            if existing.get("status") in ("queued", "running"):
                return _json_bytes(
                    {
                        "success": True,
                        "job_id": _ACTIVE_RUN,
                        "status": existing.get("status"),
                        "resumed": True,
                        "message": "已有发布任务进行中",
                    }
                )

        job_id = uuid.uuid4().hex[:12]
        _ACTIVE_RUN = job_id

    set_job(
        job_id,
        status="queued",
        type="publish_run",
        message="排队中…",
        platforms=[str(p).strip() for p in platforms if str(p).strip()],
        media_count=len(media_paths),
        control_status="running",
    )
    payload = dict(body)
    payload["platforms"] = [str(p).strip() for p in platforms if str(p).strip()]
    threading.Thread(
        target=_run_worker,
        args=(job_id, payload, media_paths),
        kwargs={
            "set_job": set_job,
            "lock_acquire": lock_acquire,
            "lock_release": lock_release,
        },
        daemon=True,
        name=f"publish-run-{job_id[:8]}",
    ).start()
    return _json_bytes({"success": True, "job_id": job_id, "status": "queued"})


def control_run(body: Dict[str, Any], *, set_job: Callable[..., None]) -> tuple[bytes, int, str]:
    from console.app import _json_bytes
    from signals.control import control_action, get as get_ctl

    job_id = str(body.get("job_id") or active_run_id() or "").strip()
    action = str(body.get("action") or "stop").strip().lower()
    out = control_action(job_id, action)
    if not out.get("success"):
        return _json_bytes(out, 400)
    jid = str(out.get("job_id") or job_id)
    if jid:
        set_job(jid, control_status=out.get("status") or "stopped", message="正在终止…")
    return _json_bytes(out)


def active_run_payload(*, get_job: Callable[[str], Optional[Dict[str, Any]]]) -> tuple[bytes, int, str]:
    from console.app import _json_bytes

    jid = active_run_id()
    if not jid:
        return _json_bytes({"success": True, "job_id": "", "job": None})
    job = get_job(jid)
    if not job or job.get("status") not in ("queued", "running"):
        return _json_bytes({"success": True, "job_id": "", "job": job})
    return _json_bytes({"success": True, "job_id": jid, "job": job})
