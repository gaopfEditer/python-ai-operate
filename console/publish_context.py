# coding=utf-8
"""当前线程 CDP 发布任务的控制句柄（用于深度 CDP 循环里响应终止）。"""

from __future__ import annotations

import threading
from typing import Optional

from signals.control import RunControl

_tls = threading.local()


def bind_run_control(ctl: Optional[RunControl]) -> None:
    _tls.ctl = ctl


def clear_run_control() -> None:
    _tls.ctl = None


def abort_requested() -> bool:
    ctl = getattr(_tls, "ctl", None)
    return bool(ctl and ctl.is_stopped())
