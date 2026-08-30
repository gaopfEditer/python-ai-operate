# coding=utf-8
"""事件入库管线：规则 → 防抖 → LLM → SQLite（不外发）。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from realtime_info.filters.debounce import pass_debounce
from realtime_info.llm import enrich_with_llm
from realtime_info.models import Event
from realtime_info.storage.db import insert_event

logger = logging.getLogger(__name__)


def ingest_event(
    *,
    module: str,
    fingerprint: str,
    raw: Dict[str, Any],
    title: str,
    draft_text: str,
    severity: str = "info",
    skip_llm: bool = False,
    cooldown_hours: Optional[float] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    返回 {"ok": bool, "skipped": reason?, "event": Event?}
    """
    ok, until = pass_debounce(
        module, fingerprint, hours=cooldown_hours, db_path=db_path
    )
    if not ok:
        return {"ok": False, "skipped": "cooldown", "event": None}

    if skip_llm:
        enriched = {
            "title": title,
            "draft_text": draft_text,
            "severity": severity,
            "extracted": {"source": "skip_llm"},
        }
    else:
        enriched = enrich_with_llm(
            module=module,
            raw=raw,
            fallback_title=title,
            fallback_draft=draft_text,
        )

    ev = Event(
        module=module,
        fingerprint=fingerprint,
        severity=str(enriched.get("severity") or severity),
        title=str(enriched.get("title") or title),
        draft_text=str(enriched.get("draft_text") or draft_text),
        raw=raw,
        extracted=dict(enriched.get("extracted") or {}),
        cooled_until=until,
        status="pending",
    )
    saved = insert_event(ev, db_path=db_path)
    if saved is None:
        return {"ok": False, "skipped": "duplicate_fingerprint", "event": None}

    # 外发占位：默认配置关闭，零外呼
    try:
        from realtime_info.bot.notify import notify_candidate
        from realtime_info.publishers.x_publish import publish_approved

        notify_candidate(saved)
        # 仅 pending 入库，不自动发推
        _ = publish_approved
    except Exception as e:
        logger.debug("outbound hooks: %s", e)

    return {"ok": True, "skipped": "", "event": saved}
