# coding=utf-8
"""X 列表信号 · 所选 KOL 周期实时抓取（默认 15 分钟）。"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from signals.store import get_config, save_config

_LOCK = threading.RLock()
_STOP = threading.Event()
_THREAD: Optional[threading.Thread] = None
_RUNNING_JOB = False
_STATUS: Dict[str, Any] = {
    "enabled": False,
    "alive": False,
    "last_run_at": None,
    "last_status": None,
    "last_message": "",
    "next_wait_seconds": None,
    "next_run_at": None,
    "active_job_id": "",
}


def _set_status(**kwargs: Any) -> None:
    with _LOCK:
        _STATUS.update(kwargs)


def _interval_seconds(cfg: Optional[Dict[str, Any]] = None) -> int:
    cfg = cfg or get_config()
    try:
        mins = int(cfg.get("kol_realtime_interval_min") or 15)
    except (TypeError, ValueError):
        mins = 15
    return max(5, min(mins, 120)) * 60


def status() -> Dict[str, Any]:
    cfg = get_config()
    with _LOCK:
        snap = dict(_STATUS)
    snap.update(
        {
            "enabled": bool(cfg.get("kol_realtime_enabled")),
            "session_id": str(cfg.get("kol_realtime_session_id") or ""),
            "session_started_at": str(cfg.get("kol_realtime_session_started_at") or ""),
            "interval_min": int(cfg.get("kol_realtime_interval_min") or 15),
            "cutoff_hours": _cutoff_hours_for_run(cfg),
            "max_tweets": int(cfg.get("kol_realtime_max_tweets") or 40),
            "handles": list(cfg.get("kol_realtime_handles") or []),
            "push_enabled": bool(cfg.get("kol_realtime_push_enabled")),
            "alive": bool(_THREAD and _THREAD.is_alive()),
            "running": _RUNNING_JOB,
        }
    )
    return snap


def new_session_id() -> str:
    return f"kol_rt_{uuid.uuid4().hex[:10]}"


def _cutoff_hours_for_run(cfg: Optional[Dict[str, Any]] = None) -> int:
    """首轮拉满首窗（默认 8h），之后用较小增量窗（默认 2h，不超过配置时间窗）。"""
    cfg = cfg or get_config()
    cap = max(1, min(int(cfg.get("kol_realtime_cutoff_hours") or 8), 168))
    first = max(
        1,
        min(
            int(cfg.get("kol_realtime_first_hours") or cfg.get("first_crawl_hours") or 8),
            48,
        ),
    )
    inc = max(1, min(int(cfg.get("kol_realtime_incremental_hours") or 2), 24))
    inc = min(inc, cap)
    last = str(cfg.get("kol_realtime_last_crawl_at") or "").strip()
    if not last:
        return first
    return inc


def _run_once() -> Dict[str, Any]:
    global _RUNNING_JOB
    from signals.control import RunControl, register, unregister
    from signals.pipeline import run_kol_realtime_batch

    cfg = get_config()
    handles = [str(h).strip().lower() for h in (cfg.get("kol_realtime_handles") or []) if str(h).strip()]
    if not handles:
        return {"success": False, "error": "未选择 KOL"}

    with _LOCK:
        if _RUNNING_JOB:
            return {"success": False, "error": "已有一轮在跑"}
        _RUNNING_JOB = True

    job_id = f"kol_rt_{int(time.time())}"
    ctl = register(job_id, RunControl(job_id))
    _set_status(active_job_id=job_id)
    try:
        cutoff = _cutoff_hours_for_run(cfg)
        print(f"[kol-realtime] 时间窗≤{cutoff}h", flush=True)
        result = run_kol_realtime_batch(
            handles=handles,
            cutoff_hours=cutoff,
            max_tweets=int(cfg.get("kol_realtime_max_tweets") or 40),
            session_id=str(cfg.get("kol_realtime_session_id") or ""),
            push_enabled=bool(cfg.get("kol_realtime_push_enabled")),
            progress=lambda m: print(f"[kol-realtime] {m}", flush=True),
            control=ctl,
        )
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        if result.get("success"):
            save_config({"kol_realtime_last_crawl_at": now})
        _set_status(
            last_run_at=now,
            last_status="ok" if result.get("success") else "error",
            last_message=str(result.get("message") or result.get("error") or ""),
        )
        return result
    except Exception as e:
        traceback.print_exc()
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        _set_status(last_run_at=now, last_status="error", last_message=str(e))
        return {"success": False, "error": str(e)}
    finally:
        unregister(job_id)
        with _LOCK:
            _RUNNING_JOB = False
            _STATUS["active_job_id"] = ""


def _loop() -> None:
    print("[kol-realtime] 周期抓取已启动", flush=True)
    while not _STOP.is_set():
        cfg = get_config()
        if not cfg.get("kol_realtime_enabled"):
            _set_status(
                enabled=False,
                alive=True,
                next_wait_seconds=None,
                next_run_at=None,
                active_job_id="",
            )
            if _STOP.wait(5.0):
                break
            continue

        _run_once()
        if _STOP.is_set() or not get_config().get("kol_realtime_enabled"):
            continue

        cfg = get_config()
        wait = _interval_seconds(cfg)
        next_run = (datetime.now(timezone.utc).astimezone() + timedelta(seconds=wait)).isoformat(
            timespec="seconds"
        )
        _set_status(
            enabled=True,
            alive=True,
            next_wait_seconds=wait,
            next_run_at=next_run,
        )
        print(f"[kol-realtime] 下次约 {wait // 60} 分钟后（{next_run}）", flush=True)

        end = time.time() + wait
        while time.time() < end:
            if _STOP.is_set():
                break
            if not get_config().get("kol_realtime_enabled"):
                break
            chunk = min(15.0, max(1.0, end - time.time()))
            if _STOP.wait(chunk):
                break

    _set_status(alive=False, active_job_id="")
    print("[kol-realtime] 已停止", flush=True)


def start_kol_realtime_watcher(*, force: bool = False) -> Dict[str, Any]:
    global _THREAD
    cfg = get_config()
    if not force and not cfg.get("kol_realtime_enabled"):
        return status()
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return status()
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, name="kol-realtime", daemon=True)
        _THREAD.start()
    return status()


def stop_kol_realtime_watcher() -> Dict[str, Any]:
    _STOP.set()
    return status()


def set_kol_realtime(enabled: bool, *, new_session: bool = False) -> Dict[str, Any]:
    cfg = get_config()
    patch: Dict[str, Any] = {"kol_realtime_enabled": bool(enabled)}
    if enabled and new_session:
        sid = new_session_id()
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        patch["kol_realtime_session_id"] = sid
        patch["kol_realtime_session_started_at"] = now
        patch["kol_realtime_last_crawl_at"] = ""
    if not enabled:
        from signals.control import get as get_ctl

        jid = str(_STATUS.get("active_job_id") or "")
        if jid:
            ctl = get_ctl(jid)
            if ctl:
                ctl.stop()
    save_config(patch)
    if enabled:
        start_kol_realtime_watcher(force=True)
    else:
        stop_kol_realtime_watcher()
    return status()
