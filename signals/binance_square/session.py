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
    csrf = cookies.get("csrftoken") or headers.get("csrftoken") or ""
    if csrf:
        headers["csrftoken"] = csrf
        headers.setdefault("BNC-CSRF-TOKEN", csrf)
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items() if v)
    return {"cookies": cookies, "headers": headers, "cookie_header": cookie_header}


def get_active_binance_session_for_http() -> Optional[Dict[str, Any]]:
    try:
        from signals.cdp_session_loader import get_cached_binance_session

        return get_cached_binance_session()
    except Exception:
        return load_binance_session()


def session_diagnostics(session: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    s = session if session is not None else get_active_binance_session_for_http()
    if not s:
        return {"ready": False, "has_cookie": False, "has_fingerprint": False}
    hdr = s.get("headers") if isinstance(s.get("headers"), dict) else {}
    has_cookie = bool(s.get("cookie_header") or hdr.get("csrftoken") or hdr.get("bnc-uuid"))
    has_fp = bool(hdr.get("device-info") or hdr.get("fvideo-id") or hdr.get("fvideo-token"))
    return {"ready": session_ready(s), "has_cookie": has_cookie, "has_fingerprint": has_fp}


def merge_supplemental_headers(
    primary: Dict[str, Any], supplemental: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """CDP Cookie 为主；本地文件仅补充 device-info 等指纹头（不覆盖 Cookie）。"""
    out = {
        "cookies": dict(primary.get("cookies") or {}),
        "headers": dict(primary.get("headers") or {}),
        "cookie_header": str(primary.get("cookie_header") or ""),
    }
    if not supplemental:
        return out
    extra = supplemental.get("headers") if isinstance(supplemental.get("headers"), dict) else {}
    fp_keys = ("device-info", "fvideo-id", "fvideo-token")
    hdr = out["headers"]
    for k in fp_keys:
        v = str(extra.get(k) or "").strip()
        if v and not str(hdr.get(k) or "").strip():
            hdr[k] = v
    csrf = out["cookies"].get("csrftoken") or hdr.get("csrftoken") or ""
    if csrf:
        hdr["csrftoken"] = csrf
        hdr.setdefault("BNC-CSRF-TOKEN", csrf)
    if not out["cookie_header"]:
        out["cookie_header"] = "; ".join(
            f"{k}={v}" for k, v in out["cookies"].items() if str(v).strip()
        )
    return out


def resolve_binance_session(
    *,
    debugger_url: str = "",
    progress=None,
    force_refresh: bool = False,
) -> Optional[Dict[str, Any]]:
    from signals.cdp_session_loader import refresh_binance_session_from_cdp

    cfg_dbg = ""
    try:
        from signals.binance_square.store import load_config

        cfg_dbg = str(load_config().get("debugger_url") or "")
    except Exception:
        pass
    return refresh_binance_session_from_cdp(
        debugger_url=debugger_url,
        binance_cfg_debugger=cfg_dbg,
        progress=progress,
        force_refresh=force_refresh,
    )


def session_ready(session: Optional[Dict[str, Any]] = None) -> bool:
    if session is not None:
        s = session
    else:
        try:
            from signals.cdp_session_loader import get_cached_binance_session

            s = get_cached_binance_session()
        except Exception:
            s = load_binance_session()
    if not s:
        return False
    if str(s.get("cookie_header") or "").strip():
        return True
    hdr = s.get("headers") if isinstance(s.get("headers"), dict) else {}
    return bool(hdr.get("csrftoken") or hdr.get("bnc-uuid"))


def save_binance_session(payload: Dict[str, Any], *, path: Optional[Path] = None) -> Path:
    dest = path or session_file_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    clean = {
        "cookies": dict(payload.get("cookies") or {}),
        "headers": dict(payload.get("headers") or {}),
    }
    dest.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest
