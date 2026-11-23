# coding=utf-8
"""tweet_id → @handle 缓存（列表/博主 GraphQL 抓取时写入，供历史卡片补全作者）。"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from signals.store import parse_user_handle

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = PROJECT_ROOT / "output" / "signals" / "tweet_author_cache.json"
_LOCK = threading.Lock()
_MAX_ENTRIES = 50_000


def _load() -> Dict[str, str]:
    if not CACHE_PATH.is_file():
        return {}
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {str(k): str(v).strip().lstrip("@").lower() for k, v in raw.items() if k and v}
    except Exception:
        pass
    return {}


def _save(data: Dict[str, str]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if len(data) > _MAX_ENTRIES:
        keys = sorted(data.keys(), reverse=True)[:_MAX_ENTRIES]
        data = {k: data[k] for k in keys}
    CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")


def lookup_tweet_author(tweet_id: str) -> str:
    tid = str(tweet_id or "").strip()
    if not tid:
        return ""
    with _LOCK:
        return _load().get(tid, "")


def record_tweet_authors(items: Iterable[Dict[str, Any]]) -> int:
    """从抓取 items 写入缓存，返回新增/更新条数。"""
    updates: Dict[str, str] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        tid = str(it.get("tweet_id") or "").strip()
        if not tid:
            continue
        h = parse_user_handle(str(it.get("author") or "")) or parse_user_handle(str(it.get("url") or ""))
        if h:
            updates[tid] = h.lower()
    if not updates:
        return 0
    with _LOCK:
        data = _load()
        n = 0
        for tid, h in updates.items():
            if data.get(tid) != h:
                data[tid] = h
                n += 1
        if n:
            _save(data)
    return n


def authors_for_tweet_ids(tweet_ids: List[str]) -> Dict[str, str]:
    ids = [str(x).strip() for x in tweet_ids if str(x).strip()]
    if not ids:
        return {}
    with _LOCK:
        data = _load()
    return {tid: data[tid] for tid in ids if tid in data}