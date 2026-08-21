# coding=utf-8
"""列表交易信号流水线：时间窗去重 → CDP 抓取 → 下图 → AI 解析 → 卡片。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from signals.analyze import analyze_tweet_signal
from signals.crawl import crawl_list_timeline, download_image
from signals.push import push_cards_batch
from signals.store import (
    add_window,
    get_config,
    is_seen,
    latest_window_end,
    list_url,
    parse_dt,
    parse_list_id,
    save_config,
    upsert_card,
)

ProgressCb = Optional[Callable[[str], None]]


def _log(cb: ProgressCb, msg: str) -> None:
    print(f"[signals] {msg}")
    if cb:
        try:
            cb(msg)
        except Exception:
            pass


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def run_list_signal_pipeline(
    *,
    list_id: str = "",
    cutoff_hours: Optional[int] = None,
    max_tweets: Optional[int] = None,
    ignore_windows: bool = False,
    skip_non_trade: Optional[bool] = None,
    reparse_seen: bool = False,
    push: Optional[bool] = None,
    force_push: bool = False,
    progress: ProgressCb = None,
) -> Dict[str, Any]:
    cfg = get_config()
    lid = parse_list_id(list_id or str(cfg.get("list_id") or "")) or str(cfg.get("list_id") or "")
    if not lid:
        return {"success": False, "error": "请配置 X List ID 或列表链接"}

    hours = int(cutoff_hours if cutoff_hours is not None else cfg.get("cutoff_hours") or 24)
    hours = max(1, min(hours, 24 * 14))
    limit = int(max_tweets if max_tweets is not None else cfg.get("max_tweets") or 40)
    limit = max(1, min(limit, 120))
    skip_nt = (
        bool(skip_non_trade)
        if skip_non_trade is not None
        else bool(cfg.get("skip_non_trade"))
    )
    do_push = bool(cfg.get("push_enabled", True)) if push is None else bool(push)

    # 持久化本次配置
    save_config(
        {
            "list_id": lid,
            "cutoff_hours": hours,
            "max_tweets": limit,
            "skip_non_trade": skip_nt,
            "push_enabled": do_push,
        }
    )

    now = datetime.now(timezone.utc).astimezone()
    cutoff = now - timedelta(hours=hours)
    floor = cutoff
    window_note = f"截至 {hours}h（{cutoff.isoformat()}）"
    if not ignore_windows:
        last_end = latest_window_end(lid)
        if last_end is not None:
            last_end = _aware(last_end)
            if last_end > floor:
                floor = last_end
                window_note = (
                    f"截至 {hours}h，且跳过已爬区间 → 仅取 {floor.isoformat()} 之后"
                )
            else:
                window_note = f"截至 {hours}h；历史窗终点 {last_end.isoformat()} 已更早"

    _log(progress, window_note)
    crawled = crawl_list_timeline(
        lid,
        since=floor,
        max_tweets=limit,
        progress=progress,
    )
    if not crawled.get("success"):
        return crawled

    raw_items: List[Dict[str, Any]] = list(crawled.get("items") or [])
    # 再按 floor 过滤（JS 侧可能漏）
    fresh: List[Dict[str, Any]] = []
    for it in raw_items:
        tid = str(it.get("tweet_id") or "")
        created = parse_dt(str(it.get("created_at") or ""))
        if created and _aware(created) < _aware(floor):
            continue
        if tid and is_seen(tid) and not reparse_seen:
            continue
        fresh.append(it)

    _log(progress, f"待解析 {len(fresh)} 条（抓取 {len(raw_items)}，已去重/过滤）")

    cards: List[Dict[str, Any]] = []
    parsed = 0
    skipped = 0
    newest: Optional[datetime] = None
    oldest: Optional[datetime] = None

    for i, it in enumerate(fresh, 1):
        tid = str(it.get("tweet_id") or "")
        text = str(it.get("text") or "").strip()
        author = str(it.get("author") or "")
        created_raw = str(it.get("created_at") or "")
        created = parse_dt(created_raw)
        if created:
            created = _aware(created)
            if newest is None or created > newest:
                newest = created
            if oldest is None or created < oldest:
                oldest = created

        _log(progress, f"[{i}/{len(fresh)}] 解析 {author or tid}…")
        images_meta = []
        alts: List[str] = []
        urls: List[str] = []
        for j, im in enumerate(it.get("images") or []):
            if not isinstance(im, dict):
                continue
            u = str(im.get("url") or "")
            alt = str(im.get("alt") or "")
            if alt:
                alts.append(alt)
            if u:
                urls.append(u)
            saved = download_image(u, tid or f"x{i}", j)
            saved["alt"] = alt
            images_meta.append(saved)

        if not text and not images_meta:
            skipped += 1
            continue

        signal = analyze_tweet_signal(
            text=text or "（无文字，见配图）",
            author=author,
            image_alts=alts,
            image_urls=urls,
        )
        if skip_nt and not signal.get("has_trade_signal"):
            skipped += 1
            # 仍标记 seen，避免反复解析闲聊
            from signals.store import mark_seen

            if tid:
                mark_seen([tid])
            continue

        card = {
            "id": f"sig_{uuid4().hex[:10]}",
            "list_id": lid,
            "tweet_id": tid,
            "url": str(it.get("url") or ""),
            "author": author,
            "text": text,
            "created_at": created_raw,
            "time_label": str(it.get("time_label") or ""),
            "images": images_meta,
            "signal": signal,
            "parsed_at": now.isoformat(timespec="seconds"),
        }
        upsert_card(card)
        cards.append(card)
        parsed += 1

    push_result: Dict[str, Any] = {
        "pushed": 0,
        "skipped": 0,
        "failed": 0,
        "items": [],
    }
    if do_push and cards:
        _log(progress, f"推送增量卡片到 Cards API（{len(cards)}）…")
        push_result = push_cards_batch(cards, force=force_push, progress=progress)
    elif not do_push:
        push_result["reason"] = "push_disabled"

    win_from = (oldest or floor).isoformat(timespec="seconds")
    win_to = (newest or now).isoformat(timespec="seconds")
    # 即使本轮无新帖，也推进窗口到 now，避免空转重复扫同一段
    if not fresh:
        win_from = floor.isoformat(timespec="seconds")
        win_to = now.isoformat(timespec="seconds")
    else:
        # 覆盖到「现在」，后续默认只拉更新
        win_to = now.isoformat(timespec="seconds")
        if oldest:
            win_from = oldest.isoformat(timespec="seconds")

    win = add_window(
        list_id=lid,
        window_from=win_from,
        window_to=win_to,
        fetched=len(raw_items),
        parsed=parsed,
        skipped=skipped + (len(raw_items) - len(fresh)),
    )

    msg = (
        f"完成：解析 {parsed}，跳过 {skipped}，抓取 {len(raw_items)}"
        f" · 推送 {push_result.get('pushed', 0)}"
        f"（跳过 {push_result.get('skipped', 0)} / 失败 {push_result.get('failed', 0)}）"
    )
    return {
        "success": True,
        "list_id": lid,
        "list_url": list_url(lid),
        "cutoff_hours": hours,
        "floor": floor.isoformat(timespec="seconds"),
        "window": win,
        "fetched": len(raw_items),
        "candidates": len(fresh),
        "parsed": parsed,
        "skipped": skipped,
        "cards": cards,
        "push": push_result,
        "message": msg,
    }
