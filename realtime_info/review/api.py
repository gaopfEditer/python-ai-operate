# coding=utf-8
"""审阅 API 辅助（供 console 调用）。"""

from __future__ import annotations

from typing import Any, Dict

from realtime_info.models import STATUSES, Event
from realtime_info.storage.db import (
    count_events,
    get_event,
    list_events,
    stats,
    update_event_status,
)


def list_for_review(
    *,
    status: str = "pending",
    module: str = "",
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    items = list_events(status=status, module=module, limit=limit, offset=offset)
    return {
        "success": True,
        "items": [_public(e) for e in items],
        "total": count_events(status=status, module=module),
        "stats": stats(),
    }


def set_status(event_id: int, status: str, note: str = "") -> Dict[str, Any]:
    if status not in STATUSES:
        return {"success": False, "error": f"invalid status: {status}"}
    ev = update_event_status(event_id, status, note=note)
    if not ev:
        return {"success": False, "error": "not found"}
    return {"success": True, "item": _public(ev)}


def get_one(event_id: int) -> Dict[str, Any]:
    ev = get_event(event_id)
    if not ev:
        return {"success": False, "error": "not found"}
    return {"success": True, "item": _public(ev)}


def _public(e: Event) -> Dict[str, Any]:
    return {
        "id": e.id,
        "module": e.module,
        "fingerprint": e.fingerprint,
        "severity": e.severity,
        "title": e.title,
        "draft_text": e.draft_text,
        "raw": e.raw,
        "extracted": e.extracted,
        "status": e.status,
        "note": e.note,
        "cooled_until": e.cooled_until,
        "created_at": e.created_at,
        "updated_at": e.updated_at,
    }
