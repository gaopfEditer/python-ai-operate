# coding=utf-8
"""运行时从本地 Chrome CDP 读取 Cookie，供 Square bapi / X GraphQL 使用（短 TTL 内存缓存，不写盘）。"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

ProgressCb = Optional[Callable[[str], None]]

_BINANCE_COOKIE_NAMES = frozenset({"csrftoken", "bnc-uuid"})
_BINANCE_URLS = ("https://www.binance.com", "https://binance.com")
_X_COOKIE_NAMES = frozenset({"auth_token", "ct0"})
_X_URLS = ("https://x.com", "https://twitter.com")

_LOCK = threading.RLock()
_CACHE: Dict[str, Dict[str, Any]] = {}


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)


def _ttl_seconds() -> float:
    raw = str(os.environ.get("SIGNALS_SESSION_CDP_TTL") or "120").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 120.0


def _cdp_disabled() -> bool:
    return str(os.environ.get("SIGNALS_SESSION_CDP_DISABLE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def normalize_debugger_host(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    s = s.replace("http://", "").replace("https://", "").strip().strip("/")
    return s


def resolve_debugger_url(*, explicit: str = "", binance_cfg_debugger: str = "") -> str:
    host = normalize_debugger_host(explicit) or normalize_debugger_host(binance_cfg_debugger)
    if host:
        return host
    try:
        from signals.store import resolve_signals_debugger_url

        return resolve_signals_debugger_url()
    except Exception:
        pass
    try:
        from utils.crawl_cdp import resolve_crawl_debugger_url

        return resolve_crawl_debugger_url()
    except Exception:
        return "127.0.0.1:9223"


def _http_json_on_host(host: str, path: str) -> Any:
    import json
    import urllib.request

    base = host if host.startswith("http") else f"http://{host}"
    base = base.rstrip("/")
    url = f"{base}{path}"
    with urllib.request.urlopen(url, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _collect_cookies_from_cdp(
    debugger_url: str,
    *,
    urls: Tuple[str, ...],
    want_names: frozenset,
    prefer_url_substr: str = "",
) -> Tuple[Dict[str, str], str]:
    """返回 (cookies, error_message)。"""
    host = normalize_debugger_host(debugger_url)
    if not host:
        return {}, "未配置 CDP 地址"

    try:
        pages = _http_json_on_host(host, "/json/list")
    except Exception as e:
        return {}, f"无法连接 CDP（{host}）: {e}"

    if not isinstance(pages, list):
        return {}, "CDP /json/list 无效"

    ordered: List[Dict[str, Any]] = [p for p in pages if isinstance(p, dict)]
    if prefer_url_substr:
        ordered.sort(
            key=lambda p: (0 if prefer_url_substr in str(p.get("url") or "").lower() else 1)
        )

    from allnews_mornitor.cdp_browser import _CdpClient

    last_err = "未找到匹配 Cookie"
    for page in ordered:
        ws = str(page.get("webSocketDebuggerUrl") or "").strip()
        if not ws:
            continue
        client = None
        try:
            client = _CdpClient(ws)
            client.call("Network.enable", {})
            res = client.call("Network.getCookies", {"urls": list(urls)})
            found: Dict[str, str] = {}
            for c in res.get("cookies") or []:
                if not isinstance(c, dict):
                    continue
                name = str(c.get("name") or "")
                val = str(c.get("value") or "").strip()
                if not val:
                    continue
                if name in want_names or name.lower() in {x.lower() for x in want_names}:
                    found[name if name in want_names else name.lower()] = val
            if want_names == _X_COOKIE_NAMES:
                if found.get("auth_token") and found.get("ct0"):
                    return found, ""
            elif want_names == _BINANCE_COOKIE_NAMES or "csrftoken" in {
                k.lower() for k in found
            }:
                norm: Dict[str, str] = {}
                for k, v in found.items():
                    lk = k.lower()
                    if lk == "csrftoken":
                        norm["csrftoken"] = v
                    elif lk in ("bnc-uuid", "bnc_uuid"):
                        norm["bnc-uuid"] = v
                    else:
                        norm[k] = v
                if norm.get("csrftoken") or norm.get("bnc-uuid"):
                    return norm, ""
            last_err = "当前标签无所需 Cookie"
        except Exception as e:
            last_err = str(e)[:160]
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
    return {}, last_err


def _binance_session_from_cookies(cookies: Dict[str, str]) -> Dict[str, Any]:
    headers: Dict[str, str] = {}
    for k in ("csrftoken", "bnc-uuid"):
        if cookies.get(k):
            headers[k] = cookies[k]
    csrf = cookies.get("csrftoken") or ""
    if csrf:
        headers["csrftoken"] = csrf
        headers.setdefault("BNC-CSRF-TOKEN", csrf)
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items() if v)
    return {"cookies": dict(cookies), "headers": headers, "cookie_header": cookie_header}


def pull_binance_session_from_cdp(debugger_url: str) -> Tuple[Optional[Dict[str, Any]], str]:
    cookies, err = _collect_cookies_from_cdp(
        debugger_url,
        urls=_BINANCE_URLS,
        want_names=_BINANCE_COOKIE_NAMES,
        prefer_url_substr="binance.com",
    )
    if not cookies:
        return None, err
    return _binance_session_from_cookies(cookies), ""


def pull_x_session_from_cdp(debugger_url: str) -> Tuple[Optional[Dict[str, Any]], str]:
    from signals.x_cdp_graphql import ensure_graphql_query_ids_from_cdp, merge_captured_query_ids
    from signals.x_session import DEFAULT_BEARER

    cookies, err = _collect_cookies_from_cdp(
        debugger_url,
        urls=_X_URLS,
        want_names=_X_COOKIE_NAMES,
        prefer_url_substr="x.com",
    )
    auth = cookies.get("auth_token") or ""
    ct0 = cookies.get("ct0") or ""
    if not auth or not ct0:
        return None, err or "缺少 auth_token/ct0"

    captured_q, cap_bearer, cap_hint = ensure_graphql_query_ids_from_cdp(
        debugger_url,
        ("ListLatestTweetsTimeline", "UserTweets", "UserByScreenName"),
        navigate_urls=("https://x.com/home",),
    )
    qids = merge_captured_query_ids(captured_q)
    bearer = DEFAULT_BEARER
    if cap_bearer:
        bearer = cap_bearer if cap_bearer.lower().startswith("bearer") else f"Bearer {cap_bearer}"

    sess = {
        "auth_token": auth,
        "ct0": ct0,
        "authorization": bearer,
        "query_ids": qids,
        "cookie_header": f"auth_token={auth}; ct0={ct0}",
        "query_ids_captured": list(captured_q.keys()),
        "query_id_hint": cap_hint,
    }
    return sess, cap_hint


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        ent = _CACHE.get(key)
        if not ent:
            return None
        ttl = _ttl_seconds()
        if ttl > 0 and time.monotonic() - float(ent.get("ts") or 0) > ttl:
            return None
        sess = ent.get("session")
        return dict(sess) if isinstance(sess, dict) else None


def _cache_set(key: str, session: Dict[str, Any]) -> None:
    with _LOCK:
        _CACHE[key] = {"session": dict(session), "ts": time.monotonic()}


def clear_session_cache() -> None:
    with _LOCK:
        _CACHE.clear()


def refresh_binance_session_from_cdp(
    *,
    debugger_url: str = "",
    binance_cfg_debugger: str = "",
    progress: ProgressCb = None,
    force_refresh: bool = False,
) -> Optional[Dict[str, Any]]:
    from signals.binance_square.session import load_binance_session, merge_supplemental_headers

    if not force_refresh:
        cached = _cache_get("binance")
        if cached:
            return cached

    dbg = resolve_debugger_url(explicit=debugger_url, binance_cfg_debugger=binance_cfg_debugger)

    if not _cdp_disabled():
        cdp_sess, err = pull_binance_session_from_cdp(dbg)
        if cdp_sess:
            file_sess = load_binance_session()
            merged = merge_supplemental_headers(cdp_sess, file_sess)
            n_ck = len(merged.get("cookies") or {})
            _log(progress, f"Square 会话：已从 CDP（{dbg}）读取 Cookie（{n_ck} 项），立即走 bapi")
            _cache_set("binance", merged)
            return merged
        _log(
            progress,
            f"Square 会话：CDP（{dbg}）读取失败 — {err}；"
            "请确认 Chrome 已开远程调试且已登录 binance.com",
        )
    else:
        _log(progress, "Square 会话：已禁用 CDP 读取（SIGNALS_SESSION_CDP_DISABLE）")

    fallback = load_binance_session()
    if fallback:
        _log(progress, "Square 会话：回退本地 session 文件/环境变量")
        _cache_set("binance", fallback)
        return fallback

    _log(progress, "Square 会话：未就绪，无法调用 bapi")
    return None


def refresh_x_session_from_cdp(
    *,
    debugger_url: str = "",
    progress: ProgressCb = None,
    force_refresh: bool = False,
) -> Optional[Dict[str, Any]]:
    from signals.x_session import load_x_session, merge_x_supplemental

    if not force_refresh:
        cached = _cache_get("x")
        if cached:
            return cached

    dbg = resolve_debugger_url(explicit=debugger_url)

    if not _cdp_disabled():
        cdp_sess, err = pull_x_session_from_cdp(dbg)
        if cdp_sess:
            file_sess = load_x_session()
            merged = merge_x_supplemental(cdp_sess, file_sess)
            cap_ops = cdp_sess.get("query_ids_captured") or []
            qn = len(cap_ops) if isinstance(cap_ops, list) else 0
            ops_preview = ", ".join(list(cap_ops)[:4]) if qn else "内置默认"
            hint = str(cdp_sess.get("query_id_hint") or err or "").strip()
            _log(
                progress,
                f"X 会话：已从 CDP（{dbg}）读取 auth_token/ct0 + GraphQL queryId"
                f"（{qn or '默认'} 项：{ops_preview}）",
            )
            if hint and qn == 0:
                _log(progress, f"X queryId 提示：{hint}")
            clean = {k: v for k, v in merged.items() if k != "query_id_hint"}
            _cache_set("x", clean)
            return clean
        _log(
            progress,
            f"X 会话：CDP（{dbg}）读取失败 — {err}；"
            "请确认 Chrome 已登录 x.com",
        )
    else:
        _log(progress, "X 会话：已禁用 CDP 读取（SIGNALS_SESSION_CDP_DISABLE）")

    fallback = load_x_session()
    if fallback:
        _log(progress, "X 会话：回退本地 session 文件/环境变量")
        _cache_set("x", fallback)
        return fallback

    _log(progress, "X 会话：未就绪，无法调用 GraphQL API")
    return None


def get_cached_binance_session() -> Optional[Dict[str, Any]]:
    cached = _cache_get("binance")
    if cached:
        return cached
    from signals.binance_square.session import load_binance_session

    return load_binance_session()


def get_cached_x_session() -> Optional[Dict[str, Any]]:
    cached = _cache_get("x")
    if cached:
        return cached
    from signals.x_session import load_x_session

    return load_x_session()


def patch_cached_x_session(session: Dict[str, Any]) -> None:
    if not isinstance(session, dict):
        return
    clean = {k: v for k, v in session.items() if k != "query_id_hint"}
    _cache_set("x", clean)


def ensure_x_graphql_query_ids(
    operations: Tuple[str, ...],
    *,
    debugger_url: str = "",
    navigate_urls: Optional[Tuple[str, ...]] = None,
    progress: ProgressCb = None,
    force: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    GraphQL 调用前：在 CDP 可用时刷新 Cookie + queryId（必要时导航 X 页面抓 live queryId）。
    更新内存缓存；若已有 session 文件则合并写入 query_ids。
    """
    from signals.x_cdp_graphql import (
        ensure_graphql_query_ids_from_cdp,
        merge_captured_query_ids,
        operation_query_id_is_builtin_only,
    )
    from signals.x_session import load_x_session, merge_x_supplemental, maybe_persist_x_query_ids

    ops = tuple(str(o).strip() for o in operations if str(o).strip())
    if not ops:
        return get_cached_x_session()

    if _cdp_disabled():
        return get_cached_x_session()

    dbg = resolve_debugger_url(explicit=debugger_url)
    base = get_cached_x_session() or load_x_session()
    need_capture = force
    if base and not need_capture:
        qids = base.get("query_ids") if isinstance(base.get("query_ids"), dict) else {}
        captured_ops = {
            str(x).strip()
            for x in (base.get("query_ids_captured") or [])
            if str(x).strip()
        }
        need_capture = any(
            op not in captured_ops and operation_query_id_is_builtin_only(qids, op)
            for op in ops
        )
    elif not base:
        need_capture = True

    if not need_capture:
        return base

    cookies, err = _collect_cookies_from_cdp(
        dbg,
        urls=_X_URLS,
        want_names=_X_COOKIE_NAMES,
        prefer_url_substr="x.com",
    )
    if not cookies.get("auth_token") or not cookies.get("ct0"):
        _log(progress, f"X queryId：CDP Cookie 不可用（{err or '缺 auth_token/ct0'}）")
        return base

    captured_q, cap_bearer, cap_hint = ensure_graphql_query_ids_from_cdp(
        dbg,
        ops,
        navigate_urls=navigate_urls,
    )
    from signals.x_session import DEFAULT_BEARER

    bearer = DEFAULT_BEARER
    if cap_bearer:
        bearer = cap_bearer if cap_bearer.lower().startswith("bearer") else f"Bearer {cap_bearer}"

    draft = {
        "auth_token": cookies["auth_token"],
        "ct0": cookies["ct0"],
        "authorization": bearer,
        "query_ids": merge_captured_query_ids(captured_q),
        "cookie_header": f"auth_token={cookies['auth_token']}; ct0={cookies['ct0']}",
        "query_ids_captured": list(captured_q.keys()),
        "query_id_hint": cap_hint,
    }
    merged = merge_x_supplemental(draft, load_x_session())
    cap_ops = draft.get("query_ids_captured") or []
    qn = len(cap_ops) if isinstance(cap_ops, list) else 0
    if qn:
        _log(
            progress,
            f"X queryId：已从 CDP 捕获 {qn} 项（{', '.join(list(cap_ops)[:4])}）",
        )
    elif cap_hint:
        _log(progress, f"X queryId 提示：{cap_hint}")

    patch_cached_x_session(merged)
    maybe_persist_x_query_ids(merged)
    return merged
