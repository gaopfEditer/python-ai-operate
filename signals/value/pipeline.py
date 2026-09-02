# coding=utf-8
"""价值回归流水线。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from signals.control import RunControl
from signals.store import get_config, parse_list_id, parse_dt, save_config, upsert_card
from signals.tweet_log import clip_text, fmt_tweet_line
from signals.value.deduplicator import already_evaluated
from signals.value.evaluator import evaluate_tweet
from signals.value.fetcher import fetch_list_tweets
from signals.value.notifier import get_notifier
from signals.value.prefilter import prefilter_tweet
from signals.value.store_policy import apply_store_policy
from signals.value.threshold import resolve_threshold_for_eval

ProgressCb = Optional[Callable[[str], None]]


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        try:
            cb(msg)
            return
        except Exception:
            pass
    print(msg, flush=True)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _wait_if_paused(control: Optional[RunControl], progress: ProgressCb) -> str:
    if not control:
        return "ok"
    while control.is_paused() and not control.is_stopped():
        _log(progress, "已暂停…")
        control.wait_while_paused(0.8)
    if control.is_stopped():
        return "stop"
    return "ok"


def run_value_return_pipeline(
    *,
    list_id: str = "",
    cutoff_hours: Optional[int] = None,
    max_tweets: Optional[int] = None,
    reparse: bool = False,
    progress: ProgressCb = None,
    control: Optional[RunControl] = None,
) -> Dict[str, Any]:
    cfg = get_config()
    lid = parse_list_id(list_id or str(cfg.get("list_id") or "")) or str(cfg.get("list_id") or "")
    if not lid:
        return {"success": False, "error": "请配置 X List ID 或列表链接"}

    hours = int(
        cutoff_hours
        if cutoff_hours is not None
        else cfg.get("value_cutoff_hours") or cfg.get("cutoff_hours") or 24
    )
    hours = max(1, min(hours, 24 * 14))
    limit = int(
        max_tweets
        if max_tweets is not None
        else cfg.get("value_max_tweets") or cfg.get("max_tweets") or 40
    )
    limit = max(1, min(limit, 120))

    save_config(
        {
            "list_id": lid,
            "value_cutoff_hours": hours,
            "value_max_tweets": limit,
        }
    )

    if control and control.is_stopped():
        return {"success": False, "error": "已终止", "aborted": True}

    now = datetime.now(timezone.utc).astimezone()
    floor = now - timedelta(hours=hours)
    _log(progress, "=" * 56)
    _log(progress, "价值回归：开始一轮")
    _log(progress, f"列表 {lid} · 截至 {hours}h · 最多 {limit} 条")

    if _wait_if_paused(control, progress) == "stop":
        return {"success": False, "error": "已终止", "aborted": True}

    crawled = fetch_list_tweets(
        lid,
        since=floor,
        max_tweets=limit,
        progress=progress,
        should_abort=(lambda: bool(control and control.is_stopped())) if control else None,
    )
    if not crawled.get("success"):
        return crawled

    raw_items: List[Dict[str, Any]] = list(crawled.get("items") or [])
    cards: List[Dict[str, Any]] = []
    skipped_pre = 0
    skipped_dup = 0
    evaluated = 0
    recommended_n = 0
    aborted = False
    item_logs: List[Dict[str, Any]] = []

    notifier = get_notifier()

    for i, it in enumerate(raw_items, 1):
        if _wait_if_paused(control, progress) == "stop":
            aborted = True
            _log(progress, f"用户终止于 {i - 1}/{len(raw_items)}")
            break

        tid = str(it.get("tweet_id") or "")
        created = parse_dt(str(it.get("created_at") or ""))
        if created and _aware(created) < _aware(floor):
            continue

        keep, why = prefilter_tweet(it)
        if not keep:
            skipped_pre += 1
            _log(progress, f"[预过滤] {why} · {fmt_tweet_line(it)}")
            item_logs.append({"tweet_id": tid, "skipped": True, "reason": why})
            continue

        cached = already_evaluated(it, reparse=reparse)
        if cached:
            skipped_dup += 1
            _log(progress, f"[去重] 已评估 · {fmt_tweet_line(it)}")
            cards.append(cached)
            continue

        text = str(it.get("text") or "").strip()
        author = str(it.get("author") or "")
        _log(progress, f"---------- 评估 [{i}/{len(raw_items)}] ----------")
        _log(progress, f"{author} · {clip_text(text, 120)}")

        ev = evaluate_tweet(it)
        thr_info = resolve_threshold_for_eval(ev)
        threshold = float(thr_info["threshold"])
        score = float(ev.get("score") or 0)
        # 动态门槛下：分 >= 门槛 或 模型 is_recommended
        is_rec = bool(ev.get("is_recommended")) or score >= threshold
        ev["is_recommended"] = is_rec
        ev["threshold"] = threshold
        ev["value_kind"] = thr_info.get("kind")

        evaluated += 1
        if is_rec:
            recommended_n += 1

        _log(
            progress,
            f"得分 {score:.2f} · 门槛 {threshold:.2f} ({thr_info.get('kind')}) · "
            f"{'推荐' if is_rec else '未达'} · {ev.get('provider')}",
        )

        card: Dict[str, Any] = {
            "id": f"value-{tid or uuid4().hex[:10]}",
            "tweet_id": tid,
            "list_id": lid,
            "author": author,
            "url": str(it.get("url") or ""),
            "text": text,
            "created_at": str(it.get("created_at") or ""),
            "time_label": str(it.get("time_label") or ""),
            "display_time": str(it.get("created_at") or it.get("time_label") or ""),
            "parsed_at": now.isoformat(timespec="seconds"),
            "images": list(it.get("images") or []) if isinstance(it.get("images"), list) else [],
            "signal": {
                "has_trade_signal": False,
                "summary": ev.get("incremental_value") or ev.get("reason") or "",
                "confidence": score / 10.0,
                "provider": ev.get("provider") or "",
            },
            "source_mode": "value_return",
            "source_modes": ["value_return"],
            "value_eval": ev,
            "value_score": score,
            "value_recommended": 1 if is_rec else 0,
            "category": ev.get("category"),
            "key_takeaways": ev.get("key_takeaways") or [],
        }
        card = apply_store_policy(
            card, score=score, threshold=threshold, recommended=is_rec
        )
        saved = upsert_card(card)
        cards.append(saved)

        if is_rec:
            try:
                notifier.notify(saved)
            except Exception:
                pass

        item_logs.append(
            {
                "tweet_id": tid,
                "author": author,
                "score": score,
                "threshold": threshold,
                "is_recommended": is_rec,
                "category": ev.get("category"),
            }
        )

    msg = (
        f"价值回归完成：评估 {evaluated} · 推荐 {recommended_n} · "
        f"预过滤 {skipped_pre} · 去重 {skipped_dup}"
    )
    if aborted:
        msg += "（已终止）"
    _log(progress, msg)

    return {
        "success": not aborted or evaluated > 0 or recommended_n > 0,
        "aborted": aborted,
        "message": msg,
        "list_id": lid,
        "evaluated": evaluated,
        "recommended": recommended_n,
        "skipped_prefilter": skipped_pre,
        "skipped_dup": skipped_dup,
        "cards": cards,
        "card_count": len(cards),
        "item_logs": item_logs[-80:],
    }
