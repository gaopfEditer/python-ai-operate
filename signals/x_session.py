# coding=utf-8
"""X.com 会话：Cookie + Bearer + GraphQL queryId（本地文件或环境变量，不入库）。"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SESSION_PATH = PROJECT_ROOT / "output" / "signals" / "x_api_session.json"

# Web 客户端公开 Bearer；与 auth_token + ct0 组合用于已登录 GraphQL
DEFAULT_BEARER = (
    "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LF81IUq15cAPsr7T9MXWOL4Y5E86L8vE0H5Q"
)

DEFAULT_QUERY_IDS: Dict[str, str] = {
    "ListLatestTweetsTimeline": "RlZzktZY_9wJynoepm8ZsA",
    "UserByScreenName": "G3KGOASz96M-Qu0nwmFhNg",
    "UserTweets": "q6xj5bs0hapm9309hexA_g",
    "UserTweetsAndReplies": "6hvhmQQ9zPIR8RZWHFAm4w",
    "SearchTimeline": "VhUd6vHVmLBcw0uX-6jMLA",
}


def session_file_path() -> Path:
    raw = str(os.environ.get("X_API_SESSION_FILE") or "").strip()
    return Path(raw) if raw else DEFAULT_SESSION_PATH


def _merge_query_ids(custom: Any) -> Dict[str, str]:
    out = dict(DEFAULT_QUERY_IDS)
    if isinstance(custom, dict):
        for k, v in custom.items():
            if k and str(v).strip():
                out[str(k)] = str(v).strip()
    return out


def load_x_session() -> Optional[Dict[str, Any]]:
    auth = str(os.environ.get("X_AUTH_TOKEN") or os.environ.get("AUTH_TOKEN") or "").strip()
    ct0 = str(os.environ.get("X_CT0") or os.environ.get("CT0") or "").strip()
    bearer = str(os.environ.get("X_BEARER") or os.environ.get("X_AUTHORIZATION") or "").strip()
    qids: Dict[str, str] = dict(DEFAULT_QUERY_IDS)

    path = session_file_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if isinstance(data, dict):
            auth = auth or str(data.get("auth_token") or "").strip()
            ct0 = ct0 or str(data.get("ct0") or data.get("csrf") or "").strip()
            bearer = bearer or str(data.get("authorization") or "").strip()
            qids = _merge_query_ids(data.get("query_ids") or data.get("queryIds"))
            file_cookie = str(data.get("cookie_header") or "").strip()
        else:
            file_cookie = ""
    else:
        file_cookie = ""

    if not auth or not ct0:
        return None
    if bearer and not bearer.lower().startswith("bearer"):
        bearer = f"Bearer {bearer}"
    if not bearer:
        bearer = DEFAULT_BEARER

    cookie_header = file_cookie if file_cookie else f"auth_token={auth}; ct0={ct0}"
    if "auth_token=" not in cookie_header:
        cookie_header = f"auth_token={auth}; " + cookie_header
    if "ct0=" not in cookie_header:
        cookie_header = cookie_header + f"; ct0={ct0}"

    return {
        "auth_token": auth,
        "ct0": ct0,
        "authorization": bearer,
        "query_ids": qids,
        "cookie_header": cookie_header,
    }


def session_ready(session: Optional[Dict[str, Any]] = None) -> bool:
    s = session if session is not None else load_x_session()
    return bool(s and s.get("auth_token") and s.get("ct0"))


def query_id(session: Dict[str, Any], operation: str) -> str:
    q = session.get("query_ids") if isinstance(session.get("query_ids"), dict) else {}
    return str(q.get(operation) or DEFAULT_QUERY_IDS.get(operation) or "").strip()


def save_x_session(payload: Dict[str, Any], *, path: Optional[Path] = None) -> Path:
    dest = path or session_file_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    clean = {
        "auth_token": str(payload.get("auth_token") or "").strip(),
        "ct0": str(payload.get("ct0") or payload.get("csrf") or "").strip(),
        "authorization": str(payload.get("authorization") or DEFAULT_BEARER).strip(),
        "query_ids": _merge_query_ids(payload.get("query_ids") or payload.get("queryIds")),
    }
    ch = str(payload.get("cookie_header") or "").strip()
    if ch:
        clean["cookie_header"] = ch
    dest.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def parse_netscape_cookies(text: str) -> Dict[str, str]:
    """Netscape cookies.txt → name → value（仅 x.com / twitter.com）。"""
    out: Dict[str, str] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, _path, _secure, _expiry, name, value = parts[:7]
        if "x.com" not in domain and "twitter.com" not in domain:
            continue
        if name in ("auth_token", "ct0"):
            out[name] = value
    return out


def load_from_cookie_file(path: str) -> Optional[Dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return None
    cookies = parse_netscape_cookies(p.read_text(encoding="utf-8", errors="replace"))
    if not cookies.get("auth_token") or not cookies.get("ct0"):
        return None
    prev_a = os.environ.pop("X_AUTH_TOKEN", None)
    prev_c = os.environ.pop("X_CT0", None)
    try:
        os.environ["X_AUTH_TOKEN"] = cookies["auth_token"]
        os.environ["X_CT0"] = cookies["ct0"]
        return load_x_session()
    finally:
        if prev_a is None:
            os.environ.pop("X_AUTH_TOKEN", None)
        else:
            os.environ["X_AUTH_TOKEN"] = prev_a
        if prev_c is None:
            os.environ.pop("X_CT0", None)
        else:
            os.environ["X_CT0"] = prev_c


def _cdp_debugger_host() -> str:
    try:
        from signals.store import resolve_signals_debugger_url

        return str(resolve_signals_debugger_url() or "127.0.0.1:9223").replace("http://", "").replace("https://", "").strip("/")
    except Exception:
        return str(os.environ.get("CDP_DEBUGGER_URL") or "127.0.0.1:9223").replace("http://", "").replace("https://", "").strip("/")


def _extract_query_ids_from_js(blob: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not blob:
        return out
    # queryId:"xxx"...operationName:"ListLatest..."  or reverse order windows
    for name in DEFAULT_QUERY_IDS:
        for m in re.finditer(re.escape(name), blob):
            window = blob[max(0, m.start() - 220) : m.end() + 220]
            for q in re.findall(r'queryId:"([A-Za-z0-9_-]{18,32})"', window):
                out[name] = q
                break
            if name in out:
                break
            for q in re.findall(r'"([A-Za-z0-9_-]{18,32})"', window):
                if q != name and re.fullmatch(r"[A-Za-z0-9_-]{18,32}", q):
                    # prefer strings that look like queryIds near the op name
                    if "queryId" in window or "operationName" in window:
                        out[name] = q
                        break
            if name in out:
                break
    # URL style /graphql/QID/Operation
    for m in re.finditer(r"/graphql/([A-Za-z0-9_-]+)/([A-Za-z0-9_]+)", blob):
        qid, op = m.group(1), m.group(2)
        if op in DEFAULT_QUERY_IDS:
            out[op] = qid
    return out


def refresh_x_session_from_cdp(
    *,
    progress: Any = None,
    debugger_url: Optional[str] = None,
    save: bool = True,
) -> Dict[str, Any]:
    """每次 GraphQL 前调用：从已登录 Chrome CDP 拉取最新 cookie + queryId。"""
    def _log(msg: str) -> None:
        if callable(progress):
            try:
                progress(msg)
            except Exception:
                pass

    host = (debugger_url or _cdp_debugger_host()).replace("http://", "").replace("https://", "").strip("/")
    _log(f"X API：CDP 刷新会话 @ {host}…")

    import urllib.request

    from allnews_mornitor.cdp_browser import _CdpClient

    list_url = f"http://{host}/json/list"
    try:
        with urllib.request.urlopen(list_url, timeout=5) as resp:
            pages = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        raise RuntimeError(f"无法连接 Chrome CDP（{host}）以刷新 X 会话: {e}") from e

    # Prefer an x.com page target
    candidates = []
    for page in pages or []:
        if not isinstance(page, dict) or not page.get("webSocketDebuggerUrl"):
            continue
        url = str(page.get("url") or "")
        score = 0
        if "x.com" in url and not url.startswith("blob:"):
            score += 10
        if "twitter.com" in url:
            score += 8
        if page.get("type") == "page":
            score += 2
        candidates.append((score, page))
    candidates.sort(key=lambda x: x[0], reverse=True)
    if not candidates:
        raise RuntimeError("CDP 无可用页签，无法刷新 X cookie/queryId")

    jar: Dict[str, str] = {}
    qids: Dict[str, str] = {}
    script_srcs: list[str] = []
    last_err: Optional[Exception] = None

    for score, page in candidates[:8]:
        ws = page["webSocketDebuggerUrl"]
        client = None
        try:
            client = _CdpClient(ws)
            client.call("Network.enable", {})
            try:
                res = client.call("Network.getAllCookies", {})
            except Exception:
                res = client.call(
                    "Network.getCookies",
                    {"urls": ["https://x.com", "https://twitter.com", "https://api.x.com"]},
                )
            for c in res.get("cookies") or []:
                if not isinstance(c, dict):
                    continue
                dom = str(c.get("domain") or "")
                if "x.com" not in dom and "twitter.com" not in dom:
                    continue
                name = str(c.get("name") or "")
                val = str(c.get("value") or "")
                if name and val:
                    jar[name] = val

            # queryIds from performance resource URLs + script tags
            ev = client.call(
                "Runtime.evaluate",
                {
                    "expression": """(() => {
  const out = {qids: {}, scripts: []};
  try {
    for (const e of (performance.getEntriesByType('resource') || [])) {
      const n = String(e.name || '');
      const m = n.match(/\\/graphql\\/([^/]+)\\/([A-Za-z0-9_]+)/);
      if (m) out.qids[m[2]] = m[1];
    }
  } catch (e) {}
  try {
    out.scripts = [...document.querySelectorAll('script[src]')]
      .map(s => s.src)
      .filter(u => /abs\\.twimg\\.com\\/responsive-web\\/client-web\\/(main|api|bundle)/.test(u))
      .slice(0, 8);
  } catch (e) {}
  return JSON.stringify(out);
})()""",
                    "returnByValue": True,
                },
            )
            raw_val = (ev.get("result") or {}).get("value")
            if isinstance(raw_val, str) and raw_val:
                try:
                    blob = json.loads(raw_val)
                    for k, v in (blob.get("qids") or {}).items():
                        if k and v:
                            qids[str(k)] = str(v)
                    for u in blob.get("scripts") or []:
                        if u and u not in script_srcs:
                            script_srcs.append(str(u))
                except Exception:
                    pass
            if jar.get("auth_token") and jar.get("ct0"):
                break
        except Exception as e:
            last_err = e
            continue
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

    if not jar.get("auth_token") or not jar.get("ct0"):
        raise RuntimeError(
            f"CDP 未读到 x.com auth_token/ct0（请先在调试 Chrome 登录 X）: {last_err or ''}"
        )

    # Supplement queryIds from client-web JS if still missing ops
    missing = [k for k in DEFAULT_QUERY_IDS if k not in qids]
    if missing and script_srcs:
        _log(f"X API：从 client-web 补 queryId（缺 {','.join(missing)}）…")
        for src in script_srcs[:3]:
            try:
                with urllib.request.urlopen(src, timeout=20) as resp:
                    js = resp.read().decode("utf-8", errors="ignore")
                qids.update(_extract_query_ids_from_js(js))
            except Exception:
                continue
            missing = [k for k in DEFAULT_QUERY_IDS if k not in qids]
            if not missing:
                break

    cookie_header = "; ".join(f"{k}={v}" for k, v in jar.items() if v)
    payload = {
        "auth_token": jar["auth_token"],
        "ct0": jar["ct0"],
        "authorization": DEFAULT_BEARER,
        "query_ids": _merge_query_ids(qids),
        "cookie_header": cookie_header,
    }
    if save:
        save_x_session(payload)
    session = load_x_session()
    if not session_ready(session):
        # build directly if file load somehow skips cookie_header-only
        session = {
            "auth_token": payload["auth_token"],
            "ct0": payload["ct0"],
            "authorization": DEFAULT_BEARER,
            "query_ids": payload["query_ids"],
            "cookie_header": cookie_header,
        }
    _log(
        "X API：CDP 会话已刷新 · "
        f"ct0={str(session.get('ct0') or '')[:6]}… · "
        f"queryIds={len((session or {}).get('query_ids') or {})}"
    )
    return session or payload

