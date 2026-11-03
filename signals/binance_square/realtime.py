# coding=utf-8
"""币安 Square 实时抓取：bapi 优先、运行时 CDP Cookie、入库前补时间。"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

ProgressCb = Optional[Callable[[str], None]]


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)


def ensure_binance_session_for_realtime(
    progress: ProgressCb = None,
    *,
    debugger_url: str = "",
) -> bool:
    from signals.binance_square.session import resolve_binance_session, session_diagnostics, session_ready

    resolve_binance_session(debugger_url=debugger_url, progress=progress, force_refresh=False)
    if session_ready():
        diag = session_diagnostics()
        if not diag.get("has_fingerprint"):
            _log(
                progress,
                "提示：未检测到 device-info 等指纹头（可选）；若 bapi 返回空 data，"
                "请在 Chrome 打开 Square 时间线或在本机 session 文件补充 headers",
            )
        return True
    _log(
        progress,
        "Square 会话未就绪：请启动带 --remote-debugging-port 的 Chrome 并登录 binance.com",
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
