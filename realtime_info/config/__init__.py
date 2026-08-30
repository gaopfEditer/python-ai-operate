# coding=utf-8
"""配置加载。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent.parent
CONFIG_DIR = PACKAGE_DIR
DEFAULT_SETTINGS = CONFIG_DIR / "settings.yaml"
DEFAULT_ENTITIES = CONFIG_DIR / "entities.yaml"
DEFAULT_KOL = CONFIG_DIR / "kol_watchlist.yaml"
OUTPUT_DIR = PROJECT_ROOT / "output" / "realtime_info"
DB_PATH = OUTPUT_DIR / "events.db"


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def load_settings(*, reload: bool = False) -> Dict[str, Any]:
    if reload:
        load_settings.cache_clear()
    return _load_yaml(DEFAULT_SETTINGS)


def load_entities() -> Dict[str, Any]:
    return _load_yaml(DEFAULT_ENTITIES)


def load_kol_watchlist() -> Dict[str, Any]:
    return _load_yaml(DEFAULT_KOL)


def module_enabled(module: str, settings: Optional[Dict[str, Any]] = None) -> bool:
    cfg = settings or load_settings()
    mods = cfg.get("modules") if isinstance(cfg.get("modules"), dict) else {}
    m = mods.get(module) if isinstance(mods.get(module), dict) else {}
    return bool(m.get("enabled", False))


def module_cfg(module: str, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = settings or load_settings()
    mods = cfg.get("modules") if isinstance(cfg.get("modules"), dict) else {}
    m = mods.get(module)
    return dict(m) if isinstance(m, dict) else {}


def env_or(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()


def ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR
