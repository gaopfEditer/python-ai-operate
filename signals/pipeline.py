# coding=utf-8
"""列表交易信号流水线：时间窗去重 → CDP 抓取 → 下图 → AI 解析 → 卡片。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from signals.analyze import analyze_tweet_signal
from signals.control import RunControl
from signals.crawl import crawl_list_timeline, crawl_user_timeline, download_image
from signals.push import push_cards_batch
from signals.store import (
    add_window,
    get_card_by_tweet_id,
    get_config,
    is_seen,
    latest_window_end,
    list_url,
    parse_dt,
    parse_list_id,
    save_config,
    upsert_card,
)
from signals.tweet_log import clip_text, fmt_item_summary_line, fmt_post_time, fmt_signal_line, fmt_tweet_line, resolve_display_time

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


def run_user_signal_pipeline(
    *,
    profile_url: str = "",
    user_handle: str = "",
    weeks: Optional[int] = None,
    max_tweets: Optional[int] = None,
    skip_non_trade: Optional[bool] = None,
    reparse_seen: bool = False,
    push: Optional[bool] = None,
    force_push: bool = False,
    progress: ProgressCb = None,
    control: Optional[RunControl] = None,
) -> Dict[str, Any]:
    """博主主页回溯：CDP 抓取 N 周 → AI 判交易信号 → 卡片入库 → Cards API。"""
    from signals.store import parse_user_handle, user_profile_url, user_scope_id

    cfg = get_config()
    handle = parse_user_handle(profile_url or user_handle or str(cfg.get("user_profile_url") or ""))
    if not handle:
        return {"success": False, "error": "请填写博主链接或 @handle"}

    wks = int(weeks if weeks is not None else cfg.get("user_weeks") or 1)
    wks = max(1, min(wks, 52))
    limit = int(max_tweets if max_tweets is not None else cfg.get("user_max_tweets") or wks * 50)
    limit = max(10, min(limit, 300))
    skip_nt = True if skip_non_trade is None else bool(skip_non_trade)
    do_push = bool(cfg.get("push_enabled", True)) if push is None else bool(push)
    scope = user_scope_id(handle)

    save_config(
        {
            "user_profile_url": user_profile_url(handle),
            "user_weeks": wks,
            "user_max_tweets": limit,
            "skip_non_trade": skip_nt,
            "push_enabled": do_push,
        }
    )

    if control and control.is_stopped():
        return {"success": False, "error": "已终止", "aborted": True}

    now = datetime.now(timezone.utc).astimezone()
    since = now - timedelta(days=wks * 7)
    max_scroll = max(35, min(wks * 30, 150))

    _log(progress, "=" * 56)
    _log(progress, f"博主回溯：@{handle} · 近 {wks} 周（自 {since.isoformat()}）")
    if _wait_if_paused(control, progress) == "stop":
        return {"success": False, "error": "已终止", "aborted": True, "message": "用户终止"}

    crawled = crawl_user_timeline(
        handle,
        since=since,
        max_tweets=limit,
        max_scroll=max_scroll,
        progress=progress,
        should_abort=(lambda: bool(control and control.is_stopped())) if control else None,
    )
    if not crawled.get("success"):
        return crawled

    raw_items: List[Dict[str, Any]] = list(crawled.get("items") or [])
    fresh: List[Dict[str, Any]] = []
    filtered_old = 0
    filtered_seen = 0
    filtered_cache = 0
    for it in raw_items:
        tid = str(it.get("tweet_id") or "")
        created = parse_dt(str(it.get("created_at") or ""))
        if created and _aware(created) < _aware(since):
            filtered_old += 1
            _log(progress, f"[过滤] 早于窗口 · {fmt_tweet_line(it)}")
            continue
        if tid and is_seen(tid) and not reparse_seen:
            cached = get_card_by_tweet_id(tid)
            if cached and isinstance(cached.get("signal"), dict):
                fresh.append(it)
                filtered_cache += 1
                _log(progress, f"[缓存] 将复用已解析 · {fmt_tweet_line(it)}")
                continue
            fresh.append(it)
            _log(progress, f"[补解析] 无缓存记录 · {fmt_tweet_line(it)}")
            continue
        fresh.append(it)

    _log(
        progress,
        f"待解析 {len(fresh)} 条（窗口内 {len(raw_items)}，"
        f"过滤过旧 {filtered_old}/已见 {filtered_seen}"
        f"{f'/缓存复用 {filtered_cache}' if filtered_cache else ''}）",
    )

    cards: List[Dict[str, Any]] = []
    trade_cards: List[Dict[str, Any]] = []
    parsed = 0
    skipped = 0
    reused_cache = 0
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
        author = str(it.get("author") or f"@{handle}")
        if not author.startswith("@"):
            author = f"@{parse_user_handle(author) or handle}"
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
        _log(progress, f"发帖人: {author}")
        _log(progress, f"发帖时间: {time_s}")
        _log(progress, f"正文前200字: {preview}")

        cached_card = get_card_by_tweet_id(tid) if tid and not reparse_seen else None
        from_cache = bool(cached_card and isinstance(cached_card.get("signal"), dict))

        images_meta = []
        alts: List[str] = []
        urls: List[str] = []
        if from_cache and cached_card:
            images_meta = list(cached_card.get("images") or [])
        else:
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

        if not text and not images_meta and not from_cache:
            skipped += 1
            _log(progress, "是否交易信号=跳过（无正文且无图）")
            ilog = {
                "author": author,
                "created_at": created_raw,
                "time_label": time_label,
                "display_time": time_s,
                "preview": preview,
                "has_trade_signal": False,
                "skipped": True,
                "result": "无正文且无图，已跳过",
                "url": str(it.get("url") or ""),
            }
            item_logs.append(ilog)
            summary = fmt_item_summary_line(ilog, index=i, total=len(fresh))
            ilog["summary_line"] = summary
            _log(progress, f"摘要 · {summary}")
            continue

        if _wait_if_paused(control, progress) == "stop":
            aborted = True
            break

        if from_cache and cached_card:
            signal = dict(cached_card["signal"])
            reused_cache += 1
            _log(progress, fmt_signal_line(signal, time_s=time_s) + " · 继承缓存")
        else:
            signal = analyze_tweet_signal(
                text=text or "（无文字，见配图）",
                author=author,
                image_alts=alts,
                image_urls=urls,
            )
            _log(progress, fmt_signal_line(signal, time_s=time_s))

        if skip_nt and not signal.get("has_trade_signal"):
            skipped += 1
            result_txt = "无交易信号，已跳过（缓存）" if from_cache else "无交易信号，已跳过"
            if not from_cache and tid:
                cache_card = {
                    "id": f"sig_{uuid4().hex[:10]}",
                    "list_id": scope,
                    "user_handle": handle,
                    "tweet_id": tid,
                    "url": str(it.get("url") or ""),
                    "author": author,
                    "text": text,
                    "created_at": created_raw or now.isoformat(timespec="seconds"),
                    "time_label": time_label or time_s,
                    "display_time": time_s,
                    "images": images_meta,
                    "signal": signal,
                    "parsed_at": now.isoformat(timespec="seconds"),
                    "source_mode": "user_backfill",
                    "cache_only": True,
                }
                upsert_card(cache_card)
            ilog = {
                "author": author,
                "created_at": created_raw,
                "time_label": time_label,
                "display_time": time_s,
                "preview": preview,
                "has_trade_signal": False,
                "direction": signal.get("direction"),
                "coins": signal.get("coins") or [],
                "summary": signal.get("summary") or "",
                "url": str(it.get("url") or ""),
                "from_cache": from_cache,
                "result": result_txt,
            }
            item_logs.append(ilog)
            summary = fmt_item_summary_line(ilog, index=i, total=len(fresh))
            ilog["summary_line"] = summary
            _log(progress, f"结果: {result_txt}")
            _log(progress, f"摘要 · {summary}")
            continue

        if from_cache and cached_card:
            cards.append(cached_card)
            if signal.get("has_trade_signal"):
                trade_cards.append(cached_card)
            parsed += 1
            result_txt = "继承缓存 · 有交易信号" if signal.get("has_trade_signal") else "继承缓存"
            ilog = {
                "author": author,
                "created_at": created_raw,
                "time_label": time_label,
                "display_time": time_s,
                "preview": preview,
                "has_trade_signal": bool(signal.get("has_trade_signal")),
                "direction": signal.get("direction"),
                "coins": signal.get("coins") or [],
                "summary": signal.get("summary") or "",
                "url": str(it.get("url") or ""),
                "from_cache": True,
                "result": result_txt,
            }
            item_logs.append(ilog)
            summary = fmt_item_summary_line(ilog, index=i, total=len(fresh))
            ilog["summary_line"] = summary
            _log(progress, f"结果: {result_txt}")
            _log(progress, f"摘要 · {summary}")
            continue

        if not created_raw:
            created_raw = now.isoformat(timespec="seconds")
        if not time_label:
            time_label = time_s

        card = {
            "id": f"sig_{uuid4().hex[:10]}",
            "list_id": scope,
            "user_handle": handle,
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
            "source_mode": "user_backfill",
        }
        upsert_card(card)
        cards.append(card)
        if signal.get("has_trade_signal"):
            trade_cards.append(card)
        parsed += 1
        has_trade = bool(signal.get("has_trade_signal"))
        result_txt = "已入库 · 有交易信号" if has_trade else "已入库"
        ilog = {
            "author": author,
            "created_at": created_raw,
            "time_label": time_label,
            "display_time": time_s,
            "preview": preview,
            "has_trade_signal": has_trade,
            "direction": signal.get("direction"),
            "coins": signal.get("coins") or [],
            "summary": signal.get("summary") or "",
            "url": str(it.get("url") or ""),
            "from_cache": False,
            "result": result_txt,
        }
        item_logs.append(ilog)
        summary = fmt_item_summary_line(ilog, index=i, total=len(fresh))
        ilog["summary_line"] = summary
        _log(progress, f"结果: {result_txt}")
        _log(progress, f"摘要 · {summary}")

    push_result: Dict[str, Any] = {"pushed": 0, "skipped": 0, "failed": 0, "items": []}
    push_targets = trade_cards if skip_nt else cards

    if not aborted and do_push and push_targets:
        if _wait_if_paused(control, progress) == "stop":
            aborted = True
        else:
            _log(progress, f"推送交易卡片到 Cards API（{len(push_targets)}）…")
            push_result = push_cards_batch(push_targets, force=force_push, progress=progress)
    elif not do_push:
        push_result["reason"] = "push_disabled"

    win_from = (oldest or since).isoformat(timespec="seconds")
    win_to = (newest or now).isoformat(timespec="seconds")
    win = add_window(
        list_id=scope,
        window_from=win_from,
        window_to=win_to,
        fetched=len(raw_items),
        parsed=parsed,
        skipped=skipped + (len(raw_items) - len(fresh)),
    )

    if item_logs:
        _log(progress, "")
        _log(progress, "======== 逐条摘要（验证用） ========")
        for j, ilog in enumerate(item_logs, 1):
            line = str(ilog.get("summary_line") or fmt_item_summary_line(ilog, index=j, total=len(item_logs)))
            _log(progress, line)

    msg = (
        f"博主 @{handle} 完成：抓取 {len(raw_items)} · 解析入库 {parsed}"
        f" · 无交易跳过 {skipped}"
        f" · 交易信号 {len(trade_cards)}"
        f" · 缓存复用 {reused_cache}"
        f" · 推送 {push_result.get('pushed', 0)}"
    )
    _log(progress, msg)
    _log(progress, "=" * 56)
    return {
        "success": True,
        "aborted": aborted,
        "handle": handle,
        "profile_url": user_profile_url(handle),
        "scope_id": scope,
        "weeks": wks,
        "since": since.isoformat(timespec="seconds"),
        "window": win,
        "fetched": len(raw_items),
        "candidates": len(fresh),
        "parsed": parsed,
        "skipped": skipped,
        "reused_cache": reused_cache,
        "trade_count": len(trade_cards),
        "cards": cards,
        "trade_cards": trade_cards,
        "item_logs": item_logs,
        "push": push_result,
        "message": msg,
    }
