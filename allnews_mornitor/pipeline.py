# coding=utf-8
"""抓取调度：整段共用一次静默 CDP session，避免每平台切标签抢焦点。"""

from __future__ import annotations

import traceback
from typing import Any, Dict, List, Optional

from allnews_mornitor import archive, cdp_browser, store
from allnews_mornitor.models import Post
from allnews_mornitor.platforms import loader  # noqa: F401 — 注册平台
from allnews_mornitor.platforms import all_enabled_ids, get_platform


def run_crawl(platform_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    ids = platform_ids or all_enabled_ids()
    all_posts: List[Post] = []
    errors: Dict[str, str] = {}
    fetched: Dict[str, int] = {}

    # 一次后台 CDP session：不激活标签、不还焦
    try:
        with cdp_browser.cdp_session() as driver:
            for pid in ids:
                try:
                    plat = get_platform(pid)
                    if not plat.enabled():
                        continue
                    print(f"[allnews] 抓取 {pid} …")
                    try:
                        posts = plat.fetch(driver=driver) or []
                    except TypeError:
                        posts = plat.fetch() or []
                    fetched[pid] = len(posts)
                    print(f"[allnews] {pid}: {len(posts)} 条")
                    all_posts.extend(posts)
                    store.touch_schedule(pid)
                except Exception as e:
                    errors[pid] = str(e)
                    print(f"[allnews] {pid} 失败: {e}")
                    traceback.print_exc()
    except Exception as e:
        errors["_session"] = str(e)
        print(f"[allnews] CDP session 失败: {e}")
        traceback.print_exc()

    result = archive.auto_archive_batch(all_posts)
    result["fetched"] = fetched
    result["errors"] = errors
    if "total_fetched" not in result:
        result["total_fetched"] = len(all_posts)
    return result
