# coding=utf-8
"""Uvicorn 访问日志：压低轮询与健康检查噪音，保留写操作与失败请求。"""

from __future__ import annotations

import logging
import re

_ACCESS_LINE = re.compile(r'"([A-Z]+) ([^"? ]+)(?:\?[^"]*)? HTTP/1\.[01]" (\d{3})')

# WhisprRT：仅保留文字稿相关
_WHISPRRT_TRANSCRIPT_MARKERS = (
    "/whisprrt/save",
    "/whisprrt/youtube/subtitles",
    "/whisprrt/start",
    "/whisprrt/stop",
)

# 仍显式屏蔽的 GET（即便将来放宽 /api/ 规则）
_NOISY_GET_EXACT_OR_PREFIX = (
    "/api/health",
    "/api/jobs/",
    "/api/publish/queue",
    "/api/signals/binance-square/cycle",
    "/api/signals/cycle",
    "/api/signals/kol-realtime",
    "/api/signals/config",
    "/api/corpus/",
    "/api/realtime/",
)

_STATIC_SUFFIXES = (
    ".js",
    ".css",
    ".map",
    ".ico",
    ".png",
    ".jpg",
    ".svg",
    ".woff",
    ".woff2",
)


def _path_from_access_message(message: str) -> tuple[str, str, int] | None:
    m = _ACCESS_LINE.search(message)
    if not m:
        return None
    return m.group(1), m.group(2), int(m.group(3))


def console_access_should_log(message: str) -> bool:
    method, path, status = _path_from_access_message(message) or ("", "", 0)

    if "/whisprrt" in message:
        if status >= 400:
            return True
        return any(marker in message for marker in _WHISPRRT_TRANSCRIPT_MARKERS)

    # 任务轮询打到已清理的 job（如 bs_cycle_*）时不刷屏
    if path.startswith("/api/jobs/") and status in (404, 410):
        return False

    if status >= 400:
        return True

    if method and method != "GET":
        return True

    if not path:
        return False

    for suf in _STATIC_SUFFIXES:
        if path.endswith(suf):
            return False

    if path in ("/", "/index.html", "/favicon.ico"):
        return False

    for prefix in _NOISY_GET_EXACT_OR_PREFIX:
        if path == prefix.rstrip("/") or path.startswith(prefix):
            return False

    # 成功 GET /api/* 一律不记（前端轮询、刷卡片等）
    if path.startswith("/api/"):
        return False

    return False


class ConsoleAccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return False
        return console_access_should_log(msg)


def attach_console_access_log_filter() -> None:
    logging.getLogger("uvicorn.access").addFilter(ConsoleAccessLogFilter())
