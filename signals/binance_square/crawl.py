# coding=utf-8
from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from signals.control import RunControl

from signals.binance_square.bapi import fetch_trending
from signals.binance_square.profile_js import PROFILE_POST_EXTRACT_JS
from signals.binance_square.enrich import enrich_posts_with_signals
from signals.binance_square.store import (
    apply_binance_time_filter,
    known_square_content_ids,
    load_config,
    load_state,
    merge_square_post_times_from_prior,
    merge_square_posts,
    partition_square_posts_by_known,
    post_content_id,
    register_square_content_ids,
    resolve_binance_time_filter,
    save_state,
)
from signals.backfill_range import BACKFILL_RANGE_LABELS

ProgressCb = Optional[Callable[[str], None]]


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)


def _wait_control(control: Optional["RunControl"], progress: ProgressCb) -> str:
    if control is None:
        return "ok"
    if control.is_paused():
        _log(progress, "已暂停，等待继续…")
    if control.check() == "stop":
        return "stop"
    return "ok"


def _slug_from_profile(url: str) -> str:
    m = re.search(r"/square/profile/([^/?#]+)", url or "", re.I)
    return (m.group(1) if m else "").strip()


def _chunk_has_known_non_pinned(
    chunk: List[Dict[str, Any]], known_ids: set[str]
) -> Optional[str]:
    """按时间流（页面上从上到下）遇到首个已记录且非置顶帖时返回 contentId。"""
    for row in chunk:
        if not isinstance(row, dict):
            continue
        if row.get("is_pinned"):
            continue
        cid = post_content_id(row)
        if cid and cid in known_ids:
            return cid
    return None


def _scroll_profile_and_extract(
    driver,
    *,
    max_items: int,
    author_slug: str,
    max_rounds: int = 35,
    min_rounds: int = 12,
    progress: ProgressCb = None,
    should_abort: Optional[Callable[[], bool]] = None,
    known_content_ids: Optional[set[str]] = None,
    stop_on_known: bool = False,
) -> List[Dict[str, Any]]:
    """
    虚拟列表会在滚走后卸载 DOM；边滚边抽、按 contentId 合并，避免「中间漏帖」。
    实时增量（stop_on_known）时，时间流中出现已记录的非置顶帖即停止下滚。
    """
    merged: List[Dict[str, Any]] = []
    known_ids = known_content_ids or set()
    last_unique = -1
    stable = 0
    for rnd in range(max_rounds):
        if should_abort and should_abort():
            break
        try:
            js_cap = max(max_items * 3, 120)
            chunk = driver.execute_script(PROFILE_POST_EXTRACT_JS, js_cap, author_slug) or []
        except Exception:
            chunk = []
        chunk = [c for c in (chunk or []) if isinstance(c, dict)]
        if chunk:
            merged = merge_square_posts([*merged, *chunk])
        hit_known = ""
        if stop_on_known and known_ids and chunk:
            hit_known = _chunk_has_known_non_pinned(chunk, known_ids) or ""
        n = len(merged)
        if hit_known:
            _log(progress, f"  遇到已记录帖 contentId={hit_known}，停止下滚（非置顶）")
            break
        if rnd + 1 >= max_rounds:
            break
        for _ in range(5):
            if should_abort and should_abort():
                break
            driver.execute_script(
                "window.scrollBy(0, Math.max(320, Math.floor(window.innerHeight * 0.82)));"
            )
            time.sleep(0.55)
        if rnd + 1 < min_rounds:
            last_unique = n
            continue
        if n == last_unique:
            stable += 1
            if stable >= 4 and n > 0:
                break
        else:
            stable = 0
        last_unique = n
        if progress and (rnd + 1) % 3 == 0:
            _log(progress, f"  深滚 {rnd + 1}/{max_rounds} · 累计 {n} 条（去重）")
    return merged[: max(max_items, 1)]


