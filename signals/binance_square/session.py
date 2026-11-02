# coding=utf-8
"""币安 Square HTTP 会话（Cookie + 指纹头，本地文件）。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SESSION_PATH = PROJECT_ROOT / "output" / "signals" / "binance_square_session.json"


def session_file_path() -> Path:
    raw = str(os.environ.get("BINANCE_SQUARE_SESSION_FILE") or "").strip()
    return Path(raw) if raw else DEFAULT_SESSION_PATH


def load_binance_session() -> Optional[Dict[str, Any]]:
    cookies: Dict[str, str] = {}
    headers: Dict[str, str] = {}

    for key in ("BNC_CSRF", "BNC_UUID"):
        val = str(os.environ.get(key) or "").strip()
        if val:
            lk = key.replace("BNC_", "").lower()
            cookies[lk] = val
            headers[lk] = val

    path = session_file_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if isinstance(data, dict):
            if isinstance(data.get("cookies"), dict):
                for k, v in data["cookies"].items():
                    if str(v).strip():
                        cookies[str(k)] = str(v).strip()
            if isinstance(data.get("headers"), dict):
                for k, v in data["headers"].items():
                    if str(v).strip():
                        headers[str(k)] = str(v).strip()

    if not cookies and not headers:
        return None
    for k, v in cookies.items():
        headers.setdefault(k, v)
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items() if v)
    return {"cookies": cookies, "headers": headers, "cookie_header": cookie_header}


def session_ready(session: Optional[Dict[str, Any]] = None) -> bool:
    s = session if session is not None else load_binance_session()
    if not s:
        return False
    hdr = s.get("headers") if isinstance(s.get("headers"), dict) else {}
    return bool(hdr.get("csrftoken") or hdr.get("bnc-uuid") or s.get("cookie_header"))


def save_binance_session(payload: Dict[str, Any], *, path: Optional[Path] = None) -> Path:
    dest = path or session_file_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    clean = {
        "cookies": dict(payload.get("cookies") or {}),
        "headers": dict(payload.get("headers") or {}),
    }
    dest.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest
