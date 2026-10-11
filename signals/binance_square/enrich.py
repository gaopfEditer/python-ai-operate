# coding=utf-8
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from signals.analyze import _heuristic, analyze_tweet_signal

ProgressCb = Optional[Callable[[str], None]]


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)


def _post_text(p: Dict[str, Any]) -> str:
    return str(p.get("raw") or p.get("title") or "").strip()


def _signal_cache_from_posts(posts: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for p in posts or []:
        if not isinstance(p, dict):
            continue
        href = str(p.get("href") or "").strip()
        sig = p.get("signal")
        if href and isinstance(sig, dict) and sig:
            out[href] = {"signal": dict(sig), "text": _post_text(p)}
    return out


def enrich_posts_with_signals(
    posts: List[Dict[str, Any]],
    *,
    prior_posts: Optional[List[Dict[str, Any]]] = None,
    progress: ProgressCb = None,
    use_ai: bool = True,
) -> List[Dict[str, Any]]:
    cache = _signal_cache_from_posts(prior_posts or [])
    out: List[Dict[str, Any]] = []
    total = len(posts or [])
    for i, raw in enumerate(posts or [], 1):
        if not isinstance(raw, dict):
            continue
        p = dict(raw)
        href = str(p.get("href") or "").strip()
        text = _post_text(p)
        author = str(p.get("profile_name") or p.get("profile_id") or p.get("author_slug") or "")
        cached = cache.get(href) if href else None
        if cached and cached.get("text") == text and isinstance(cached.get("signal"), dict):
            p["signal"] = dict(cached["signal"])
        else:
            urls = [str(u) for u in (p.get("image_urls") or []) if str(u).strip()][:6]
            if use_ai:
                _log(progress, f"解析信号 [{i}/{total}] {author or href[:48]}…")
                p["signal"] = analyze_tweet_signal(
                    text=text or "（无正文）",
                    author=author,
                    image_urls=urls,
                )
            else:
                p["signal"] = _heuristic(text or "（无正文）")
        out.append(p)
    return out


def fill_missing_signals_heuristic(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """列表 API 用：仅对缺 signal 的条目做规则解析，避免阻塞 UI。"""
    out: List[Dict[str, Any]] = []
    for raw in posts or []:
        if not isinstance(raw, dict):
            continue
        p = dict(raw)
        sig = p.get("signal")
        if not isinstance(sig, dict) or not sig:
            text = _post_text(p)
            p["signal"] = _heuristic(text or "（无正文）")
        out.append(p)
    return out