def _scroll_params_for_time_spec(time_spec: Dict[str, Any]) -> Dict[str, int]:
    from signals.backfill_range import backfill_range_span_days

    if time_spec.get("mode") == "range":
        rk = str(time_spec.get("backfill_range") or "last_7d")
        span = max(7, int(backfill_range_span_days(rk) or 7))
        return {
            "max_rounds": min(90, 24 + span * 4),
            "min_rounds": min(28, 12 + span // 2),
        }
    if time_spec.get("mode") == "hours":
        return {"max_rounds": 28, "min_rounds": 1}
    return {"max_rounds": 48, "min_rounds": 16}


def run_binance_square_fetch(
    *,
    profile_ids: Optional[List[str]] = None,
    debugger_url: Optional[str] = None,
    cutoff_hours: Optional[float] = None,
    backfill_range: Optional[str] = None,
    max_posts_per_profile: Optional[int] = None,
    try_bapi: Optional[bool] = None,
    progress: ProgressCb = None,
    control: Optional["RunControl"] = None,
) -> Dict[str, Any]:
    cfg = load_config()
    aborted = False
    profile_stats: List[Dict[str, Any]] = []
    dbg = (debugger_url or cfg.get("debugger_url") or "").strip()
    time_spec = resolve_binance_time_filter(
        backfill_range=backfill_range, cutoff_hours=cutoff_hours, cfg=cfg
    )
    max_n = int(max_posts_per_profile if max_posts_per_profile is not None else cfg.get("max_posts_per_profile") or 40)
    use_bapi = bool(try_bapi if try_bapi is not None else cfg.get("try_bapi_first"))

    profiles = [p for p in (cfg.get("profiles") or []) if isinstance(p, dict) and p.get("enabled", True)]
    if profile_ids:
        want = {str(x).strip().lower() for x in profile_ids if str(x).strip()}
        profiles = [p for p in profiles if str(p.get("id") or "").lower() in want]

    if not profiles and not use_bapi:
        return {"success": False, "error": "未配置启用的 Square 博主", "posts": []}

    if time_spec.get("mode") == "range":
        from signals.backfill_range import resolve_backfill_since

        rk = str(time_spec.get("backfill_range") or "last_7d")
        since_dt, range_label = resolve_backfill_since(rk)
        _log(
            progress,
            f"Square 博主回溯 · {BACKFILL_RANGE_LABELS.get(rk, range_label)}"
            f"（自 {since_dt.isoformat(timespec='seconds')}）",
        )
    if _wait_control(control, progress) == "stop":
        return {"success": False, "error": "已终止", "aborted": True, "posts": []}

    all_posts: List[Dict[str, Any]] = []
    routes: List[str] = []

    if use_bapi:
        _log(progress, "尝试 bapi 热榜…")
        trending = fetch_trending(limit=max_n)
        if trending:
            all_posts.extend(trending)
            routes.append("bapi")
        else:
            _log(progress, "bapi 无数据，改走 CDP 主页…")

    if profiles:
        from public.platforms.cdp_common import connect_cdp, invalidate_cdp_driver

        if not dbg:
            from signals.store import resolve_signals_debugger_url

            dbg = resolve_signals_debugger_url()
        _log(progress, f"连接 CDP {dbg}…")
        try:
            driver = connect_cdp(dbg)
        except Exception as e:
            invalidate_cdp_driver(dbg)
            return {"success": False, "error": f"CDP 连接失败: {e}", "posts": []}

        scroll_kw = _scroll_params_for_time_spec(time_spec)
        realtime_scroll = time_spec.get("mode") == "hours"
        known_for_scroll = known_square_content_ids() if realtime_scroll else set()
        try:
            abort_fn = (lambda: bool(control and control.is_stopped())) if control else None
            for i, prof in enumerate(profiles, 1):
                if _wait_control(control, progress) == "stop":
                    aborted = True
                    _log(progress, f"用户终止于博主 {i - 1}/{len(profiles)}")
                    break
                url = str(prof.get("url") or "").strip()
                slug = _slug_from_profile(url) or str(prof.get("id") or "")
                name = str(prof.get("name") or slug)
                if not url:
                    continue
                _log(progress, f"======== [{i}/{len(profiles)}] @{slug} · {name} ========")
                _log(progress, f"打开主页 …")
                try:
                    driver.get(url)
                except Exception as e:
                    _log(progress, f"  打开失败: {e}")
                    continue
                time.sleep(2.2)
                try:
                    chunk = _scroll_profile_and_extract(
                        driver,
                        max_items=max_n,
                        author_slug=slug,
                        progress=progress,
                        should_abort=abort_fn,
                        known_content_ids=known_for_scroll,
                        stop_on_known=realtime_scroll,
                        **scroll_kw,
                    )
                except Exception as e:
                    _log(progress, f"  解析失败: {e}")
                    chunk = []
                for row in chunk:
                    if isinstance(row, dict):
                        row["profile_id"] = slug
                        row["profile_name"] = name
                        row["source"] = "profile_cdp"
                _log(progress, f"  抽到 {len(chunk)} 条（去重后）")
                profile_stats.append(
                    {"id": slug, "name": name, "fetched": len(chunk), "url": url}
                )
                all_posts.extend(chunk)
            routes.append("profile_cdp")
        finally:
            pass

    merged = merge_square_posts(all_posts)
    scraped_n = len(merged)
    if time_spec.get("mode") == "range":
        rk = str(time_spec.get("backfill_range") or "last_7d")
        label = BACKFILL_RANGE_LABELS.get(rk, rk)
        _log(progress, f"按回溯范围过滤：{label}（抓取 {scraped_n} 条）…")
        merged = apply_binance_time_filter(merged, backfill_range=rk, cfg=cfg)
    else:
        hours = float(time_spec.get("cutoff_hours") or 24)
        _log(progress, f"按近 {hours:g} 小时过滤（抓取 {scraped_n} 条）…")
        merged = apply_binance_time_filter(merged, cutoff_hours=hours, cfg=cfg)
    _log(progress, f"时间过滤后 {len(merged)}/{scraped_n} 条")

    known_ids = known_square_content_ids()
    to_process, skipped_known = partition_square_posts_by_known(merged, known_ids)
    if skipped_known:
        _log(progress, f"跳过已抓取 {skipped_known} 条（contentId 已在缓存/库）")

    if profiles and to_process:
        from signals.binance_square.media import enrich_posts_media_from_detail
        from public.platforms.cdp_common import connect_cdp

        try:
            driver = connect_cdp(dbg)
            _log(progress, "详情页补抓无媒体帖子（仅新帖）…")
            to_process = enrich_posts_media_from_detail(
                driver,
                to_process,
                limit=min(10, max(4, max_n // 4)),
                progress=progress,
            )
        except Exception as e:
            _log(progress, f"详情补媒体跳过: {e}")

    st = load_state()
    prior = st.get("last_posts") if isinstance(st.get("last_posts"), list) else []
    if to_process:
        to_process = merge_square_post_times_from_prior(prior, to_process)
        _log(progress, f"AI/规则解析 {len(to_process)} 条新贴文信号…")
        enriched = enrich_posts_with_signals(to_process, prior_posts=prior, progress=progress)
    else:
        enriched = []
        if merged and skipped_known:
            _log(progress, "范围内帖子均已抓取过，跳过 AI 解析与入库")

    register_square_content_ids(
        [post_content_id(p) for p in merged],
        posts=merged,
    )

    st = load_state()
    combined_posts = merge_square_post_times_from_prior(
        prior, merge_square_posts([*prior, *enriched])
    )[:200]
    st["last_posts_raw"] = merge_square_posts(all_posts)[:300]
    st["last_posts"] = combined_posts
    st["last_run_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_state(st)

    cards_sync: Dict[str, Any] = {}
    # 周期增量（hours）只更新 state，卡片由「产出卡片」+ 币种门槛入库
    if enriched and time_spec.get("mode") != "hours":
        from signals.backfill_range import resolve_backfill_since
        from signals.binance_square.cards_sync import sync_posts_to_signal_cards

        rk = str(time_spec.get("backfill_range") or "last_7d")
        if time_spec.get("mode") == "range":
            since_dt, range_label = resolve_backfill_since(rk)
            cards_sync = sync_posts_to_signal_cards(
                enriched,
                backfill_range=rk,
                range_label=range_label or BACKFILL_RANGE_LABELS.get(rk, rk),
                since_iso=since_dt.isoformat(timespec="seconds"),
                progress=progress,
            )
        else:
            cards_sync = sync_posts_to_signal_cards(enriched, progress=progress)

    ok = not aborted
    return {
        "success": ok or bool(merged),
        "aborted": aborted,
        "posts": combined_posts,
        "cards_sync": cards_sync,
        "new_count": len(enriched),
        "skipped_known": skipped_known,
        "total": len(merged),
        "routes": routes,
        "profiles": [p.get("id") for p in profiles],
        "profile_stats": profile_stats,
        "backfill_range": time_spec.get("backfill_range") if time_spec.get("mode") == "range" else "",
        "cutoff_hours": time_spec.get("cutoff_hours") if time_spec.get("mode") == "hours" else None,
        "message": (
            f"Square 回溯完成 · {len(merged)} 条"
            if not aborted
            else f"已终止 · 已得 {len(merged)} 条"
        ),
    }
