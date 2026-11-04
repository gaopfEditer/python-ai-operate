# coding=utf-8
"""从本地 Chrome CDP（X 已打开标签）读取 GraphQL queryId / Bearer 捕获。"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from signals.cdp_session_loader import _http_json_on_host, normalize_debugger_host

# x.com/i/api/graphql/{id}/{Op} 或 api.x.com/graphql/{id}/{Op}
_GRAPHQL_OP_RE = re.compile(
    r"(?:^|[/?#])graphql/([A-Za-z0-9_-]+)/(\w+)",
    re.IGNORECASE,
)
_STORE_KEY = "__TrendRadarXGraphqlCapture"

_READ_CAPTURE_JS = r"""
(function () {
  var q = {};
  var re = /graphql\/([A-Za-z0-9_-]+)\/(\w+)/i;
  var auth = "";
  try {
    var raw = sessionStorage.getItem("__TrendRadarXGraphqlCapture")
      || sessionStorage.getItem("__x_toolkit_api_capture");
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
    if (window.__TrendRadarXGraphqlStore && window.__TrendRadarXGraphqlStore.queryIds) {
      var wq = window.__TrendRadarXGraphqlStore.queryIds;
      for (var k2 in wq) { if (wq[k2]) q[k2] = String(wq[k2]); }
      if (window.__TrendRadarXGraphqlStore.authorization) {
        auth = String(window.__TrendRadarXGraphqlStore.authorization);
      }
    }
  } catch (e1) {}
  try {
    var entries = performance.getEntriesByType("resource") || [];
    for (var i = 0; i < entries.length; i++) {
      var name = String(entries[i].name || "");
      if (name.indexOf("graphql") < 0) continue;
      var m = name.match(re);
      if (m) q[m[2]] = m[1];
    }
  } catch (e2) {}
  return { queryIds: q, authorization: auth };
})()
"""

_MAIN_HOOK_JS = r"""
(function () {
  if (window.__TrendRadarXCapture) return;
  window.__TrendRadarXCapture = true;
  var STORE_KEY = "__TrendRadarXGraphqlCapture";
  var OP_RE = /graphql\/([A-Za-z0-9_-]+)\/(\w+)/i;
  function loadStore() {
    try { return JSON.parse(sessionStorage.getItem(STORE_KEY) || "{}") || {}; }
    catch (e) { return {}; }
  }
  function saveStore(patch) {
    var prev = loadStore();
    var next = Object.assign({}, prev, patch, { updatedAt: Date.now() });
    if (patch.queryIds) {
      next.queryIds = Object.assign({}, prev.queryIds || {}, patch.queryIds);
    }
    try { sessionStorage.setItem(STORE_KEY, JSON.stringify(next)); } catch (e) {}
    try { window.__TrendRadarXGraphqlStore = next; } catch (e2) {}
    return next;
  }
  function pickHeaders(h) {
    if (!h) return {};
    var get = function (k) { return (typeof h.get === "function" ? h.get(k) : h[k]); };
    var out = {};
    var auth = get("authorization") || get("Authorization");
    if (auth) out.authorization = auth;
    return out;
  }
  function captureFromRequest(url, headers) {
    var u = String(url || "");
    if (u.indexOf("graphql") < 0) return;
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
  var XO = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    try { captureFromRequest(url, {}); } catch (e) {}
    return XO.apply(this, arguments);
  };
  var XS = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.setRequestHeader = function (name, value) {
    try {
      if (String(name).toLowerCase() === "authorization") {
        saveStore({ authorization: value });
      }
    } catch (e) {}
    return XS.apply(this, arguments);
  };
})()
"""


def parse_graphql_operation_from_url(url: str) -> Tuple[str, str]:
    """从 GraphQL URL 解析 (queryId, operationName)，无法解析时返回 ('', '')。"""
    text = str(url or "").strip()
    if not text or "graphql" not in text.lower():
        return "", ""
    m = _GRAPHQL_OP_RE.search(text)
    if not m:
        return "", ""
    return str(m.group(1)).strip(), str(m.group(2)).strip()


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


class _CdpPageGraphqlCapture:
    """单页 CDP：Network.requestWillBeSent 捕获 GraphQL（不依赖扩展）。"""

    def __init__(self, ws_url: str):
        from websockets.sync.client import connect

        self._ws = connect(ws_url, max_size=64 * 1024 * 1024, open_timeout=10)
        self._next_id = 0
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._pending: dict[int, dict] = {}
        self._closed = False
        self.query_ids: Dict[str, str] = {}
        self.authorization: str = ""
        self._reader = threading.Thread(target=self._read_loop, name="x-gql-cdp", daemon=True)
        self._reader.start()

    def _on_network_request(self, request: Dict[str, Any]) -> None:
        url = str(request.get("url") or "")
        qid, op = parse_graphql_operation_from_url(url)
        if qid and op:
            self.query_ids[op] = qid
        headers = request.get("headers") if isinstance(request.get("headers"), dict) else {}
        auth = str(
            headers.get("authorization")
            or headers.get("Authorization")
            or ""
        ).strip()
        if auth and not self.authorization:
            self.authorization = auth

    def _read_loop(self) -> None:
        try:
            while not self._closed:
                raw = self._ws.recv()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                msg = json.loads(raw)
                method = msg.get("method")
                if method == "Network.requestWillBeSent":
                    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
                    req = params.get("request") if isinstance(params.get("request"), dict) else {}
                    self._on_network_request(req)
                mid = msg.get("id")
                if mid is not None:
                    with self._cv:
                        self._pending[int(mid)] = msg
                        self._cv.notify_all()
        except Exception:
            with self._cv:
                self._closed = True
                self._cv.notify_all()

    def call(
        self,
        method: str,
        params: Optional[dict] = None,
        timeout: float = 60.0,
    ) -> dict:
        with self._lock:
            if self._closed:
                raise RuntimeError("CDP 连接已关闭")
            self._next_id += 1
            msg_id = self._next_id
            payload: dict[str, Any] = {
                "id": msg_id,
                "method": method,
                "params": params or {},
            }
            self._ws.send(json.dumps(payload))
            deadline = time.time() + timeout
            while msg_id not in self._pending:
                if self._closed:
                    raise RuntimeError(f"CDP 断开: {method}")
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise TimeoutError(f"CDP 超时: {method}")
                self._cv.wait(timeout=remaining)
            resp = self._pending.pop(msg_id)
        if "error" in resp:
            err = resp["error"]
            raise RuntimeError(f"{method}: {err}")
        return resp.get("result") or {}

    def close(self) -> None:
        self._closed = True
        try:
            self._ws.close()
        except Exception:
            pass


def _eval_on_page(ws_url: str, expression: str) -> Any:
    cap = _CdpPageGraphqlCapture(ws_url)
    try:
        cap.call("Runtime.enable", {})
        res = cap.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": False},
        )
        return (res.get("result") or {}).get("value")
    finally:
        cap.close()


def _install_main_world_hook(capture: _CdpPageGraphqlCapture) -> None:
    """尽量在页面 MAIN world 安装 hook（新文档 + 当前文档各试一次）。"""
    params: Dict[str, Any] = {"source": _MAIN_HOOK_JS}
    try:
        capture.call("Page.addScriptToEvaluateOnNewDocument", params)
    except RuntimeError:
        try:
            capture.call("Page.addScriptToEvaluateOnNewDocument", {**params, "worldName": "MAIN"})
        except RuntimeError:
            pass
    for expr_params in (
        {"expression": _MAIN_HOOK_JS, "returnByValue": True},
        {"expression": _MAIN_HOOK_JS, "returnByValue": True, "includeCommandLineAPI": False},
    ):
        try:
            capture.call("Runtime.evaluate", expr_params)
            break
        except RuntimeError:
            continue


def _read_page_capture_store(capture: _CdpPageGraphqlCapture) -> Tuple[Dict[str, str], str]:
    res = capture.call(
        "Runtime.evaluate",
        {"expression": _READ_CAPTURE_JS, "returnByValue": True, "awaitPromise": False},
    )
    val = (res.get("result") or {}).get("value")
    q, b = _parse_query_ids_from_value(val)
    q.update(capture.query_ids)
    bearer = b or capture.authorization
    return q, bearer


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
    timeout_sec: float = 22.0,
) -> Tuple[Dict[str, str], str]:
    """Network 监听 + MAIN hook；导航列表/首页并轮询直到捕获所需 operation。"""
    deadline = time.monotonic() + max(5.0, float(timeout_sec))
    merged: Dict[str, str] = {}
    bearer = ""
    capture = _CdpPageGraphqlCapture(ws_url)
    try:
        capture.call("Network.enable", {})
        capture.call("Page.enable", {})
        _install_main_world_hook(capture)

        if navigate_url:
            capture.call("Page.navigate", {"url": navigate_url})
        else:
            capture.call("Page.reload", {"ignoreCache": False})

        while time.monotonic() < deadline:
            q, b = _read_page_capture_store(capture)
            merged.update(q)
            if b and not bearer:
                bearer = b
            if not _missing_operations(merged, needed):
                return merged, ""
            try:
                res = capture.call(
                    "Runtime.evaluate",
                    {"expression": "document.readyState", "returnByValue": True},
                    timeout=3.0,
                )
                state = (res.get("result") or {}).get("value")
                if state == "complete" and time.monotonic() > deadline - 8.0:
                    capture.call("Page.reload", {"ignoreCache": False})
            except Exception:
                pass
            time.sleep(0.4)
    finally:
        capture.close()

    missing = _missing_operations(merged, needed)
    if missing:
        return merged, f"导航后仍未捕获: {', '.join(missing)}"
    return merged, ""


def ensure_graphql_query_ids_from_cdp(
    debugger_url: str,
    needed_operations: Iterable[str],
    *,
    navigate_urls: Optional[Sequence[str]] = None,
    timeout_sec: float = 22.0,
) -> Tuple[Dict[str, str], str, str]:
    """
    优先读已有标签；缺 operation 时在 x.com 标签上 Network 监听并导航等待。
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
    扫描 x.com 标签 performance / sessionStorage；必要时短监听 Network。
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
