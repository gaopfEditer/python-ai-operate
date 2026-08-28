# coding=utf-8
"""列表信号后台监听：按北京时间分时频率触发 CDP 流水线。"""

from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from signals.schedule import estimate_daily_runs, next_wait_seconds, now_beijing, resolve_slot_id
from signals.store import get_config, save_config

_LOCK = threading.RLock()
_STOP = threading.Event()
_THREAD: Optional[threading.Thread] = None
_RUNNING_JOB = False
_STATUS: Dict[str, Any] = {
    "watch_enabled": False,
    "alive": False,
    "last_run_at": None,
    "last_status": None,
    "last_message": "",
    "last_result": None,
    "next": None,
    "slot_id": None,
}


def _set_status(**kwargs: Any) -> None:
    with _LOCK:
        _STATUS.update(kwargs)


def status() -> Dict[str, Any]:
    cfg = get_config()
    with _LOCK:
        snap = dict(_STATUS)
    deep_mode = str(cfg.get("deep_sleep_mode") or "sleep")
    nxt = next_wait_seconds(deep_mode=deep_mode)
    snap.update(
        {
            "watch_enabled": bool(cfg.get("watch_enabled")),
            "deep_sleep_mode": deep_mode,
            "alive": bool(_THREAD and _THREAD.is_alive()),
            "running": _RUNNING_JOB,
            "beijing_now": now_beijing().isoformat(timespec="seconds"),
            "slot_id": resolve_slot_id(),
            "next": nxt,
            "daily_estimate": estimate_daily_runs(deep_mode),
        }
    )
    return snap


def _run_once() -> Dict[str, Any]:
    global _RUNNING_JOB
    from signals.control import RunControl, register, unregister
    from signals.pipeline import run_list_signal_pipeline

    cfg = get_config()
    with _LOCK:
        if _RUNNING_JOB:
            return {"success": False, "error": "已有一轮在跑"}
        _RUNNING_JOB = True
    job_id = f"watch_{int(time.time())}"
    ctl = register(job_id, RunControl(job_id))
    try:
        result = run_list_signal_pipeline(
            list_id=str(cfg.get("list_id") or ""),
            cutoff_hours=int(cfg.get("cutoff_hours") or 24),
            max_tweets=int(cfg.get("max_tweets") or 40),
            ignore_windows=False,
            progress=lambda m: print(f"[signals-watch] {m}", flush=True),
            control=ctl,
        )
        _set_status(
            last_run_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            last_status="ok" if result.get("success") else "error",
            last_message=str(result.get("message") or result.get("error") or ""),
            last_result={
                "parsed": result.get("parsed"),
                "fetched": result.get("fetched"),
                "pushed": (result.get("push") or {}).get("pushed"),
                "success": result.get("success"),
                "aborted": result.get("aborted"),
            },
            active_job_id=job_id,
        )
        return result
    except Exception as e:
        traceback.print_exc()
        _set_status(
            last_run_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            last_status="error",
            last_message=str(e),
        )
        return {"success": False, "error": str(e)}
    finally:
        unregister(job_id)
        with _LOCK:
            _RUNNING_JOB = False
            _STATUS["active_job_id"] = ""


def _loop() -> None:
    print("[signals-watch] 分时监听已启动（北京时间阶梯频率）")
    while not _STOP.is_set():
        cfg = get_config()
        if not cfg.get("watch_enabled"):
            _set_status(watch_enabled=False, alive=True, next=None)
            if _STOP.wait(5.0):
                break
            continue

        deep_mode = str(cfg.get("deep_sleep_mode") or "sleep")
        plan = next_wait_seconds(deep_mode=deep_mode)
        _set_status(
            watch_enabled=True,
            alive=True,
            next=plan,
            slot_id=plan.get("slot_id"),
        )
        wait = int(plan.get("wait_seconds") or 60)
        print(
            f"[signals-watch] 时段={plan.get('slot_id')} "
            f"等待 {plan.get('wait_minutes')} 分 · {plan.get('reason')}"
        )

        # 分段 sleep，便于停用/停止
        end = time.time() + wait
        while time.time() < end:
            if _STOP.is_set():
                break
            cfg2 = get_config()
            if not cfg2.get("watch_enabled"):
                break
            # 若跨入新时段且剩余很长，可提前重算（每 60s 看一次）
            remain = end - time.time()
            if remain > 90:
                new_plan = next_wait_seconds(
                    deep_mode=str(cfg2.get("deep_sleep_mode") or "sleep")
                )
                if new_plan.get("slot_id") != plan.get("slot_id"):
                    print(
                        f"[signals-watch] 时段切换 {plan.get('slot_id')} → {new_plan.get('slot_id')}，重算等待"
                    )
                    break
            chunk = min(30.0, max(1.0, remain))
            if _STOP.wait(chunk):
                break
        else:
            # 正常等到点
            cfg3 = get_config()
            if not cfg3.get("watch_enabled") or _STOP.is_set():
                continue
            plan2 = next_wait_seconds(
                deep_mode=str(cfg3.get("deep_sleep_mode") or "sleep")
            )
            if plan2.get("sleeping"):
                # 仍在休眠窗（边界抖动），不跑
                continue
            print("[signals-watch] 触发 CDP 列表抓取…")
            _run_once()

    _set_status(alive=False)
    print("[signals-watch] 已停止")


def start_watcher(*, force: bool = False) -> Dict[str, Any]:
    """启动后台线程（幂等）。force=True 时即使未启用也拉起线程待命。"""
    global _THREAD
    cfg = get_config()
    if not force and not cfg.get("watch_enabled"):
        return status()
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return status()
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, name="signals-watch", daemon=True)
        _THREAD.start()
    return status()


def stop_watcher() -> Dict[str, Any]:
    _STOP.set()
    return status()


def set_watch(enabled: bool, *, deep_sleep_mode: Optional[str] = None) -> Dict[str, Any]:
    patch: Dict[str, Any] = {"watch_enabled": bool(enabled)}
    if deep_sleep_mode is not None:
        mode = str(deep_sleep_mode).strip().lower()
        if mode not in ("sleep", "patrol"):
            mode = "sleep"
        patch["deep_sleep_mode"] = mode
    save_config(patch)
    if enabled:
        start_watcher(force=True)
    return status()
