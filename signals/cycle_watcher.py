# coding=utf-8
"""列表信号周期抓取：5–15 分钟随机间隔，增量去重。"""

from __future__ import annotations

import random
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from signals.store import get_config, latest_window_end, save_config

_LOCK = threading.RLock()
_STOP = threading.Event()
_THREAD: Optional[threading.Thread] = None
_RUNNING_JOB = False
_STATUS: Dict[str, Any] = {
    "cycle_enabled": False,
    "alive": False,
    "last_run_at": None,
    "last_status": None,
    "last_message": "",
    "next_wait_seconds": None,
    "next_run_at": None,
}


def _set_status(**kwargs: Any) -> None:
    with _LOCK:
        _STATUS.update(kwargs)


def is_first_list_crawl(list_id: str, cfg: Optional[Dict[str, Any]] = None) -> bool:
    """无上次爬取记录且无历史时间窗 → 视为首次（最多拉 first_crawl_hours）。"""
    cfg = cfg or get_config()
    if str(cfg.get("last_crawl_at") or "").strip():
        return False
    lid = str(list_id or cfg.get("list_id") or "").strip()
    if lid and latest_window_end(lid) is not None:
        return False
    return True


def next_cycle_wait_seconds(cfg: Optional[Dict[str, Any]] = None) -> int:
    cfg = cfg or get_config()
    lo = max(1, int(cfg.get("cycle_min_minutes") or 5))
    hi = max(lo, int(cfg.get("cycle_max_minutes") or 15))
    return random.randint(lo * 60, hi * 60)


def status() -> Dict[str, Any]:
    cfg = get_config()
    with _LOCK:
        snap = dict(_STATUS)
    snap.update(
        {
            "cycle_enabled": bool(cfg.get("cycle_enabled")),
            "last_crawl_at": cfg.get("last_crawl_at"),
            "first_crawl_hours": int(cfg.get("first_crawl_hours") or 8),
            "cycle_min_minutes": int(cfg.get("cycle_min_minutes") or 5),
            "cycle_max_minutes": int(cfg.get("cycle_max_minutes") or 15),
            "alive": bool(_THREAD and _THREAD.is_alive()),
            "running": _RUNNING_JOB,
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

    lid = str(cfg.get("list_id") or "")
    first = is_first_list_crawl(lid, cfg)
    first_hours = max(1, min(int(cfg.get("first_crawl_hours") or 8), 48))
    cutoff = first_hours if first else max(1, min(int(cfg.get("cutoff_hours") or 8), 24))

    job_id = f"cycle_{int(time.time())}"
    ctl = register(job_id, RunControl(job_id))
    tag = "首次" if first else "增量"
    print(f"[signals-cycle] 开始{tag}抓取 · 时间窗≤{cutoff}h", flush=True)
    try:
        result = run_list_signal_pipeline(
            list_id=lid,
            cutoff_hours=cutoff,
            max_tweets=int(cfg.get("max_tweets") or 40),
            skip_non_trade=bool(cfg.get("skip_non_trade")),
            push=bool(cfg.get("push_enabled", True)),
            ignore_windows=False,
            reparse_seen=False,
            progress=lambda m: print(f"[signals-cycle] {m}", flush=True),
            control=ctl,
        )
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        save_config({"last_crawl_at": now})
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


def _loop() -> None:
    print("[signals-cycle] 周期抓取已启动（5–15 分钟随机间隔）", flush=True)
    while not _STOP.is_set():
        cfg = get_config()
        if not cfg.get("cycle_enabled"):
            _set_status(cycle_enabled=False, alive=True, next_wait_seconds=None, next_run_at=None)
            if _STOP.wait(5.0):
                break
            continue

        _run_once()
        if _STOP.is_set() or not get_config().get("cycle_enabled"):
            continue

        cfg = get_config()
        wait = next_cycle_wait_seconds(cfg)
        from datetime import timedelta

        next_run = (datetime.now(timezone.utc).astimezone() + timedelta(seconds=wait)).isoformat(
            timespec="seconds"
        )
        _set_status(
            cycle_enabled=True,
            alive=True,
            next_wait_seconds=wait,
            next_run_at=next_run,
        )
        print(
            f"[signals-cycle] 下次抓取约 {wait // 60} 分 {wait % 60} 秒后（{next_run}）",
            flush=True,
        )

        end = time.time() + wait
        while time.time() < end:
            if _STOP.is_set():
                break
            if not get_config().get("cycle_enabled"):
                break
            chunk = min(15.0, max(1.0, end - time.time()))
            if _STOP.wait(chunk):
                break

    _set_status(alive=False)
    print("[signals-cycle] 已停止", flush=True)


def start_cycle_watcher(*, force: bool = False) -> Dict[str, Any]:
    global _THREAD
    cfg = get_config()
    if not force and not cfg.get("cycle_enabled"):
        return status()
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return status()
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, name="signals-cycle", daemon=True)
        _THREAD.start()
    return status()


def stop_cycle_watcher() -> Dict[str, Any]:
    _STOP.set()
    return status()


def set_cycle(enabled: bool) -> Dict[str, Any]:
    save_config({"cycle_enabled": bool(enabled)})
    if enabled:
        start_cycle_watcher(force=True)
    return status()
