# coding=utf-8
"""币安 Square 帖 → 列表信号 SQLite 卡片（与博主回溯同源存储）。"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from signals.binance_square.store import parse_post_time, post_content_id

ProgressCb = Optional[Callable[[str], None]]
BINANCE_LIST_ROOT = "binance:square"


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)


def _display_time(post: Dict[str, Any]) -> str:
    tl = str(post.get("time_label") or "").strip()
    if tl:
        return tl
    iso = str(post.get("published_iso") or "").strip()
    if iso:
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return iso[:19]
    return ""


def _created_iso_and_ts(post: Dict[str, Any]) -> tuple[str, int]:
    """避免「10月5日」等同日帖共用同一 created_at_ts 被 SQLite 唯一索引覆盖。"""
    cid = post_content_id(post) or str(post.get("live_content_id") or "").strip()
    dt = parse_post_time(post)
    now = datetime.now(timezone.utc)
    if dt is not None:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        base_ts = int(dt.timestamp())
        iso = dt.astimezone().isoformat(timespec="seconds")
    elif post.get("published_iso"):
        iso = str(post.get("published_iso") or "").strip()
        try:
            pdt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            if pdt.tzinfo is None:
                pdt = pdt.replace(tzinfo=timezone.utc)
            base_ts = int(pdt.timestamp())
        except Exception:
            base_ts = int(now.timestamp())
    else:
        iso = now.astimezone().isoformat(timespec="seconds")
        base_ts = int(now.timestamp())
    if cid.isdigit():
        spread = int(cid[-7:]) % 86400
        base_ts += spread
    return iso, base_ts


def square_post_to_card(post: Dict[str, Any]) -> Dict[str, Any]:
    slug = str(post.get("profile_id") or post.get("author_slug") or "").strip().lower()
    name = str(post.get("profile_name") or slug or "Square").strip()
    cid = post_content_id(post) or str(post.get("live_content_id") or "").strip()
    href = str(post.get("href") or "").strip()
    text = str(post.get("raw") or post.get("title") or "").strip()
    created, created_ts = _created_iso_and_ts(post)
    time_label = str(post.get("time_label") or "").strip()
    disp = _display_time(post)
    images = []
    for u in post.get("image_urls") or []:
        url = str(u or "").strip()
        if url:
            images.append({"url": url, "alt": ""})
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    author = f"@{slug}" if slug else name
    card = {
        "id": f"bs_{cid}" if cid else f"bs_{uuid4().hex[:10]}",
        "list_id": f"binance:{slug}" if slug else BINANCE_LIST_ROOT,
        "user_handle": slug,
        "tweet_id": cid or href.rsplit("/", 1)[-1][:32],
        "url": href,
        "author": author,
        "text": text,
        "created_at": created,
        "time_label": time_label,
        "display_time": disp or time_label or created[:19],
        "images": images[:12],
        "signal": post.get("signal") if isinstance(post.get("signal"), dict) else {},
        "parsed_at": now,
        "source_mode": "binance_square",
        "source_modes": ["binance_square", "binance_backfill"],
        "channel": {"channelName": name},
        "replay_url": str(post.get("replay_url") or "").strip(),
        "video_url": str(post.get("video_url") or "").strip(),
        "live_content_id": str(post.get("live_content_id") or "").strip(),
    }
    card["_created_at_ts"] = created_ts
    return card


def sync_posts_to_signal_cards(
    posts: List[Dict[str, Any]],
    *,
    backfill_range: str = "",
    range_label: str = "",
    since_iso: str = "",
    progress: ProgressCb = None,
) -> Dict[str, Any]:
    from signals.store import add_window, upsert_card

    rows = [p for p in (posts or []) if isinstance(p, dict)]
    if not rows:
        return {"synced": 0, "skipped": 0}

    synced = 0
    oldest: Optional[datetime] = None
    newest: Optional[datetime] = None
    now = datetime.now(timezone.utc).astimezone()

    for p in rows:
        card = square_post_to_card(p)
        if not card.get("tweet_id") and not card.get("url"):
            continue
        upsert_card(card)
        synced += 1
        dt = parse_post_time(p)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if oldest is None or dt < oldest:
                oldest = dt
            if newest is None or dt > newest:
                newest = dt

    br = str(backfill_range or "")
    rl = str(range_label or "")
    since = str(since_iso or "")

    def _window_for_subset(subset: List[Dict[str, Any]]) -> tuple[str, str]:
        o: Optional[datetime] = None
        n: Optional[datetime] = None
        for p in subset:
            dt = parse_post_time(p)
            if dt is None:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if o is None or dt < o:
                o = dt
            if n is None or dt > n:
                n = dt
        return (o or now).isoformat(timespec="seconds"), (n or now).isoformat(timespec="seconds")

    by_slug: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in rows:
        slug = str(p.get("profile_id") or p.get("author_slug") or "square").strip() or "square"
        by_slug[slug].append(p)
    for slug, subset in by_slug.items():
        wf, wt = _window_for_subset(subset)
        add_window(
            list_id=f"binance:{slug}",
            window_from=wf,
            window_to=wt,
            fetched=len(subset),
            parsed=len(subset),
            skipped=0,
            backfill_range=br,
            range_label=rl,
            since=since,
        )
    win_from = (oldest or now).isoformat(timespec="seconds")
    win_to = (newest or now).isoformat(timespec="seconds")
    add_window(
        list_id=BINANCE_LIST_ROOT,
        window_from=win_from,
        window_to=win_to,
        fetched=len(rows),
        parsed=synced,
        skipped=max(0, len(rows) - synced),
        backfill_range=br,
        range_label=rl,
        since=since,
    )
    _log(progress, f"Square 卡片入库 {synced} 条（SQLite · 与博主回溯共用）")
    return {"synced": synced, "skipped": max(0, len(rows) - synced)}


def _binance_cards_in_db() -> int:
    from signals.card_db import connect, init_db

    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM signal_cards WHERE list_id LIKE 'binance:%'"
        ).fetchone()
    return int(row["c"] if row else 0)


def ensure_binance_cards_materialized(*, progress: ProgressCb = None) -> Dict[str, Any]:
    """
    若 SQLite 尚无 binance 卡片但 state 里有 last_posts，则补写入库。
    （避免仅升级代码、未重跑抓取时刷新页面变空。）
    """
    from signals.backfill_range import BACKFILL_RANGE_LABELS, resolve_backfill_since
    from signals.binance_square.store import load_config, load_state

    st = load_state()
    posts = st.get("last_posts") or st.get("last_posts_raw") or []
    if not isinstance(posts, list):
        posts = []
    posts = [p for p in posts if isinstance(p, dict)]
    if not posts:
        return {"synced": 0, "reason": "no_state_posts"}

    existing = _binance_cards_in_db()
    need = len(posts)
    if existing >= max(1, need - 2):
        return {"synced": 0, "already_in_db": existing, "reason": "already_in_db"}

    if existing > 0 and existing < need:
        from signals.card_db import db_delete_binance_square_cards

        _log(progress, f"Square 卡片数 {existing}/{need}，重建 SQLite 索引…")
        db_delete_binance_square_cards("")
        existing = 0

    cfg = load_config()
    rk = str(cfg.get("backfill_range") or "last_7d")
    since_dt, range_label = resolve_backfill_since(rk)
    from signals.binance_square.store import apply_binance_time_filter

    posts = apply_binance_time_filter(posts, backfill_range=rk, cfg=cfg)
    if not posts:
        return {"synced": 0, "reason": "no_posts_in_range", "already_in_db": existing}
    _log(progress, f"从 Square 缓存补同步 {len(posts)} 条到 SQLite（{rk}）…")
    out = sync_posts_to_signal_cards(
        posts,
        backfill_range=rk,
        range_label=range_label or BACKFILL_RANGE_LABELS.get(rk, rk),
        since_iso=since_dt.isoformat(timespec="seconds"),
        progress=progress,
    )
    out["reason"] = "materialized_from_state"
    out["already_in_db"] = 0
    return out
