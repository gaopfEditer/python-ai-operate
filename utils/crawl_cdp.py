# coding=utf-8
"""抓取用 Chrome CDP 地址：环境变量 > 主配置 > allnews 配置 > 默认 9223。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

DEFAULT_CRAWL_CDP = "127.0.0.1:9223"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _normalize(host: str) -> str:
    h = (host or "").strip()
    if h.startswith("http://"):
        h = h[len("http://") :]
    elif h.startswith("https://"):
        h = h[len("https://") :]
    return h.rstrip("/")


def resolve_crawl_debugger_url(override: Optional[str] = None) -> str:
    """
    解析资讯/列表信号等「抓取」使用的 CDP 地址。
    优先级：
      1. 显式 override
      2. 环境变量 CDP_DEBUGGER_URL / TRENDRADAR_CDP_URL
      3. config/config.yaml → crawler.x_cdp.debugger_url
      4. allnews_mornitor/config.yaml → cdp.debugger_url
      5. 默认 127.0.0.1:9223
    """
    if override and str(override).strip():
        return _normalize(str(override))

    for key in ("CDP_DEBUGGER_URL", "TRENDRADAR_CDP_URL"):
        env = os.environ.get(key, "").strip()
        if env:
            return _normalize(env)

    try:
        import yaml

        main_cfg = _PROJECT_ROOT / "config" / "config.yaml"
        if main_cfg.is_file():
            with open(main_cfg, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            host = str(
                ((cfg.get("crawler") or {}).get("x_cdp") or {}).get("debugger_url") or ""
            ).strip()
            if host:
                return _normalize(host)
    except Exception:
        pass

    try:
        import yaml

        an_cfg = _PROJECT_ROOT / "allnews_mornitor" / "config.yaml"
        if an_cfg.is_file():
            with open(an_cfg, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            host = str((cfg.get("cdp") or {}).get("debugger_url") or "").strip()
            if host:
                return _normalize(host)
    except Exception:
        pass

    return DEFAULT_CRAWL_CDP
