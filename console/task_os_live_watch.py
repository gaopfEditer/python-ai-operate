# coding=utf-8
"""Console 内嵌：task-os「实时关注」增量同步与整点调度。"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("task_os_live_watch")

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_SCHED_LOCK = threading.Lock()
_SCHED_THREAD: Optional[threading.Thread] = None
_SCHED_STOP = threading.Event()
_LAST_SLOT_KEY: Optional[str] = None


def _import_sync():
    from scripts import task_os_live_watch_sync as mod

    return mod


def _now() -> datetime:
    mod = _import_sync()
    return mod.now_local()


def next_slot_boundary(ref: Optional[datetime] = None) -> Tuple[datetime, int]:
    """下一次整点档位及对应 slot（0/8/12/16/20）。"""
    mod = _import_sync()
    ref = (ref or _now()).replace(second=0, microsecond=0)
    today: date = ref.date()
    for s in sorted(mod.SLOT_ORDER):
        cand = datetime.combine(today, dt_time(hour=s, minute=0), tzinfo=mod.TZ)
        if cand > ref:
            return cand, s
    tomorrow = today + timedelta(days=1)
    return datetime.combine(tomorrow, dt_time(hour=0, minute=0), tzinfo=mod.TZ), 0


def load_status() -> Dict[str, Any]:
    mod = _import_sync()
    cfg = mod.load_config()
    state_path = mod.expand_path(str(cfg["state_path"]), mod.ROOT)
    out: Dict[str, Any] = {
        "scheduler_enabled": bool(cfg.get("scheduler_enabled", True)),
        "git_push": bool(cfg.get("git_push", True)),
        "slots": list(cfg.get("slots") or mod.SLOT_ORDER),
        "last_run": None,
        "last_slot": None,
        "last_added": None,
    }
    nxt, slot = next_slot_boundary()
    out["next_run_at"] = nxt.isoformat(timespec="seconds")
    out["next_slot"] = slot
    if state_path.is_file():
        try:
            st = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(st, dict):
                out["last_run"] = st.get("last_run")
                out["last_slot"] = st.get("last_slot")
                out["last_added"] = st.get("added")
        except Exception:
            pass
    return out


def run_sync(
    *,
    slot: Optional[int] = None,
    push: Optional[bool] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    mod = _import_sync()
    cfg = mod.load_config()
    do_push = bool(cfg.get("git_push", True)) if push is None else bool(push)
    with _SCHED_LOCK:
        return mod.run_sync(slot=slot, dry_run=dry_run, push=do_push, cfg=cfg)


def _scheduler_loop() -> None:
    global _LAST_SLOT_KEY
    mod = _import_sync()
    while not _SCHED_STOP.is_set():
        try:
            cfg = mod.load_config()
            if not bool(cfg.get("scheduler_enabled", True)):
                if _SCHED_STOP.wait(60.0):
                    break
                continue
            nxt, slot = next_slot_boundary()
            logger.info("task-os live_watch 下次 %s slot=%s", nxt.isoformat(timespec="seconds"), slot)
            while not _SCHED_STOP.is_set() and _now() < nxt:
                remain = max(1.0, (nxt - _now()).total_seconds())
                if _SCHED_STOP.wait(min(60.0, remain)):
                    break
            if _SCHED_STOP.is_set():
                break
            slot_label = f"{nxt.date().isoformat()}T{slot:02d}:00+08:00"
            if _LAST_SLOT_KEY == slot_label:
                if _SCHED_STOP.wait(30.0):
                    break
                continue
            rep = run_sync(slot=slot, push=None)
            _LAST_SLOT_KEY = slot_label
            logger.info(
                "task-os live_watch 完成 slot=%s added=%s push=%s",
                slot,
                rep.get("added"),
                (rep.get("git_push") or {}).get("message"),
            )
        except Exception:
            logger.exception("task-os live_watch 调度异常")
            if _SCHED_STOP.wait(60.0):
                break


def start_scheduler() -> bool:
    """启动整点调度线程；已运行则跳过。返回本次是否新启动。"""
    global _SCHED_THREAD
    mod = _import_sync()
    if not bool(mod.load_config().get("scheduler_enabled", True)):
        return False
    if _SCHED_THREAD and _SCHED_THREAD.is_alive():
        return False
    _SCHED_STOP.clear()
    _SCHED_THREAD = threading.Thread(
        target=_scheduler_loop, name="task-os-live-watch", daemon=True
    )
    _SCHED_THREAD.start()
    return True


def stop_scheduler() -> None:
    _SCHED_STOP.set()