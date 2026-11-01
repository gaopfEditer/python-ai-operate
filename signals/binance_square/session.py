# coding=utf-8
"""币安 Square HTTP/bapi 会话：Cookie 路径与请求头（与 WhisprRT 共用 binance_cookies.txt）。"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def whispr_root() -> Path:
    raw = os.environ.get("WHISPRT_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    try:
        import yaml

        cfg_path = PROJECT_ROOT / "config" / "config.yaml"
        if cfg_path.is_file():
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            root = str((cfg.get("whisper") or {}).get("root") or "").strip()
            if root:
                return Path(root).expanduser().resolve()
    except Exception:
        pass
    return Path("/Users/maotouying/frontend/code/1.operations/WhisprRT")


def default_cookie_path() -> Path:
    env = os.environ.get("BINANCE_COOKIES_FILE", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (whispr_root() / "binance_cookies.txt").resolve()


def cookie_header_from_file(path: Path, *, domain_suffix: str = "binance.com") -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return ""
    if not text.lstrip().startswith("#"):
        return text
    pairs: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, name, value = parts[0], parts[5], parts[6]
        if domain_suffix in domain.lstrip("."):
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def cookie_jar_from_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        out[parts[5]] = parts[6]
    return out


def ensure_binance_cookies(*, on_log: Any = None) -> Optional[Path]:
    from console.whisper_service import ensure_binance_cookies_file

    root = whispr_root()
    return ensure_binance_cookies_file(root, on_log=on_log)


def bapi_headers(
    *,
    cookie_path: Optional[Path] = None,
    referer: str = "https://www.binance.com/zh-CN/square",
    lang: str = "zh-CN",
) -> Dict[str, str]:
    path = cookie_path or default_cookie_path()
    cookie = cookie_header_from_file(path)
    jar = cookie_jar_from_file(path)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "clienttype": "web",
        "lang": lang,
        "Referer": referer,
        "Origin": "https://www.binance.com",
    }
    if cookie:
        headers["Cookie"] = cookie
    for key in ("csrftoken", "csrfToken"):
        if jar.get(key):
            headers["csrftoken"] = jar[key]
            break
    bnc_uuid = jar.get("bnc-uuid") or jar.get("BNC-UUID")
    if bnc_uuid:
        headers["bnc-uuid"] = bnc_uuid
    extra = os.environ.get("BINANCE_SQUARE_HEADERS_JSON", "").strip()
    if extra:
        try:
            import json

            more = json.loads(extra)
            if isinstance(more, dict):
                headers.update({str(k): str(v) for k, v in more.items()})
        except Exception:
            pass
    return headers


def profile_referer(profile_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]", "", str(profile_id or "").strip()) or "square"
    return f"https://www.binance.com/zh-CN/square/profile/{slug}"
