# coding=utf-8
"""抓取：复用列表信号 CDP crawl_list_timeline。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, Optional

ProgressCb = Optional[Callable[[str], None]]


def fetch_list_tweets(
    list_id: str,
    *,
    since: datetime,
    max_tweets: int = 40,
    progress: ProgressCb = None,
    should_abort: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    from signals.crawl import crawl_list_timeline

    return crawl_list_timeline(
        list_id,
        since=since,
        max_tweets=max_tweets,
        progress=progress,
        should_abort=should_abort,
    )
