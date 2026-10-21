# coding=utf-8
"""列表信号后台周期任务：配置开启但线程已退出时自动拉起。"""

from __future__ import annotations

from typing import Any, Dict


def ensure_signal_background_watchers() -> Dict[str, Any]:
    """若配置为开启且 watcher 线程未存活，则重新 start（幂等）。"""
    out: Dict[str, Any] = {}
    try:
        from signals.store import get_config
        from signals.watcher import start_watcher, status as watch_status

        cfg = get_config() or {}
        if cfg.get("watch_enabled"):
            st = watch_status()
            if not st.get("alive"):
                start_watcher(force=True)
        out["watch"] = watch_status()
    except Exception as e:
        out["watch_error"] = str(e)

    try:
        from signals.cycle_watcher import start_cycle_watcher, status as cycle_status
        from signals.store import get_config

        cfg = get_config() or {}
        if cfg.get("cycle_enabled"):
            st = cycle_status()
            if not st.get("alive"):
                start_cycle_watcher(force=True)
        out["list_cycle"] = cycle_status()
    except Exception as e:
        out["list_cycle_error"] = str(e)

    try:
        from signals.kol_realtime_watcher import (
            start_kol_realtime_watcher,
            status as kol_rt_status,
        )
        from signals.store import get_config

        cfg = get_config() or {}
        if cfg.get("kol_realtime_enabled"):
            st = kol_rt_status()
            if not st.get("alive"):
                start_kol_realtime_watcher(force=True)
        out["kol_realtime"] = kol_rt_status()
    except Exception as e:
        out["kol_realtime_error"] = str(e)

    try:
        from signals.binance_square.cycle_watcher import (
            start_cycle_watcher as start_bs_cycle,
            status as bs_cycle_status,
        )
        from signals.binance_square.store import load_config

        bc = load_config() or {}
        if bc.get("cycle_enabled"):
            st = bs_cycle_status()
            if not st.get("alive"):
                start_bs_cycle(force=True)
        out["binance_square_cycle"] = bs_cycle_status()
    except Exception as e:
        out["binance_square_cycle_error"] = str(e)

    return out
