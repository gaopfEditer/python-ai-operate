# coding=utf-8
"""抓取调度：按平台 CDP 拉取 → 热度门槛入候选 → 中位数自动归档。"""

from __future__ import annotations

import traceback
from typing import Any, Dict, List, Optional

from allnews_mornitor import archive, store
from allnews_mornitor.models import Post
from allnews_mornitor.platforms import loader  # noqa: F401 — 注册平台
from allnews_mornitor.platforms import all_enabled_ids, get_platform


def run_crawl(platform_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    ids = platform_ids or all_enabled_ids()
    all_posts: List[Post] = []
    errors: Dict[str, str] = {}
    fetched: Dict[str, int] = {}

    for pid in ids:
        try:
            plat = get_platform(pid)
            if not plat.enabled():
                continue
            print(f"[allnews] 抓取 {pid} …")
            posts = plat.fetch() or []
            fetched[pid] = len(posts)
            print(f"[allnews] {pid}: {len(posts)} 条")
            all_posts.extend(posts)
            store.touch_schedule(pid)
        except Exception as e:
            errors[pid] = str(e)
            print(f"[allnews] {pid} 失败: {e}")
            traceback.print_exc()

    result = archive.auto_archive_batch(all_posts)
    result["fetched"] = fetched
    result["errors"] = errors
    if "total_fetched" not in result:
        result["total_fetched"] = len(all_posts)
    return result
