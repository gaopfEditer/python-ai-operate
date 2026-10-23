# coding=utf-8
"""币安 Square 周期抓取：5–15 分钟随机间隔，按小时窗增量。"""

from __future__ import annotations

import random
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from signals.binance_square.store import load_config, load_state, save_config

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
    "active_job_id": "",
}


def _set_status(**kwargs: Any) -> None:
    with _LOCK:
        _STATUS.update(kwargs)


def is_first_bs_crawl(cfg: Optional[Dict[str, Any]] = None) -> bool:
    cfg = cfg or load_config()
    if str(cfg.get("last_crawl_at") or "").strip():
        return False
    st = load_state()
    if str(st.get("last_run_at") or "").strip():
        return False
    return True


def next_cycle_wait_seconds(cfg: Optional[Dict[str, Any]] = None) -> int:
    cfg = cfg or load_config()
    lo = max(1, int(cfg.get("cycle_min_minutes") or 5))
    hi = max(lo, int(cfg.get("cycle_max_minutes") or 15))
    return random.randint(lo * 60, hi * 60)


def status() -> Dict[str, Any]:
    cfg = load_config()
    with _LOCK:
        snap = dict(_STATUS)
    snap.update(
        {
            "cycle_enabled": bool(cfg.get("cycle_enabled")),
            "last_crawl_at": cfg.get("last_crawl_at"),
            "first_crawl_hours": int(cfg.get("first_crawl_hours") or 8),
            "cycle_cutoff_hours": int(cfg.get("cycle_cutoff_hours") or 8),
            "cycle_min_minutes": int(cfg.get("cycle_min_minutes") or 5),
            "cycle_max_minutes": int(cfg.get("cycle_max_minutes") or 15),
            "alive": bool(_THREAD and _THREAD.is_alive()),
            "running": _RUNNING_JOB,
        }
    )
    if not _RUNNING_JOB:
        snap["active_job_id"] = ""
    return snap


def _maybe_whisper(posts: list, cfg: Dict[str, Any]) -> None:
    if not cfg.get("replay_whisper_auto"):
        return
    if not posts:
        return
    try:
        from signals.binance_square.replay_whisper import posts_with_replay, start_replay_whisper_jobs

        max_days = float(cfg.get("replay_whisper_max_days") or 2)
        eligible = posts_with_replay(posts, max_age_days=max_days)
        if eligible:
            start_replay_whisper_jobs(posts, max_age_days=max_days)
            print(f"[bs-square-cycle] 已提交 {len(eligible)} 个回放转写", flush=True)
    except Exception as e:
        print(f"[bs-square-cycle] 转写排队跳过: {e}", flush=True)


def _run_once() -> Dict[str, Any]:
    global _RUNNING_JOB
    from signals.binance_square.crawl import run_binance_square_fetch
    from signals.control import RunControl, register, unregister

    cfg = load_config()
    with _LOCK:
        if _RUNNING_JOB:
            return {"success": False, "error": "已有一轮在跑"}
        _RUNNING_JOB = True

    first = is_first_bs_crawl(cfg)
    first_hours = max(1, min(int(cfg.get("first_crawl_hours") or 8), 48))
    cycle_h = max(1, min(int(cfg.get("cycle_cutoff_hours") or 8), 48))
    cutoff = first_hours if first else cycle_h

    job_id = f"bs_cycle_{int(time.time())}"
    ctl = register(job_id, RunControl(job_id))
    _set_status(active_job_id=job_id)
    tag = "首次" if first else "增量"
    print(f"[bs-square-cycle] 开始{tag}抓取 · 时间窗≤{cutoff}h", flush=True)
    try:
        result = run_binance_square_fetch(
            profile_ids=None,
            debugger_url=str(cfg.get("debugger_url") or "").strip() or None,
            cutoff_hours=cutoff,
            max_posts_per_profile=int(cfg.get("max_posts_per_profile") or 40),
            try_bapi=bool(cfg.get("try_bapi_first")),
            progress=lambda m: print(f"[bs-square-cycle] {m}", flush=True),
            control=ctl,
        )
        posts = result.get("posts") if isinstance(result.get("posts"), list) else []
        if result.get("success") and posts:
            _maybe_whisper(posts, cfg)
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        if result.get("success"):
            save_config({**load_config(), "last_crawl_at": now})
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
    print("[bs-square-cycle] 周期抓取已启动（5–15 分钟随机间隔）", flush=True)
    while not _STOP.is_set():
        cfg = load_config()
        if not cfg.get("cycle_enabled"):
            _set_status(
                cycle_enabled=False,
                alive=True,
                next_wait_seconds=None,
                next_run_at=None,
                active_job_id="",
            )
            if _STOP.wait(5.0):
                break
            continue

        _run_once()
        if _STOP.is_set() or not load_config().get("cycle_enabled"):
            continue

        cfg = load_config()
        wait = next_cycle_wait_seconds(cfg)
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
            f"[bs-square-cycle] 下次抓取约 {wait // 60} 分 {wait % 60} 秒后（{next_run}）",
            flush=True,
        )

        end = time.time() + wait
        while time.time() < end:
            if _STOP.is_set():
                break
            if not load_config().get("cycle_enabled"):
                break
            chunk = min(15.0, max(1.0, end - time.time()))
            if _STOP.wait(chunk):
                break

    _set_status(alive=False, active_job_id="")
    print("[bs-square-cycle] 已停止", flush=True)


def start_cycle_watcher(*, force: bool = False) -> Dict[str, Any]:
    global _THREAD
    cfg = load_config()
    if not force and not cfg.get("cycle_enabled"):
        return status()
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return status()
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, name="bs-square-cycle", daemon=True)
        _THREAD.start()
    return status()


def stop_cycle_watcher() -> Dict[str, Any]:
    _STOP.set()
    return status()


def set_cycle(enabled: bool) -> Dict[str, Any]:
    cfg = load_config()
    cfg["cycle_enabled"] = bool(enabled)
    save_config(cfg)
    if enabled:
        start_cycle_watcher(force=True)
    else:
        stop_cycle_watcher()
    return status()
