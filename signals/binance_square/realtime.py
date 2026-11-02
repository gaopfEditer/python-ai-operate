# coding=utf-8
"""币安 Square 实时抓取：bapi 优先、会话校验、入库前补时间。"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

ProgressCb = Optional[Callable[[str], None]]


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)


def ensure_binance_session_for_realtime(progress: ProgressCb = None) -> bool:
    from signals.binance_square.session import load_binance_session, session_diagnostics, session_ready

    if session_ready():
        diag = session_diagnostics()
        if not diag.get("has_fingerprint"):
            _log(
                progress,
                "提示：Square session 缺少 device-info 等指纹头，bapi 可能返回空 data；"
                "请在 Square 页滚动后重跑 bootstrap_binance_session_from_cdp.py",
            )
        return True
    _log(
        progress,
        "Square session 未配置：请运行 scripts/bootstrap_binance_session_from_cdp.py "
        "或写入 output/signals/binance_square_session.json",
    )
    return False


def enrich_publish_times_before_filter(
    posts: List[Dict[str, Any]],
    *,
    limit: int = 16,
    progress: ProgressCb = None,
) -> List[Dict[str, Any]]:
    from signals.binance_square.time_detail import enrich_posts_time_from_detail

    if not posts:
        return posts
    return enrich_posts_time_from_detail(posts, limit=limit, progress=progress)
