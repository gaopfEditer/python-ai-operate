# coding=utf-8
"""本地信号卡片：编辑正文后重新 AI 解析。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from signals.analyze import analyze_tweet_signal
from signals.store import get_card_by_tweet_id, unmark_pushed, upsert_card


def _merge_text(original: str, text: str, supplement: str) -> str:
    base = str(text if text is not None else original or "").strip()
    extra = str(supplement or "").strip()
    if not base and extra:
        return extra
    if extra and extra not in base:
        return f"{base}\n\n{extra}".strip() if base else extra
    return base


def reparse_local_card(
    tweet_id: str,
    *,
    text: Optional[str] = None,
    supplement: str = "",
) -> Dict[str, Any]:
    tid = str(tweet_id or "").strip()
    if not tid:
        return {"success": False, "error": "缺少 tweet_id"}

    card = get_card_by_tweet_id(tid)
    if not card:
        return {"success": False, "error": f"未找到卡片 tweet_id={tid}"}

    merged = _merge_text(str(card.get("text") or ""), text or "", supplement)
    if not merged:
        return {"success": False, "error": "正文不能为空"}

    images = card.get("images") if isinstance(card.get("images"), list) else []
    alts: List[str] = []
    urls: List[str] = []
    for im in images:
        if not isinstance(im, dict):
            continue
        alt = str(im.get("alt") or "").strip()
        url = str(im.get("url") or im.get("local_path") or "").strip()
        if alt:
            alts.append(alt)
        if url:
            urls.append(url)

    author = str(card.get("author") or "")
    signal = analyze_tweet_signal(
        text=merged,
        author=author,
        image_alts=alts,
        image_urls=urls,
    )

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    updated = dict(card)
    updated["text"] = merged
    updated["signal"] = signal
    updated["parsed_at"] = now
    updated.pop("cache_only", None)
    upsert_card(updated)
    unmark_pushed([tid])

    prev_trade = bool(
        isinstance(card.get("signal"), dict) and card["signal"].get("has_trade_signal")
    )
    now_trade = bool(signal.get("has_trade_signal"))

    return {
        "success": True,
        "card": updated,
        "signal": signal,
        "tweet_id": tid,
        "trade_changed": prev_trade != now_trade,
        "was_trade": prev_trade,
        "is_trade": now_trade,
        "cleared_push": True,
    }
