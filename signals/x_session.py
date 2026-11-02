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

    if not auth or not ct0:
        return None
    if bearer and not bearer.lower().startswith("bearer"):
        bearer = f"Bearer {bearer}"
    if not bearer:
        bearer = DEFAULT_BEARER

    return {
        "auth_token": auth,
        "ct0": ct0,
        "authorization": bearer,
        "query_ids": qids,
        "cookie_header": f"auth_token={auth}; ct0={ct0}",
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
