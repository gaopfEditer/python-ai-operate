# coding=utf-8
"""从本地 Chrome CDP（X 已打开标签）读取 GraphQL queryId / Bearer 捕获。"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from signals.cdp_session_loader import _http_json_on_host, normalize_debugger_host

_GRAPHQL_OP_RE = re.compile(r"/i/api/graphql/([^/]+)/(\w+)")
_STORE_KEY = "__x_toolkit_api_capture"

_READ_CAPTURE_JS = r"""
(function () {
  var q = {};
  var re = /\/i\/api\/graphql\/([^/]+)\/(\w+)/;
  var auth = "";
  try {
    var raw = sessionStorage.getItem("__x_toolkit_api_capture");
    if (raw) {
      var st = JSON.parse(raw) || {};
      if (st.queryIds && typeof st.queryIds === "object") {
        for (var k in st.queryIds) {
          if (st.queryIds[k]) q[k] = String(st.queryIds[k]);
        }
      }
      if (st.authorization) auth = String(st.authorization);
    }
  } catch (e) {}
  try {
    var entries = performance.getEntriesByType("resource") || [];
    for (var i = 0; i < entries.length; i++) {
      var name = String(entries[i].name || "");
      var m = name.match(re);
      if (m) q[m[2]] = m[1];
    }
  } catch (e2) {}
  return { queryIds: q, authorization: auth };
})()
"""

_INJECT_HOOK_JS = r"""
(function () {
  if (window.__TrendRadarXCapture) return "already";
  window.__TrendRadarXCapture = true;
  var STORE_KEY = "__x_toolkit_api_capture";
  var OP_RE = /\/i\/api\/graphql\/([^/]+)\/(\w+)/;
  function loadStore() {
    try { return JSON.parse(sessionStorage.getItem(STORE_KEY) || "{}") || {}; }
    catch (e) { return {}; }
  }
  function saveStore(patch) {
    var prev = loadStore();
    var next = Object.assign({}, prev, patch, { updatedAt: Date.now() });
    if (patch.queryIds) next.queryIds = Object.assign({}, prev.queryIds || {}, patch.queryIds);
    try { sessionStorage.setItem(STORE_KEY, JSON.stringify(next)); } catch (e) {}
    return next;
  }
  function pickHeaders(h) {
    if (!h) return {};
    var get = function (k) { return (typeof h.get === "function" ? h.get(k) : h[k]); };
    var out = {};
    var auth = get("authorization") || get("Authorization");
    var csrf = get("x-csrf-token") || get("X-Csrf-Token");
    if (auth) out.authorization = auth;
    if (csrf) out.csrf = csrf;
    return out;
  }
  function captureFromRequest(url, headers) {
    var u = String(url || "");
    if (u.indexOf("/i/api/") < 0) return;
    var patch = pickHeaders(headers);
    var m = u.match(OP_RE);
    if (m) { patch.queryIds = {}; patch.queryIds[m[2]] = m[1]; }
    if (Object.keys(patch).length) saveStore(patch);
  }
  var origFetch = window.fetch;
  window.fetch = function (input, init) {
    try {
      var url = typeof input === "string" ? input : (input && input.url);
      var headers = (init && init.headers) || (input instanceof Request ? input.headers : null);
      captureFromRequest(url, headers);
    } catch (e) {}
    return origFetch.apply(this, arguments);
  };
  return "injected";
})()
"""


def _parse_query_ids_from_value(val: Any) -> Tuple[Dict[str, str], str]:
    qids: Dict[str, str] = {}
    bearer = ""
    if isinstance(val, dict):
        raw_q = val.get("queryIds") if isinstance(val.get("queryIds"), dict) else val
        if isinstance(raw_q, dict):
            for k, v in raw_q.items():
                if k and str(v).strip():
                    qids[str(k)] = str(v).strip()
        bearer = str(val.get("authorization") or "").strip()
    return qids, bearer


def merge_captured_query_ids(*layers: Any) -> Dict[str, str]:
    from signals.x_session import DEFAULT_QUERY_IDS

    out = dict(DEFAULT_QUERY_IDS)
    for layer in layers:
        q, _ = _parse_query_ids_from_value(layer if isinstance(layer, dict) else {})
        out.update(q)
        if isinstance(layer, dict) and not layer.get("queryIds"):
            for k, v in layer.items():
                if k and str(v).strip() and k[0].isupper():
                    out[str(k)] = str(v).strip()
    return out


def _eval_on_page(ws_url: str, expression: str) -> Any:
    from allnews_mornitor.cdp_browser import _CdpClient

    client = _CdpClient(ws_url)
    try:
        client.call("Runtime.enable", {})
        res = client.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": False},
        )
        return (res.get("result") or {}).get("value")
    finally:
        try:
            client.close()
        except Exception:
            pass


def _x_pages_from_debugger(host: str) -> List[Dict[str, Any]]:
    pages = _http_json_on_host(host, "/json/list")
    if not isinstance(pages, list):
        return []
    ordered: List[Dict[str, Any]] = [p for p in pages if isinstance(p, dict)]
    ordered.sort(
        key=lambda p: (0 if "x.com" in str(p.get("url") or "").lower() else 1)
    )
    return ordered


def _missing_operations(
    merged: Dict[str, str], needed: Sequence[str]
) -> List[str]:
    out: List[str] = []
    for op in needed:
        if not str(merged.get(op) or "").strip():
            out.append(op)
    return out


def _navigate_and_wait_query_ids(
    ws_url: str,
    *,
    navigate_url: str,
    needed: Sequence[str],
    timeout_sec: float = 18.0,
) -> Tuple[Dict[str, str], str]:
    """在已有 x.com 标签上导航并轮询 performance / sessionStorage 捕获 queryId。"""
    from allnews_mornitor.cdp_browser import _CdpClient

    deadline = time.monotonic() + max(3.0, float(timeout_sec))
    merged: Dict[str, str] = {}
    client = _CdpClient(ws_url)
    try:
        client.call("Page.enable", {})
        client.call(
            "Runtime.evaluate",
            {"expression": _INJECT_HOOK_JS, "returnByValue": True},
        )
        if navigate_url:
            client.call("Page.navigate", {"url": navigate_url})
        while time.monotonic() < deadline:
            res = client.call(
                "Runtime.evaluate",
                {"expression": _READ_CAPTURE_JS, "returnByValue": True, "awaitPromise": False},
            )
            val = (res.get("result") or {}).get("value")
            q, _ = _parse_query_ids_from_value(val)
            merged.update(q)
            if not _missing_operations(merged, needed):
                return merged, ""
            time.sleep(0.45)
    finally:
        try:
            client.close()
        except Exception:
            pass
    missing = _missing_operations(merged, needed)
    if missing:
        return merged, f"导航后仍未捕获: {', '.join(missing)}"
    return merged, ""


def ensure_graphql_query_ids_from_cdp(
    debugger_url: str,
    needed_operations: Iterable[str],
    *,
    navigate_urls: Optional[Sequence[str]] = None,
    timeout_sec: float = 18.0,
) -> Tuple[Dict[str, str], str, str]:
    """
    优先读已有标签；缺 operation 时在 x.com 标签上导航并等待 GraphQL 请求。
    返回 (query_ids, authorization, hint)。
    """
    needed = [str(op).strip() for op in needed_operations if str(op).strip()]
    if not needed:
        q, b, hint = capture_x_graphql_from_cdp(debugger_url)
        return q, b, hint

    host = normalize_debugger_host(debugger_url)
    if not host:
        return {}, "", "未配置 CDP"

    merged_q, bearer, hint = capture_x_graphql_from_cdp(debugger_url)
    if not _missing_operations(merged_q, needed):
        return merged_q, bearer, hint

    pages = _x_pages_from_debugger(host)
    ws = ""
    for page in pages:
        url = str(page.get("url") or "").lower()
        if "x.com" in url or "twitter.com" in url:
            ws = str(page.get("webSocketDebuggerUrl") or "").strip()
            if ws:
                break
    if not ws:
        return merged_q, bearer, hint or "Chrome 中无 x.com 标签页，无法导航捕获 queryId"

    urls = [u for u in (navigate_urls or ()) if str(u).strip()]
    if not urls:
        urls = ["https://x.com/home"]

    nav_hint = ""
    for nav in urls:
        extra, nav_hint = _navigate_and_wait_query_ids(
            ws,
            navigate_url=nav,
            needed=needed,
            timeout_sec=timeout_sec,
        )
        merged_q.update(extra)
        if not _missing_operations(merged_q, needed):
            return merged_q, bearer, ""
    return merged_q, bearer, nav_hint or hint


def capture_x_graphql_from_cdp(debugger_url: str) -> Tuple[Dict[str, str], str, str]:
    """
    返回 (query_ids, authorization, error_hint)。
    扫描 x.com / twitter.com 标签的 sessionStorage + performance。
    """
    host = normalize_debugger_host(debugger_url)
    if not host:
        return {}, "", "未配置 CDP"

    try:
        pages = _http_json_on_host(host, "/json/list")
    except Exception as e:
        return {}, "", str(e)

    if not isinstance(pages, list):
        return {}, "", "CDP /json/list 无效"

    merged_q: Dict[str, str] = {}
    bearer = ""
    touched = 0
    ordered: List[Dict[str, Any]] = [p for p in pages if isinstance(p, dict)]
    ordered.sort(
        key=lambda p: (0 if "x.com" in str(p.get("url") or "").lower() else 1)
    )

    for page in ordered:
        url = str(page.get("url") or "").lower()
        if "x.com" not in url and "twitter.com" not in url:
            continue
        ws = str(page.get("webSocketDebuggerUrl") or "").strip()
        if not ws:
            continue
        touched += 1
        try:
            val = _eval_on_page(ws, _READ_CAPTURE_JS)
            q, b = _parse_query_ids_from_value(val)
            merged_q.update(q)
            if b and not bearer:
                bearer = b
            if not merged_q:
                _eval_on_page(ws, _INJECT_HOOK_JS)
                val2 = _eval_on_page(ws, _READ_CAPTURE_JS)
                q2, b2 = _parse_query_ids_from_value(val2)
                merged_q.update(q2)
                if b2 and not bearer:
                    bearer = b2
        except Exception:
            continue
        if merged_q.get("ListLatestTweetsTimeline") or merged_q.get("UserTweets"):
            break

    if not touched:
        return {}, "", "Chrome 中无 x.com 标签页"
    if not merged_q:
        return (
            {},
            bearer,
            "未捕获 queryId：请在 Chrome 打开 X 首页/列表/博主页后再跑实时抓取",
        )
    return merged_q, bearer, ""


def count_fresh_query_ids(qids: Dict[str, str]) -> int:
    from signals.x_session import DEFAULT_QUERY_IDS

    n = 0
    for k, v in (qids or {}).items():
        if str(v).strip() and DEFAULT_QUERY_IDS.get(k) != v:
            n += 1
    return n


def operation_query_id_is_builtin_only(qids: Dict[str, str], operation: str) -> bool:
    """True 表示仅有内置默认 id、未见 CDP/文件覆盖。"""
    from signals.x_session import DEFAULT_QUERY_IDS

    val = str((qids or {}).get(operation) or DEFAULT_QUERY_IDS.get(operation) or "").strip()
    if not val:
        return True
    return val == str(DEFAULT_QUERY_IDS.get(operation) or "").strip()
