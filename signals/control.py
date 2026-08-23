# coding=utf-8
"""列表信号运行控制：暂停 / 继续 / 终止。"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

class RunControl:
    """可在流水线循环中轮询的暂停/终止开关。"""

    def __init__(self, job_id: str = ""):
        self.job_id = job_id or ""
        self._pause = threading.Event()  # set = 暂停中
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    def stop(self) -> None:
        self._stop.set()
        self._pause.clear()  # 解除 pause 等待以便尽快退出

    def is_paused(self) -> bool:
        return self._pause.is_set() and not self._stop.is_set()

    def is_stopped(self) -> bool:
        return self._stop.is_set()

    def status(self) -> str:
        if self._stop.is_set():
            return "stopped"
        if self._pause.is_set():
            return "paused"
        return "running"

    def check(self, *, poll_s: float = 0.35) -> str:
        """
        阻塞直到非暂停；若已终止返回 "stop"，否则 "ok"。
        """
        while True:
            if self._stop.is_set():
                return "stop"
            if not self._pause.is_set():
                return "ok"
            time.sleep(max(0.1, poll_s))


_REGISTRY: Dict[str, RunControl] = {}
_REG_LOCK = threading.Lock()
_ACTIVE_JOB: str = ""


def register(job_id: str, control: Optional[RunControl] = None) -> RunControl:
    global _ACTIVE_JOB
    ctl = control or RunControl(job_id)
    with _REG_LOCK:
        _REGISTRY[job_id] = ctl
        _ACTIVE_JOB = job_id
    return ctl


def unregister(job_id: str) -> None:
    global _ACTIVE_JOB
    with _REG_LOCK:
        _REGISTRY.pop(job_id, None)
        if _ACTIVE_JOB == job_id:
            _ACTIVE_JOB = ""


def get(job_id: str) -> Optional[RunControl]:
    with _REG_LOCK:
        return _REGISTRY.get(job_id)


def active_job_id() -> str:
    with _REG_LOCK:
        return _ACTIVE_JOB


def control_action(job_id: str, action: str) -> Dict[str, Any]:
    action = (action or "").strip().lower()
    ctl = get(job_id)
    if not ctl:
        if not job_id:
            jid = active_job_id()
            ctl = get(jid) if jid else None
            job_id = jid
        if not ctl:
            return {"success": False, "error": "没有进行中的任务", "job_id": job_id or ""}
    if action == "pause":
        ctl.pause()
    elif action in ("resume", "continue"):
        ctl.resume()
    elif action in ("stop", "cancel", "abort"):
        ctl.stop()
    else:
        return {"success": False, "error": f"未知操作: {action}", "job_id": job_id}
    return {"success": True, "job_id": job_id, "status": ctl.status()}
