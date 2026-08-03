# coding=utf-8
"""按平台配置的抓取频率自动调度。"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import List, Optional

from allnews_mornitor.platforms import loader  # noqa: F401
from allnews_mornitor.platforms import list_platforms
from allnews_mornitor.pipeline import run_crawl

_STOP = threading.Event()
_THREAD: Optional[threading.Thread] = None
_LOCK = threading.Lock()


def _due_platforms() -> List[str]:
    now = datetime.now()
    due = []
    for p in list_platforms():
        if not p.get("enabled"):
            continue
        interval = int(p.get("crawl_interval_min") or 60)
        last = str(p.get("last_crawl_at") or "").strip()
        if not last:
            due.append(p["id"])
            continue
        try:
            ts = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            due.append(p["id"])
            continue
        if (now - ts).total_seconds() >= interval * 60:
            due.append(p["id"])
    return due


def _loop() -> None:
    while not _STOP.wait(30):
        try:
            due = _due_platforms()
            if not due:
                continue
            print(f"[allnews-sched] 到期平台: {due}")
            run_crawl(due)
        except Exception as e:
            print(f"[allnews-sched] 失败: {e}")


def start_scheduler() -> None:
    global _THREAD
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, name="allnews-sched", daemon=True)
        _THREAD.start()
        print("[allnews-sched] 已启动（按平台 crawl_interval_min）")


def stop_scheduler() -> None:
    _STOP.set()
