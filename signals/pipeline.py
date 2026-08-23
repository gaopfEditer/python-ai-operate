# coding=utf-8
"""列表交易信号流水线：时间窗去重 → CDP 抓取 → 下图 → AI 解析 → 卡片。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from signals.analyze import analyze_tweet_signal
from signals.control import RunControl
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
from signals.tweet_log import clip_text, fmt_post_time, fmt_signal_line, fmt_tweet_line, resolve_display_time

ProgressCb = Optional[Callable[[str], None]]


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        try:
            cb(msg)
            return
        except Exception:
            pass
    print(f"[signals] {msg}", flush=True)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _wait_if_paused(control: Optional[RunControl], progress: ProgressCb) -> str:
    if control is None:
        return "ok"
    if control.is_paused():
        _log(progress, "已暂停，等待继续…")
    state = control.check()
    if state == "stop":
        return "stop"
    return "ok"


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
    control: Optional[RunControl] = None,
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

    save_config(
        {
            "list_id": lid,
            "cutoff_hours": hours,
            "max_tweets": limit,
            "skip_non_trade": skip_nt,
            "push_enabled": do_push,
        }
    )

    if control and control.is_stopped():
        return {"success": False, "error": "已终止", "aborted": True}

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

    _log(progress, "=" * 56)
    _log(progress, "列表信号：开始一轮")
    _log(progress, window_note)
    if _wait_if_paused(control, progress) == "stop":
        return {"success": False, "error": "已终止", "aborted": True, "message": "用户终止"}

    crawled = crawl_list_timeline(
        lid,
        since=floor,
        max_tweets=limit,
        progress=progress,
        should_abort=(lambda: bool(control and control.is_stopped())) if control else None,
    )
    if not crawled.get("success"):
        return crawled

    raw_items: List[Dict[str, Any]] = list(crawled.get("items") or [])
    fresh: List[Dict[str, Any]] = []
    filtered_old = 0
    filtered_seen = 0
    for it in raw_items:
        tid = str(it.get("tweet_id") or "")
        created = parse_dt(str(it.get("created_at") or ""))
        if created and _aware(created) < _aware(floor):
            filtered_old += 1
            _log(progress, f"[过滤] 早于窗口 · {fmt_tweet_line(it)}")
            continue
        if tid and is_seen(tid) and not reparse_seen:
            filtered_seen += 1
            _log(progress, f"[过滤] 已处理过 · {fmt_tweet_line(it)}")
            continue
        fresh.append(it)

    page_seen = int(crawled.get("page_seen") or 0)
    page_old = int(crawled.get("page_old") or 0)
    _log(
        progress,
        f"待解析 {len(fresh)} 条（窗口内抓取 {len(raw_items)}，"
        f"过滤过旧 {filtered_old}/已见 {filtered_seen}；页面见过 {page_seen} 其中过旧 {page_old}）",
    )
    if not fresh:
        if page_seen and not raw_items:
            _log(
                progress,
                "提示：页面上有帖，但都早于当前时间窗。"
                "可勾选「忽略已爬时间窗」后重跑，或等列表有新帖。",
            )
        elif not page_seen:
            _log(progress, "提示：页面未抽到推文，请确认 CDP Chrome 已登录 X 且列表 ID 正确。")
        else:
            _log(progress, "提示：窗口内帖子均已处理过；可勾选「重新解析已见」或等新帖。")

    cards: List[Dict[str, Any]] = []
    parsed = 0
    skipped = 0
    aborted = False
    newest: Optional[datetime] = None
    oldest: Optional[datetime] = None
    item_logs: List[Dict[str, Any]] = []

    for i, it in enumerate(fresh, 1):
        if _wait_if_paused(control, progress) == "stop":
            aborted = True
            _log(progress, f"用户终止于 {i - 1}/{len(fresh)}")
            break

        tid = str(it.get("tweet_id") or "")
        text = str(it.get("text") or "").strip()
        author = str(it.get("author") or "")
        created_raw = str(it.get("created_at") or "")
        time_label = str(it.get("time_label") or "")
        created = parse_dt(created_raw)
        if created:
            created = _aware(created)
            if newest is None or created > newest:
                newest = created
            if oldest is None or created < oldest:
                oldest = created

        preview = clip_text(text, 200) or ("（无文字，含图）" if it.get("images") else "（空）")
        time_s = fmt_post_time(created_raw, time_label, created)
        if time_s == "未知":
            time_s = resolve_display_time(created_raw, time_label, now.isoformat(timespec="seconds"))

        _log(progress, f"---------- 解析 [{i}/{len(fresh)}] ----------")
        _log(progress, f"发帖人: {author or '(未知)'}")
        _log(progress, f"发帖时间: {time_s}")
        _log(progress, f"正文前200字: {preview}")

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
            _log(progress, "是否交易信号=跳过（无正文且无图）")
            item_logs.append(
                {
                    "author": author,
                    "created_at": created_raw,
                    "preview": preview,
                    "has_trade_signal": False,
                    "skipped": True,
                }
            )
            continue

        if _wait_if_paused(control, progress) == "stop":
            aborted = True
            _log(progress, f"用户终止于解析前 {i}/{len(fresh)}")
            break

        signal = analyze_tweet_signal(
            text=text or "（无文字，见配图）",
            author=author,
            image_alts=alts,
            image_urls=urls,
        )
        sig_line = fmt_signal_line(signal, time_s=time_s)
        _log(progress, sig_line)

        item_logs.append(
            {
                "author": author,
                "created_at": created_raw,
                "time_label": time_label,
                "preview": preview,
                "has_trade_signal": bool(signal.get("has_trade_signal")),
                "direction": signal.get("direction"),
                "coins": signal.get("coins") or [],
                "summary": signal.get("summary") or "",
                "url": str(it.get("url") or ""),
            }
        )

        if skip_nt and not signal.get("has_trade_signal"):
            skipped += 1
            from signals.store import mark_seen

            if tid:
                mark_seen([tid])
            _log(progress, "结果: 无交易信号，已跳过入库")
            continue

        if not created_raw:
            created_raw = now.isoformat(timespec="seconds")
        if not time_label:
            time_label = time_s

        card = {
            "id": f"sig_{uuid4().hex[:10]}",
            "list_id": lid,
            "tweet_id": tid,
            "url": str(it.get("url") or ""),
            "author": author,
            "text": text,
            "created_at": created_raw,
            "time_label": time_label,
            "display_time": time_s,
            "images": images_meta,
            "signal": signal,
            "parsed_at": now.isoformat(timespec="seconds"),
        }
        upsert_card(card)
        cards.append(card)
        parsed += 1
        _log(
            progress,
            "结果: 已入库"
            + (" · 有交易信号" if signal.get("has_trade_signal") else " · 无交易信号仍保留"),
        )

    push_result: Dict[str, Any] = {
        "pushed": 0,
        "skipped": 0,
        "failed": 0,
        "items": [],
    }
    if aborted:
        msg = f"已终止：解析 {parsed}，跳过 {skipped}，抓取 {len(raw_items)}"
        win_from = (oldest or floor).isoformat(timespec="seconds")
        win_to = now.isoformat(timespec="seconds")
        win = add_window(
            list_id=lid,
            window_from=win_from,
            window_to=win_to,
            fetched=len(raw_items),
            parsed=parsed,
            skipped=skipped + (len(raw_items) - len(fresh)),
        )
        _log(progress, msg)
        _log(progress, "=" * 56)
        return {
            "success": True,
            "aborted": True,
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
            "item_logs": item_logs,
            "push": push_result,
            "message": msg,
        }

    if do_push and cards:
        if _wait_if_paused(control, progress) == "stop":
            _log(progress, "终止于推送前")
            _log(progress, "=" * 56)
            return {
                "success": True,
                "aborted": True,
                "list_id": lid,
                "list_url": list_url(lid),
                "fetched": len(raw_items),
                "parsed": parsed,
                "skipped": skipped,
                "cards": cards,
                "item_logs": item_logs,
                "push": push_result,
                "message": f"已终止（推送前）：解析 {parsed}",
            }
        _log(progress, f"推送增量卡片到 Cards API（{len(cards)}）…")
        push_result = push_cards_batch(cards, force=force_push, progress=progress)
    elif not do_push:
        push_result["reason"] = "push_disabled"

    win_from = (oldest or floor).isoformat(timespec="seconds")
    win_to = (newest or now).isoformat(timespec="seconds")
    if not fresh:
        win_from = floor.isoformat(timespec="seconds")
        win_to = now.isoformat(timespec="seconds")
    else:
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

    save_config({"last_crawl_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")})

    msg = (
        f"完成：解析 {parsed}，跳过 {skipped}，抓取 {len(raw_items)}"
        f" · 推送 {push_result.get('pushed', 0)}"
        f"（跳过 {push_result.get('skipped', 0)} / 失败 {push_result.get('failed', 0)}）"
    )
    _log(progress, msg)
    _log(progress, "=" * 56)
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
        "item_logs": item_logs,
        "push": push_result,
        "message": msg,
    }
