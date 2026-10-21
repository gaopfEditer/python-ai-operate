# coding=utf-8
"""实时源产出卡片：严格币种门槛后写入 SQLite。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from signals.coin_detect import coin_gate_reason, extract_coins_strict, has_listed_coin

ProgressCb = Optional[Callable[[str], None]]


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)


def _merge_signal_coins(text: str, signal: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    sig = dict(signal) if isinstance(signal, dict) else {}
    coins = extract_coins_strict(text, sig)
    if coins:
        sig["coins"] = coins
    return sig


def emit_binance_square_cards(
    *,
    profile_ids: Optional[List[str]] = None,
    cutoff_hours: Optional[float] = None,
    progress: ProgressCb = None,
) -> Dict[str, Any]:
    from signals.binance_square.cards_sync import sync_posts_to_signal_cards
    from signals.binance_square.store import apply_binance_time_filter, load_config, load_state

    st = load_state()
    posts = st.get("last_posts") or st.get("last_posts_raw") or []
    if not isinstance(posts, list):
        posts = []
    cfg = load_config()
    if cutoff_hours is not None:
        from datetime import timedelta

        since = datetime.now(timezone.utc) - timedelta(hours=max(1, float(cutoff_hours)))
        posts = [
            p
            for p in posts
            if isinstance(p, dict)
            and (
                not p.get("published_iso")
                or datetime.fromisoformat(str(p["published_iso"]).replace("Z", "+00:00"))
                >= since.replace(tzinfo=timezone.utc)
            )
        ]
    else:
        rk = str(cfg.get("backfill_range") or "last_7d")
        posts = apply_binance_time_filter(posts, backfill_range=rk, cfg=cfg)

    if profile_ids:
        want = {str(x).strip().lower() for x in profile_ids if str(x).strip()}
        posts = [
            p
            for p in posts
            if str(p.get("profile_id") or p.get("author_slug") or "").lower() in want
        ]

    eligible: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for p in posts:
        if not isinstance(p, dict):
            continue
        text = str(p.get("raw") or p.get("title") or "")
        sig = p.get("signal") if isinstance(p.get("signal"), dict) else {}
        if not has_listed_coin(text, sig):
            cid = str(p.get("live_content_id") or p.get("content_id") or "")[:24]
            rejected.append(
                {
                    "id": cid,
                    "reason": "no_coin",
                    "message": coin_gate_reason(text, sig),
                    "preview": text[:120],
                }
            )
            continue
        patch = dict(p)
        patch["signal"] = _merge_signal_coins(text, sig)
        eligible.append(patch)

    if not eligible:
        return {
            "success": True,
            "source": "binance_square",
            "created": 0,
            "rejected": rejected,
            "skipped": 0,
            "message": "无含币种的 Square 帖可入库",
        }

    _log(progress, f"Square 产出卡片：{len(eligible)} 条含币种（拒绝 {len(rejected)}）")
    out = sync_posts_to_signal_cards(eligible, progress=progress, require_coin=True)
    out["success"] = True
    out["source"] = "binance_square"
    out["rejected"] = rejected
    out["created"] = int(out.get("synced") or 0)
    out["message"] = f"Square 产出 {out['created']} 张卡片（拒绝无币种 {len(rejected)}）"
    return out


def emit_kol_realtime_cards(
    *,
    session_id: str = "",
    progress: ProgressCb = None,
) -> Dict[str, Any]:
    from signals.store import (
        get_config,
        load_state,
        parse_user_handle,
        save_state,
        upsert_card,
        user_scope_id,
    )

    st = load_state()
    pending = st.get("kol_realtime_pending")
    if not isinstance(pending, list):
        pending = []

    cfg = get_config()
    sid = str(session_id or cfg.get("kol_realtime_session_id") or "").strip()

    created = 0
    skipped = 0
    rejected: List[Dict[str, Any]] = []
    keep: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc).astimezone()

    for row in pending:
        if not isinstance(row, dict):
            continue
        if sid and str(row.get("realtime_session_id") or "") != sid:
            keep.append(row)
            continue
        text = str(row.get("text") or "")
        sig = row.get("signal") if isinstance(row.get("signal"), dict) else {}
        if not has_listed_coin(text, sig):
            rejected.append(
                {
                    "id": str(row.get("tweet_id") or ""),
                    "reason": "no_coin",
                    "message": coin_gate_reason(text, sig),
                    "preview": text[:120],
                }
            )
            continue
        handle = parse_user_handle(str(row.get("user_handle") or row.get("author") or ""))
        if not handle:
            rejected.append({"id": "", "reason": "no_handle", "message": "缺少博主 handle", "preview": text[:80]})
            continue
        scope = user_scope_id(handle)
        signal = _merge_signal_coins(text, sig)
        tid = str(row.get("tweet_id") or "")
        card = {
            "id": f"sig_{uuid4().hex[:10]}",
            "list_id": scope,
            "user_handle": handle,
            "tweet_id": tid,
            "url": str(row.get("url") or ""),
            "author": str(row.get("author") or f"@{handle}"),
            "text": text,
            "created_at": str(row.get("created_at") or now.isoformat(timespec="seconds")),
            "time_label": str(row.get("time_label") or ""),
            "display_time": str(row.get("display_time") or row.get("time_label") or ""),
            "images": row.get("images") if isinstance(row.get("images"), list) else [],
            "signal": signal,
            "parsed_at": now.isoformat(timespec="seconds"),
            "source_mode": "kol_realtime",
            "source_modes": ["kol_realtime", "list_realtime"],
            "realtime_session_id": sid,
        }
        upsert_card(card)
        created += 1

    st["kol_realtime_pending"] = keep
    save_state(st)

    msg = f"KOL 实时产出 {created} 张卡片（拒绝无币种 {len(rejected)}，保留其他会话 {len(keep)}）"
    _log(progress, msg)
    return {
        "success": True,
        "source": "kol_realtime",
        "session_id": sid,
        "created": created,
        "skipped": skipped,
        "rejected": rejected,
        "pending_left": len(keep),
        "message": msg,
    }
