# coding=utf-8
"""fingerprint + cooldown。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from realtime_info.config import module_cfg
from realtime_info.storage.cache import is_cooled, mark_cooldown


def debounce_key(module: str, fingerprint: str) -> str:
    return f"{module}:{fingerprint}"


def pass_debounce(
    module: str,
    fingerprint: str,
    *,
    hours: Optional[float] = None,
    db_path: Optional[Path] = None,
) -> Tuple[bool, str]:
    key = debounce_key(module, fingerprint)
    if is_cooled(key, db_path=db_path):
        return False, ""
    cfg = module_cfg(module)
    h = float(hours if hours is not None else cfg.get("cooldown_hours") or 6)
    until = mark_cooldown(key, h, db_path=db_path)
    return True, until
