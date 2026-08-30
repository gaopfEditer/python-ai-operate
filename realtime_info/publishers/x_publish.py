# coding=utf-8
"""X 分发空壳（默认关闭）。"""

from __future__ import annotations

import logging
from typing import Any, Dict

from realtime_info.config import load_settings
from realtime_info.models import Event

logger = logging.getLogger(__name__)


def publish_approved(event: Event) -> Dict[str, Any]:
    cfg = load_settings()
    px = cfg.get("publish_x") if isinstance(cfg.get("publish_x"), dict) else {}
    if not px.get("enabled"):
        return {"ok": False, "skipped": "publish_x.disabled"}
    if event.status != "approved":
        return {"ok": False, "skipped": "not_approved"}
    logger.warning("publish_x.enabled=true 但尚未接线 XPublisher，event=#%s", event.id)
    return {"ok": False, "skipped": "not_implemented", "event_id": event.id}
