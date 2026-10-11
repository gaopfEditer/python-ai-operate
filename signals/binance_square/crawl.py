# coding=utf-8
from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional

from signals.binance_square.bapi import fetch_trending
from signals.binance_square.profile_js import PROFILE_POST_EXTRACT_JS
from signals.binance_square.enrich import enrich_posts_with_signals
from signals.binance_square.store import (
    apply_binance_time_filter,
    load_config,
    load_state,
    merge_square_posts,
    resolve_binance_time_filter,
    save_state,
)
from signals.backfill_range import BACKFILL_RANGE_LABELS

ProgressCb = Optional[Callable[[str], None]]


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)


def _slug_from_profile(url: str) -> str:
    m = re.search(r"/square/profile/([^/?#]+)", url or "", re.I)
    return (m.group(1) if m else "").strip()


def _scroll_profile_and_extract(
    driver,
    *,
    max_items: int,
    author_slug: str,
    max_rounds: int = 35,
    min_rounds: int = 12,
    progress: ProgressCb = None,
) -> List[Dict[str, Any]]:
    """
    虚拟列表会在滚走后卸载 DOM；边滚边抽、按 contentId 合并，避免「中间漏帖」。
    """
    merged: List[Dict[str, Any]] = []
    last_unique = -1
    stable = 0
    for rnd in range(max_rounds):
        for _ in range(5):
            driver.execute_script(
                "window.scrollBy(0, Math.max(320, Math.floor(window.innerHeight * 0.82)));"
            )
            time.sleep(0.55)
        try:
            js_cap = max(max_items * 3, 120)
            chunk = driver.execute_script(PROFILE_POST_EXTRACT_JS, js_cap, author_slug) or []
        except Exception:
            chunk = []
        if chunk:
            merged = merge_square_posts([*merged, *(c for c in chunk if isinstance(c, dict))])
        n = len(merged)
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
) -> Dict[str, Any]:
    cfg = load_config()
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
        try:
            for i, prof in enumerate(profiles, 1):
                url = str(prof.get("url") or "").strip()
                slug = _slug_from_profile(url) or str(prof.get("id") or "")
                name = str(prof.get("name") or slug)
                if not url:
                    continue
                _log(progress, f"[{i}/{len(profiles)}] 打开 {name} …")
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

    if profiles and merged:
        from signals.binance_square.media import enrich_posts_media_from_detail
        from public.platforms.cdp_common import connect_cdp

        try:
            driver = connect_cdp(dbg)
            _log(progress, "详情页补抓无媒体帖子（仅保留范围内）…")
            merged = enrich_posts_media_from_detail(
                driver, merged, limit=min(10, max(4, max_n // 4)), progress=progress
            )
        except Exception as e:
            _log(progress, f"详情补媒体跳过: {e}")

    st = load_state()
    prior = st.get("last_posts") if isinstance(st.get("last_posts"), list) else []
    _log(progress, f"AI/规则解析 {len(merged)} 条贴文信号…")
    merged = enrich_posts_with_signals(merged, prior_posts=prior, progress=progress)

    seen = set(str(x) for x in (st.get("seen_hrefs") or []))
    new_hrefs: List[str] = []
    for p in merged:
        h = str(p.get("href") or "")
        if h and h not in seen:
            new_hrefs.append(h)
            seen.add(h)
    st["seen_hrefs"] = list(seen)[-5000:]
    st["last_posts_raw"] = merge_square_posts(all_posts)[:300]
    st["last_posts"] = merged[:200]
    st["last_run_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_state(st)

    return {
        "success": True,
        "posts": merged,
        "new_count": len(new_hrefs),
        "total": len(merged),
        "routes": routes,
        "profiles": [p.get("id") for p in profiles],
        "backfill_range": time_spec.get("backfill_range") if time_spec.get("mode") == "range" else "",
        "cutoff_hours": time_spec.get("cutoff_hours") if time_spec.get("mode") == "hours" else None,
    }
