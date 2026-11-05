# coding=utf-8
"""出站 HTTP：按本地 VPN 端口顺序尝试代理（7890 → 7891），本机 CDP 等直连。"""
from __future__ import annotations

import errno
import logging
import os
import socket
import ssl
import time
import urllib.error
import urllib.request
from typing import List, Optional, Sequence, Union
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_ENV_KEY = "AI_OPERATE_HTTP_PROXIES"
# Clash Verge 默认 mixed-port 为 7890；7891 常未监听。优先 7890，失败再试 7891。
_DEFAULT_PROXIES: Sequence[str] = (
    "http://127.0.0.1:7890",
    "http://127.0.0.1:7891",
)
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})

_ENV_PER_PROXY_RETRIES = "AI_OPERATE_HTTP_RETRIES"
_DEFAULT_PER_PROXY_RETRIES = 2
_ENV_RETRY_BACKOFF = "AI_OPERATE_HTTP_RETRY_BACKOFF_SEC"
_DEFAULT_RETRY_BACKOFF_SEC = 0.35


def parse_vpn_proxy_list() -> List[str]:
    raw = os.environ.get(_ENV_KEY, "").strip()
    if raw:
        return [p.strip() for p in raw.split(",") if p.strip()]
    return list(_DEFAULT_PROXIES)


def _per_proxy_retries() -> int:
    raw = str(os.environ.get(_ENV_PER_PROXY_RETRIES) or _DEFAULT_PER_PROXY_RETRIES).strip()
    try:
        return max(1, min(int(raw), 5))
    except ValueError:
        return _DEFAULT_PER_PROXY_RETRIES


def _retry_backoff_sec() -> float:
    raw = str(os.environ.get(_ENV_RETRY_BACKOFF) or _DEFAULT_RETRY_BACKOFF_SEC).strip()
    try:
        return max(0.05, min(float(raw), 3.0))
    except ValueError:
        return _DEFAULT_RETRY_BACKOFF_SEC


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


def _iter_exception_chain(exc: BaseException):
    seen: set[int] = set()
    cur: Optional[BaseException] = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        yield cur
        nxt: Optional[BaseException] = None
        reason = getattr(cur, "reason", None)
        if isinstance(reason, BaseException):
            nxt = reason
        if nxt is None:
            nxt = cur.__cause__ if isinstance(cur.__cause__, BaseException) else None
        if nxt is None:
            nxt = cur.__context__ if isinstance(cur.__context__, BaseException) else None
        cur = nxt


def _is_proxy_connect_failure(exc: BaseException) -> bool:
    for cur in _iter_exception_chain(exc):
        if isinstance(cur, ConnectionRefusedError):
            return True
        if isinstance(cur, OSError):
            if cur.errno in (errno.ECONNREFUSED, errno.ECONNRESET, errno.ENETUNREACH, errno.EHOSTUNREACH):
                return True
        if isinstance(cur, TimeoutError):
            return True
        if isinstance(cur, socket.timeout):
            return True
        msg = str(cur).lower()
        if "connection refused" in msg or "connect refused" in msg:
            return True
        if "proxy" in msg and ("refused" in msg or "cannot connect" in msg or "failed to establish" in msg):
            return True
        if "timed out" in msg and "connect" in msg:
            return True
    return False


def _is_transient_network_failure(exc: BaseException) -> bool:
    """代理已可达后的短暂断连 / SSL 抖动 / 读超时等。"""
    if _is_proxy_connect_failure(exc):
        return True
    for cur in _iter_exception_chain(exc):
        if isinstance(cur, ssl.SSLError):
            return True
        if isinstance(cur, BrokenPipeError):
            return True
        if isinstance(cur, ConnectionResetError):
            return True
        if isinstance(cur, OSError):
            if cur.errno in (
                errno.ECONNRESET,
                errno.EPIPE,
                errno.ETIMEDOUT,
                errno.ECONNABORTED,
                errno.ENETDOWN,
            ):
                return True
        if isinstance(cur, TimeoutError):
            return True
        if isinstance(cur, socket.timeout):
            return True
        msg = str(cur).lower()
        if "unexpected eof" in msg or "eof occurred" in msg:
            return True
        if "ssl" in msg and ("eof" in msg or "handshake" in msg or "wrong version" in msg):
            return True
        if "connection reset" in msg or "broken pipe" in msg:
            return True
    return False


def _direct_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _proxy_opener(proxy: str) -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    )


def _fresh_request(req: Union[urllib.request.Request, str]) -> Union[urllib.request.Request, str]:
    """每次 open 前重建 Request，避免上次 opener 的 set_proxy 污染 host。

    urllib 在经代理访问 HTTPS 时会调用 Request.set_proxy，把 host 改成代理地址。
    若复用同一 Request 再换端口，会继续连旧代理（常见 Connection refused → 7891）。
    """
    if isinstance(req, str):
        return req
    headers = {k: v for k, v in req.header_items()}
    return urllib.request.Request(
        req.full_url,
        data=req.data,
        headers=headers,
        method=req.get_method(),
    )


def urlopen(
    req: Union[urllib.request.Request, str],
    timeout: Optional[float] = None,
    *,
    context=None,
):
    """
    对外 URL：依次尝试 AI_OPERATE_HTTP_PROXIES（默认 7890、7891）。
    每个代理上对可恢复网络错误做有界重试；连接失败则换下一端口。
    换代理 / 重试时重建 Request，避免 set_proxy 污染。
    本机 URL：强制直连，忽略系统 HTTP_PROXY。
    """
    url = _request_url(req)
    if not should_use_vpn_proxy(url):
        opener = _direct_opener()
        return opener.open(_fresh_request(req), timeout=timeout)

    proxies = parse_vpn_proxy_list()
    per_proxy = _per_proxy_retries()
    backoff = _retry_backoff_sec()
    last_err: Optional[BaseException] = None

    for idx, proxy in enumerate(proxies):
        opener = _proxy_opener(proxy)
        for attempt in range(per_proxy):
            try:
                # 关键：不可复用已被 set_proxy 改写过 host 的 Request
                resp = opener.open(_fresh_request(req), timeout=timeout)
                if idx > 0 or attempt > 0:
                    logger.info(
                        "HTTP 经代理 %s 成功（%s）",
                        proxy,
                        "换端口" if idx > 0 and attempt == 0 else f"第 {attempt + 1} 次重试",
                    )
                return resp
            except (urllib.error.URLError, OSError) as e:
                last_err = e
                if not _is_transient_network_failure(e):
                    raise
                connect_fail = _is_proxy_connect_failure(e)
                has_next_proxy = idx + 1 < len(proxies)
                if connect_fail:
                    if has_next_proxy:
                        logger.info(
                            "HTTP 代理 %s 连接失败（%s），改试 %s",
                            proxy,
                            e,
                            proxies[idx + 1],
                        )
                    break
                if attempt + 1 < per_proxy:
                    logger.info(
                        "HTTP 代理 %s 短暂失败（%s），%.2fs 后重试 (%d/%d)",
                        proxy,
                        e,
                        backoff,
                        attempt + 2,
                        per_proxy,
                    )
                    time.sleep(backoff)
                    continue
                if has_next_proxy:
                    logger.info(
                        "HTTP 代理 %s 仍失败（%s），改试 %s",
                        proxy,
                        e,
                        proxies[idx + 1],
                    )
                break

    if last_err is not None:
        raise last_err
    raise urllib.error.URLError("无可用 HTTP 代理配置")
