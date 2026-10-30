# coding=utf-8
from __future__ import annotations

from typing import Any, Dict, List

from signals.binance_square.store import load_state, save_state


def reset_binance_square_realtime() -> Dict[str, Any]:
    """清空 Square 实时/增量缓存（卡片 + state 帖文 + contentId 登记），便于按 8h 窗重抓。"""
    out = clear_binance_square_cache(None)
    from signals.binance_square.store import load_config, save_config

    cfg = load_config()
    save_config({**cfg, "last_crawl_at": ""})
    out["message"] = (
        f"Square 实时数据已重置 · 删除卡片 {out.get('removed_cards', 0)} 条 · "
        "请执行「立即抓取（增量）」按近 8 小时重抓"
    )
    out["reset_realtime"] = True
    return out


def clear_binance_square_cache(profile_ids: List[str] | None = None) -> Dict[str, Any]:
    from signals.card_db import db_delete_binance_square_cards, ensure_migrated

    ensure_migrated([])
    ids = [str(x).strip().lower() for x in (profile_ids or []) if str(x).strip()]
    removed: List[str] = []
    if ids:
        for pid in ids:
            removed.extend(db_delete_binance_square_cards(pid))
    else:
        removed = db_delete_binance_square_cards("")
    st = load_state()
    st["last_posts"] = []
    st["last_posts_raw"] = []
    st["seen_hrefs"] = []
    st["seen_content_ids"] = []
    st["seen_content_registry"] = {}
    st["last_run_at"] = ""
    save_state(st)
    uniq = sorted(set(removed))
    return {
        "success": True,
        "removed_cards": len(uniq),
        "tweet_ids": uniq,
        "profiles": ids,
        "message": f"已清除 Square 缓存 · 删除卡片 {len(uniq)} 条",
    }
