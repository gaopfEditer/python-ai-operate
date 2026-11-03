# coding=utf-8
"""出站 HTTP：按本地 VPN 端口顺序尝试代理（7890 → 7891），本机 CDP 等直连。"""
from __future__ import annotations

import errno
import logging
import os
import socket
import urllib.error
import urllib.request
from typing import List, Optional, Sequence, Union
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_ENV_KEY = "AI_OPERATE_HTTP_PROXIES"
_DEFAULT_PROXIES: Sequence[str] = (
    "http://127.0.0.1:7890",
    "http://127.0.0.1:7891",
)
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


def parse_vpn_proxy_list() -> List[str]:
    raw = os.environ.get(_ENV_KEY, "").strip()
    if raw:
        return [p.strip() for p in raw.split(",") if p.strip()]
    return list(_DEFAULT_PROXIES)


def should_use_vpn_proxy(url: str) -> bool:
    """本机调试端口（CDP 等）不走 VPN 代理。"""
    text = str(url or "").strip()
    if not text:
        return True
    try:
        parsed = urlparse(text if "://" in text else f"http://{text}")
    except Exception:
        return True
    host = (parsed.hostname or "").lower()
    if not host:
        return True
    if host in _LOCAL_HOSTS:
        return False
    if host.endswith(".local"):
        return False
    try:
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        packed = socket.inet_pton(socket.AF_INET, host)
        if packed.startswith(b"\x7f"):
            return False
    except OSError:
        pass
    try:
        packed6 = socket.inet_pton(socket.AF_INET6, host)
        if packed6 == socket.inet_pton(socket.AF_INET6, "::1"):
            return False
    except OSError:
        pass
    return True


def _request_url(req: Union[urllib.request.Request, str]) -> str:
    if isinstance(req, str):
        return req
    if hasattr(req, "full_url"):
        return str(req.full_url)
    return str(req.get_full_url())


def _is_proxy_connect_failure(exc: BaseException) -> bool:
    seen: set[int] = set()
    cur: Optional[BaseException] = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, ConnectionRefusedError):
            return True
        if isinstance(cur, OSError):
            if cur.errno in (errno.ECONNREFUSED,):
                return True
        msg = str(cur).lower()
        if "connection refused" in msg or "connect refused" in msg:
            return True
        if "proxy" in msg and ("refused" in msg or "cannot connect" in msg):
            return True
        nxt: Optional[BaseException] = None
        reason = getattr(cur, "reason", None)
        if isinstance(reason, BaseException):
            nxt = reason
        if nxt is None:
            nxt = cur.__cause__ if isinstance(cur.__cause__, BaseException) else None
        if nxt is None:
            nxt = cur.__context__ if isinstance(cur.__context__, BaseException) else None
        cur = nxt
    return False


def _direct_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _proxy_opener(proxy: str) -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    )


def urlopen(
    req: Union[urllib.request.Request, str],
    timeout: Optional[float] = None,
    *,
    context=None,
):
    """
    对外 URL：依次尝试 AI_OPERATE_HTTP_PROXIES（默认 7890、7891）。
    本机 URL：强制直连，忽略系统 HTTP_PROXY。
    """
    url = _request_url(req)
    if not should_use_vpn_proxy(url):
        opener = _direct_opener()
        return opener.open(req, timeout=timeout)

    proxies = parse_vpn_proxy_list()
    last_err: Optional[BaseException] = None
    for idx, proxy in enumerate(proxies):
        opener = _proxy_opener(proxy)
        try:
            resp = opener.open(req, timeout=timeout)
            if idx > 0:
                logger.info("HTTP 经代理 %s 成功（前一端口不可用）", proxy)
            return resp
        except (urllib.error.URLError, OSError) as e:
            if not _is_proxy_connect_failure(e):
                raise
            last_err = e
            if idx + 1 < len(proxies):
                nxt = proxies[idx + 1]
                logger.info(
                    "HTTP 代理 %s 连接失败（%s），改试 %s",
                    proxy,
                    e,
                    nxt,
                )
            continue
    if last_err is not None:
        raise last_err
    raise urllib.error.URLError("无可用 HTTP 代理配置")
