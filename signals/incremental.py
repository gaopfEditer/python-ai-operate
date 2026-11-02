# coding=utf-8
"""实时增量抓取：遇本地已存帖即停止（时间线假定新→旧）。"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set, Tuple

IdFn = Callable[[Dict[str, Any]], str]
KnownFn = Callable[[str], bool]


def filter_newest_until_known(
    items: List[Dict[str, Any]],
    *,
    id_fn: IdFn,
    is_known: KnownFn,
    enabled: bool = True,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    按 API/DOM 顺序（最新在前）只保留已知帖之前的条目。
    返回 (accepted, stop_pagination)。
    enabled=False 时原样返回 (items, False)。
    """
    if not enabled or not items:
        return list(items or []), False
    accepted: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        pid = str(id_fn(it) or "").strip()
        if pid and is_known(pid):
            return accepted, True
        accepted.append(it)
    if items and not accepted:
        return [], True
    return accepted, False


def tweet_id_from_item(item: Dict[str, Any]) -> str:
    return str(item.get("tweet_id") or "").strip()


def square_id_from_post(post: Dict[str, Any]) -> str:
    from signals.binance_square.store import post_content_id

    return post_content_id(post)


def build_x_known_checker(extra: Optional[Set[str]] = None) -> KnownFn:
    from signals.store import is_stored_tweet

    extra = extra or set()

    def _check(tid: str) -> bool:
        t = str(tid or "").strip()
        if not t:
            return False
        if t in extra:
            return True
        return is_stored_tweet(t)

    return _check


def build_square_known_checker(extra: Optional[Set[str]] = None) -> KnownFn:
    from signals.binance_square.store import known_square_content_ids

    known = known_square_content_ids()
    if extra:
        known = set(known) | set(extra)

    def _check(cid: str) -> bool:
        c = str(cid or "").strip()
        return bool(c and c in known)

    return _check
