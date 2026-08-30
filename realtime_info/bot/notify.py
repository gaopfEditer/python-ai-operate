# coding=utf-8
"""Telegram 通知空壳（默认关闭）。"""

from __future__ import annotations

import logging
from typing import Any, Dict

from realtime_info.config import load_settings
from realtime_info.models import Event

logger = logging.getLogger(__name__)


def notify_candidate(event: Event) -> Dict[str, Any]:
    cfg = load_settings()
    tg = cfg.get("telegram") if isinstance(cfg.get("telegram"), dict) else {}
    if not tg.get("enabled"):
        return {"ok": False, "skipped": "telegram.disabled"}
    logger.warning("telegram.enabled=true 但 Bot 尚未实现，event=#%s", event.id)
    return {"ok": False, "skipped": "not_implemented", "event_id": event.id}
