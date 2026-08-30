# coding=utf-8
"""统一事件模型。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import json


MODULES = ("onchain", "liq", "oi_funding", "tv", "unlock", "kol")
STATUSES = ("pending", "approved", "rejected", "snoozed")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Event:
    module: str
    fingerprint: str
    severity: str = "info"  # info | warn | high
    title: str = ""
    draft_text: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    extracted: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    note: str = ""
    cooled_until: str = ""
    created_at: str = ""
    updated_at: str = ""
    id: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = utc_now_iso()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_row(self) -> Dict[str, Any]:
        return {
            "module": self.module,
            "fingerprint": self.fingerprint,
            "severity": self.severity,
            "title": self.title,
            "draft_text": self.draft_text,
            "raw_json": json.dumps(self.raw or {}, ensure_ascii=False),
            "extracted_json": json.dumps(self.extracted or {}, ensure_ascii=False),
            "status": self.status,
            "note": self.note or "",
            "cooled_until": self.cooled_until or "",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


def row_to_event(row: Any) -> Event:
    def _j(v: Any) -> Dict[str, Any]:
        if isinstance(v, dict):
            return v
        if not v:
            return {}
        try:
            out = json.loads(v)
            return out if isinstance(out, dict) else {}
        except Exception:
            return {}

    return Event(
        id=int(row["id"]) if row["id"] is not None else None,
        module=str(row["module"] or ""),
        fingerprint=str(row["fingerprint"] or ""),
        severity=str(row["severity"] or "info"),
        title=str(row["title"] or ""),
        draft_text=str(row["draft_text"] or ""),
        raw=_j(row["raw_json"]),
        extracted=_j(row["extracted_json"]),
        status=str(row["status"] or "pending"),
        note=str(row["note"] or ""),
        cooled_until=str(row["cooled_until"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
    )
