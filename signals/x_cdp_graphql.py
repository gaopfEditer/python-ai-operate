# coding=utf-8
"""从本地 Chrome CDP（X 已打开标签）读取 GraphQL queryId / Bearer 捕获。"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

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
