# coding=utf-8
"""Uvicorn 访问日志过滤：WhisprRT 仅保留文字稿相关 HTTP 行。"""

from __future__ import annotations

import logging

# 访问日志里保留的 WhisprRT 路径（保存/字幕/启停转写）
_WHISPRRT_TRANSCRIPT_MARKERS = (
    "/whisprrt/save",
    "/whisprrt/youtube/subtitles",
    "/whisprrt/start",
    "/whisprrt/stop",
)


def whisprrt_access_should_log(message: str) -> bool:
    if "/whisprrt" not in message:
        return True
    return any(marker in message for marker in _WHISPRRT_TRANSCRIPT_MARKERS)


class ConsoleAccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        return whisprrt_access_should_log(msg)


def attach_console_access_log_filter() -> None:
    logging.getLogger("uvicorn.access").addFilter(ConsoleAccessLogFilter())
