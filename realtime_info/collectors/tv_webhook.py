# coding=utf-8
"""D · TradingView Webhook 解析与入库。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from realtime_info.filters import rule_tv
from realtime_info.pipeline import ingest_event

logger = logging.getLogger(__name__)


def _norm_tf(tf: str) -> str:
    t = (tf or "").strip().upper().replace(" ", "")
    return {"60": "1H", "240": "4H"}.get(t, t)


def _norm_side(s: str) -> str:
    s = (s or "").strip().lower()
    if s in ("long", "buy", "多", "做多", "bull"):
        return "long"
    if s in ("short", "sell", "空", "做空", "bear"):
        return "short"
    return s or "alert"


def parse_tv_payload(body: Any) -> Dict[str, Any]:
    """接受 JSON dict 或纯文本 Alert 消息。"""
    if isinstance(body, dict):
        data = dict(body)
    elif isinstance(body, str):
        text = body.strip()
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                data = {"message": text}
        except Exception:
            data = {"message": text}
    else:
        data = {"message": str(body)}

    symbol = str(
        data.get("symbol") or data.get("ticker") or data.get("pair") or ""
    ).strip()
    if not symbol and data.get("message"):
        m = re.search(r"\b([A-Z]{2,10}USDT|[A-Z]{2,10})\b", str(data["message"]))
        if m:
            symbol = m.group(1)
    tf = str(data.get("timeframe") or data.get("interval") or data.get("tf") or "").strip()
    if not tf and data.get("message"):
        m = re.search(r"\b(1H|4H|60|240|1h|4h)\b", str(data["message"]))
        if m:
            tf = m.group(1)
    side = str(data.get("side") or data.get("direction") or data.get("order") or "").strip()
    structure = str(
        data.get("structure") or data.get("event") or data.get("strategy") or ""
    ).strip()
    msg = str(data.get("message") or data.get("text") or "").strip()

    return {
        **data,
        "symbol": symbol.upper().replace(".P", ""),
        "timeframe": _norm_tf(tf) if tf else "",
        "side": _norm_side(side),
        "structure": structure or "tv_alert",
        "message": msg,
    }


def handle_tv_webhook(
    body: Any,
    *,
    skip_llm: bool = False,
    db_path=None,
) -> Dict[str, Any]:
    payload = parse_tv_payload(body)
    ok, reason = rule_tv(payload)
    if not ok:
        return {"ok": False, "error": reason, "payload": payload}

    symbol = payload["symbol"]
    tf = payload["timeframe"] or "NA"
    side = payload["side"] or "alert"
    structure = payload.get("structure") or "tv_alert"
    fp = f"{symbol}:{side}:{tf}:{structure}".lower()

    title = f"[TV {tf}] {symbol} {side} · {structure}"
    draft = (
        f"{symbol} {tf} 结构信号：{structure}（{side}）\n"
        f"{payload.get('message') or ''}\n"
        f"仅作结构记录，非投资建议；同向 6h 内防抖。"
    ).strip()

    result = ingest_event(
        module="tv",
        fingerprint=fp,
        raw=payload,
        title=title,
        draft_text=draft,
        severity="warn",
        skip_llm=skip_llm,
        db_path=db_path,
    )
    if not result.get("ok"):
        return {
            "ok": False,
            "error": result.get("skipped") or "ingest_failed",
            "payload": payload,
        }
    ev = result["event"]
    return {
        "ok": True,
        "event_id": ev.id if ev else None,
        "fingerprint": fp,
        "title": ev.title if ev else title,
    }
