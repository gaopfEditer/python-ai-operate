# coding=utf-8
"""币安 bapi 与推特 CDP 抓取互斥，避免同时抢 9223。"""
from __future__ import annotations

import threading

_LOCK = threading.Lock()


def signals_fetch_lock() -> threading.Lock:
    return _LOCK
