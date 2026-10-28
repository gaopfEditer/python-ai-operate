# coding=utf-8
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from signals.control import RunControl

from signals.binance_square.bapi import fetch_trending
from signals.binance_square.profile_js import PROFILE_POST_EXTRACT_JS
from signals.binance_square.enrich import enrich_posts_with_signals
from signals.binance_square.store import (
    apply_binance_time_filter,
    apply_canonical_square_post,
    backfill_soft_cutoff_from_time_spec,
    known_square_content_ids,
    load_config,
    load_state,
    merge_square_posts,
    parse_post_time,
    partition_square_posts_by_known,
    post_content_id,
    register_square_content_ids,
    resolve_binance_time_filter,
    save_state,
    square_posts_index_by_content_id,
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


def _wait_profile_feed(driver, *, timeout_sec: float = 14.0) -> int:
    """等待主页帖文链接出现在 DOM，返回当前锚点数量。"""
    deadline = time.time() + max(3.0, timeout_sec)
    last = 0
    while time.time() < deadline:
        try:
            last = int(
                driver.execute_script(
                    'return document.querySelectorAll(\'a[href*="/square/post/"],'
                    'a[href*="/square/video/"],a[href*="/square/article/"]\').length;'
                )
                or 0
            )
            if last > 0:
                return last
        except Exception:
            pass
        time.sleep(0.85)
    return last


def _profile_feed_diag(driver) -> str:
    try:
        pack = driver.execute_script(
            """
const href = String(location.href || '');
const title = String(document.title || '');
const body = (document.body && document.body.innerText || '').slice(0, 600);
const nPost = document.querySelectorAll('a[href*="/square/post/"]').length;
const nAny = document.querySelectorAll('a[href*="/square/"]').length;
let block = '';
const blob = (title + ' ' + body).toLowerCase();
if (/human verification/i.test(title) || /人机|验证身份|captcha|recaptcha|verify you are/i.test(blob)) {
  block = 'human_verification';
} else if (/sign in|log in|登录/.test(blob) && nPost === 0) {
  block = 'login';
}
return { href, title, nPost, nAny, block };
"""
        ) or {}
        href = str(pack.get("href") or "")
        title = str(pack.get("title") or "")[:60]
        n_post = int(pack.get("nPost") or 0)
        n_any = int(pack.get("nAny") or 0)
        block = str(pack.get("block") or "").strip()
        extra = f" · 拦截={block}" if block else ""
        return f"title={title} · url={href[:100]} · post链接={n_post} · square链接={n_any}{extra}"
    except Exception as e:
        return f"诊断失败: {e}"


def _binance_block_reason(driver) -> str:
    diag = _profile_feed_diag(driver)
    if "拦截=human_verification" in diag:
        return "币安人机验证（Human Verification）— 请在 9223 调试 Chrome 里打开该博主主页并手动过验证"
    if "拦截=login" in diag:
        return "币安要求登录 — 请在调试 Chrome 登录后再抓取"
    return ""


def _scroll_profile_and_extract(
    driver,
    *,
    max_items: int,
    author_slug: str,
    max_rounds: int = 35,
    min_rounds: int = 12,
    shallow: bool = False,
    scroll_stop_before: Optional[datetime] = None,
    progress: ProgressCb = None,
    should_abort: Optional[Callable[[], bool]] = None,
) -> List[Dict[str, Any]]:
    """
    虚拟列表会在滚走后卸载 DOM；边滚边抽、按 contentId 合并，避免「中间漏帖」。
    每次抓取先刷新并回到顶部，再从最新帖向下滚（不接上次 CDP 页签的滚动位置）。
    """
    merged: List[Dict[str, Any]] = []
    last_unique = -1
    stable = 0
    scroll_steps = 2 if shallow else 5
    scroll_pause = 0.35 if shallow else 0.55
    past_window_streak = 0
    try:
        driver.refresh()
        time.sleep(0.9)
        _wait_profile_feed(driver, timeout_sec=16.0)
    except Exception:
        pass
    try:
        driver.execute_script(
            """
(() => {
  const reset = (el) => {
    try {
      if (el && el.scrollHeight > el.clientHeight + 40) el.scrollTop = 0;
    } catch (e) {}
  };
  reset(document.scrollingElement);
  reset(document.documentElement);
  reset(document.body);
  document.querySelectorAll('main, [role="main"], [class*="overflow-y-auto"], [class*="overflow-auto"]')
    .forEach(reset);
  window.scrollTo(0, 0);
  return true;
})()
"""
        )
        time.sleep(0.65)
        tag = "浅滚" if shallow else "深滚"
        extra = "（超出回溯窗即停）" if scroll_stop_before else ""
        _log(progress, f"  已刷新并回到列表顶部，{tag}从最新帖重新向下{extra}")
    except Exception:
        pass
    for rnd in range(max_rounds):
        if should_abort and should_abort():
            break
        if rnd > 0:
            for _ in range(scroll_steps):
                if should_abort and should_abort():
                    break
                driver.execute_script(
                    "window.scrollBy(0, Math.max(320, Math.floor(window.innerHeight * 0.82)));"
                )
                time.sleep(scroll_pause)
        try:
            js_cap = max(max_items * 3, 120)
            chunk = driver.execute_script(PROFILE_POST_EXTRACT_JS, js_cap, author_slug) or []
        except Exception as e:
            if progress:
                _log(progress, f"  抽取脚本异常: {e}")
            chunk = []
        round_posts = [c for c in (chunk or []) if isinstance(c, dict)]
        if round_posts:
            merged = merge_square_posts([*merged, *round_posts])
        n = len(merged)
        if scroll_stop_before and round_posts and rnd + 1 >= min_rounds:
            parsed = [parse_post_time(p) for p in round_posts]
            times = [t for t in parsed if t is not None]
            if times:
                if max(times) < scroll_stop_before:
                    _log(
                        progress,
                        "  当前屏帖文均早于回溯窗，停止深滚（不再继续往下翻）",
                    )
                    break
                in_window = sum(1 for t in times if t >= scroll_stop_before)
                if in_window == 0:
                    past_window_streak += 1
                else:
                    past_window_streak = 0
                if past_window_streak >= 2:
                    _log(
                        progress,
                        "  已连续多屏无窗内帖，停止深滚",
                    )
                    break
        if shallow and n >= max_items:
            break
        if rnd + 1 < min_rounds:
            last_unique = n
            continue
        if n == last_unique:
            stable += 1
            empty_done = n == 0 and rnd + 1 >= min_rounds
            if stable >= (2 if shallow else 4) and (n > 0 or empty_done):
                break
        else:
            stable = 0
        last_unique = n
        if progress and (rnd + 1) % (2 if shallow else 3) == 0:
            tag = "浅滚" if shallow else "深滚"
            _log(progress, f"  {tag} {rnd + 1}/{max_rounds} · 累计 {n} 条（去重）")
    return merged[: max(max_items, 1)]


def _scroll_params_for_time_spec(
    time_spec: Dict[str, Any],
    *,
    incremental: bool = False,
) -> Dict[str, int]:
    """仅历史回溯（range）深滚；按小时窗的实时/周期一律浅滚，靠时间过滤裁旧帖。"""
    from signals.backfill_range import backfill_range_span_days

    if time_spec.get("mode") == "range":
        rk = str(time_spec.get("backfill_range") or "last_7d")
        span = max(1, int(backfill_range_span_days(rk) or 7))
        return {
            "max_rounds": min(20, 6 + span),
            "min_rounds": min(6, 3 + span // 3),
            "shallow": False,
        }
    hours = max(1.0, float(time_spec.get("cutoff_hours") or 8))
    max_r = max(3, min(7, 3 + int(hours // 12)))
    return {"max_rounds": max_r, "min_rounds": 2, "shallow": True}


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
    incremental: Optional[bool] = None,
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
    if profile_ids is not None:
        from signals.binance_square.store import normalize_profile_id_list

        want = set(normalize_profile_id_list(profile_ids))
        if not want:
            return {"success": False, "error": "未选择 Square 博主（请勾选后再抓取）", "posts": []}
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

    if incremental is None:
        incremental = time_spec.get("mode") != "range"
    if time_spec.get("mode") == "range":
        _log(progress, "历史回溯：主页深滚以覆盖回溯范围")
    elif incremental:
        hours = float(time_spec.get("cutoff_hours") or 8)
        _log(progress, f"实时/周期：浅滚首屏附近（近 {hours:g}h 由时间过滤裁切，不深滚）")

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
        from public.platforms.cdp_common import (
            activate_selenium_tab,
            connect_cdp,
            invalidate_cdp_driver,
            navigate_or_activate,
            preserve_os_focus,
            wait_landed,
        )

        if not dbg:
            from signals.store import resolve_signals_debugger_url

            dbg = resolve_signals_debugger_url()
        _log(progress, f"连接 CDP {dbg}…")
        try:
            driver = connect_cdp(dbg)
        except Exception as e:
            invalidate_cdp_driver(dbg)
            return {"success": False, "error": f"CDP 连接失败: {e}", "posts": []}

        scroll_kw = _scroll_params_for_time_spec(time_spec, incremental=bool(incremental))
        scroll_stop = (
            backfill_soft_cutoff_from_time_spec(time_spec)
            if time_spec.get("mode") == "range"
            else None
        )
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
                    with preserve_os_focus():
                        navigate_or_activate(driver, url)
                        activate_selenium_tab(driver)
                    wait_landed(
                        driver,
                        hosts=("binance.com",),
                        paths=("/square/profile/",),
                        timeout=12.0,
                    )
                except Exception as e:
                    _log(progress, f"  打开失败: {e}")
                    continue
                block = _binance_block_reason(driver)
                if block:
                    _log(progress, f"  跳过：{block}")
                    profile_stats.append(
                        {"id": slug, "name": name, "fetched": 0, "url": url, "blocked": block}
                    )
                    continue
                feed_n = _wait_profile_feed(driver, timeout_sec=12.0)
                if feed_n <= 0:
                    _log(progress, f"  帖文未就绪（{_profile_feed_diag(driver)}），滚动抽取时会再刷新…")
                try:
                    chunk = _scroll_profile_and_extract(
                        driver,
                        max_items=max_n,
                        author_slug=slug,
                        progress=progress,
                        should_abort=abort_fn,
                        scroll_stop_before=scroll_stop,
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
                if not chunk:
                    _log(progress, f"  抽到 0 条（去重后） · {_profile_feed_diag(driver)}")
                else:
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

    skip_hours = float(cfg.get("content_skip_hours") or 24)
    if time_spec.get("mode") == "range":
        known_ids = known_square_content_ids()
        skip_label = "已登记 contentId"
    else:
        from signals.binance_square.store import square_content_ids_skip_recent

        known_ids = square_content_ids_skip_recent(skip_hours)
        skip_label = f"近 {skip_hours:g}h 内已抓取"
    try:
        from signals.card_db import db_get_card_by_tweet_id, db_known_binance_content_ids
        from signals.binance_square.cards_sync import signal_card_to_square_post

        known_ids |= db_known_binance_content_ids()
    except Exception:
        db_get_card_by_tweet_id = None  # type: ignore
        signal_card_to_square_post = None  # type: ignore
    st = load_state()
    prior = st.get("last_posts") if isinstance(st.get("last_posts"), list) else []
    prior_by_cid = square_posts_index_by_content_id(prior)
    prior_by_cid.update(square_posts_index_by_content_id(st.get("last_posts_raw") or []))
    if db_get_card_by_tweet_id and signal_card_to_square_post:
        for cid in known_ids:
            if cid in prior_by_cid:
                continue
            ex = db_get_card_by_tweet_id(cid)
            if ex:
                prior_by_cid[cid] = signal_card_to_square_post(ex)
    canon_merged: List[Dict[str, Any]] = []
    for p in merged:
        if not isinstance(p, dict):
            continue
        cid = post_content_id(p)
        if cid and cid in known_ids and cid in prior_by_cid:
            canon_merged.append(apply_canonical_square_post(p, prior=prior_by_cid[cid]))
        else:
            canon_merged.append(dict(p))
    merged = canon_merged
    to_process, skipped_known = partition_square_posts_by_known(merged, known_ids)
    if skipped_known:
        _log(progress, f"跳过 {skipped_known} 条（{skip_label}）")

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

    if to_process:
        _log(progress, f"AI/规则解析 {len(to_process)} 条新贴文信号…")
        enriched = enrich_posts_with_signals(to_process, prior_posts=prior, progress=progress)
    else:
        enriched = []
        if merged and skipped_known:
            _log(progress, "范围内帖子均已抓取过，跳过 AI 解析与入库")

    enriched_map: Dict[str, Dict[str, Any]] = {}
    for p in enriched:
        if not isinstance(p, dict):
            continue
        cid = post_content_id(p)
        if cid:
            enriched_map[cid] = p

    persisted: List[Dict[str, Any]] = []
    for p in merged:
        if not isinstance(p, dict):
            continue
        cid = post_content_id(p)
        if cid and cid in known_ids and cid not in enriched_map:
            if cid in prior_by_cid:
                persisted.append(dict(prior_by_cid[cid]))
            continue
        if cid and cid in enriched_map:
            persisted.append(enriched_map[cid])
        else:
            persisted.append(dict(p))

    register_ids = [post_content_id(p) for p in to_process if post_content_id(p)]
    if register_ids:
        register_square_content_ids(register_ids, posts=to_process)

    st = load_state()
    combined_posts = merge_square_posts([*prior, *persisted])[:200]
    raw_pool = merge_square_posts(all_posts)
    fixed_raw: List[Dict[str, Any]] = []
    for p in raw_pool:
        if not isinstance(p, dict):
            continue
        cid = post_content_id(p)
        if cid and cid in prior_by_cid:
            fixed_raw.append(apply_canonical_square_post(p, prior=prior_by_cid[cid]))
        else:
            fixed_raw.append(p)
    st["last_posts_raw"] = fixed_raw[:300]
    st["last_posts"] = combined_posts
    st["last_run_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_state(st)

    cards_sync: Dict[str, Any] = {}
    if persisted:
        from signals.backfill_range import resolve_backfill_since
        from signals.binance_square.cards_sync import sync_posts_to_signal_cards
        from signals.binance_square.enrich import fill_missing_signals_heuristic

        for_cards = fill_missing_signals_heuristic(
            [p for p in persisted if post_content_id(p) in enriched_map]
        )
        rk = str(time_spec.get("backfill_range") or "last_7d")
        if time_spec.get("mode") == "range":
            since_dt, range_label = resolve_backfill_since(rk)
            cards_sync = sync_posts_to_signal_cards(
                for_cards,
                backfill_range=rk,
                range_label=range_label or BACKFILL_RANGE_LABELS.get(rk, rk),
                since_iso=since_dt.isoformat(timespec="seconds"),
                progress=progress,
            )
        else:
            cards_sync = sync_posts_to_signal_cards(for_cards, progress=progress)
        synced_n = int(cards_sync.get("synced") or 0)
        _log(progress, f"Square 卡片入库 {synced_n} 条（SQLite）")

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
