# coding=utf-8
"""后台队列：原文/card 先入库，LLM 信号解析异步执行，不阻塞 Square/X 抓取。"""
from __future__ import annotations

import os
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional

ProgressCb = Optional[Callable[[str], None]]

_PENDING = {"provider": "queued", "has_trade_signal": False, "summary": ""}

_LOCK = threading.RLock()
_QUEUE: queue.Queue = queue.Queue()
_WORKER: Optional[threading.Thread] = None
_STATUS: Dict[str, Any] = {
    "alive": False,
    "queued": 0,
    "inflight": 0,
    "done": 0,
    "failed": 0,
    "last_error": "",
    "last_finished_at": "",
}


def pending_signal() -> Dict[str, Any]:
    return dict(_PENDING)


def llm_parse_is_deferred() -> bool:
    """默认异步；SIGNALS_BLOCKING_LLM=1 恢复抓取循环内同步 LLM。"""
    return str(os.environ.get("SIGNALS_BLOCKING_LLM") or "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    )


def signal_parse_pending(sig: Any) -> bool:
    if not isinstance(sig, dict):
        return True
    prov = str(sig.get("provider") or "").strip().lower()
    return prov in ("", "queued", "pending")


def status() -> Dict[str, Any]:
    with _LOCK:
        snap = dict(_STATUS)
        snap["queue_size"] = _QUEUE.qsize()
        snap["alive"] = bool(_WORKER and _WORKER.is_alive())
    return snap


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)


def _ensure_worker() -> None:
    global _WORKER
    with _LOCK:
        if _WORKER and _WORKER.is_alive():
            return

        def _loop() -> None:
            with _LOCK:
                _STATUS["alive"] = True
            while True:
                kind, payload = _QUEUE.get()
                with _LOCK:
                    _STATUS["inflight"] = 1
                try:
                    if kind == "binance_square":
                        _process_binance_square(payload)
                    elif kind == "list_card":
                        _process_list_card(payload)
                except Exception as e:
                    with _LOCK:
                        _STATUS["failed"] = int(_STATUS.get("failed") or 0) + 1
                        _STATUS["last_error"] = str(e)[:240]
                finally:
                    with _LOCK:
                        _STATUS["inflight"] = 0
                        _STATUS["done"] = int(_STATUS.get("done") or 0) + 1
                        _STATUS["last_finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                    _QUEUE.task_done()

        _WORKER = threading.Thread(target=_loop, name="signals-parse-queue", daemon=True)
        _WORKER.start()


def enqueue_binance_square_posts(
    posts: List[Dict[str, Any]],
    *,
    progress: ProgressCb = None,
) -> int:
    rows = [p for p in (posts or []) if isinstance(p, dict)]
    if not rows:
        return 0
    _ensure_worker()
    n = 0
    for p in rows:
        cid = str(p.get("content_id") or p.get("live_content_id") or "").strip()
        href = str(p.get("href") or "").strip()
        if not cid and not href:
            continue
        _QUEUE.put(("binance_square", dict(p)))
        n += 1
    with _LOCK:
        _STATUS["queued"] = int(_STATUS.get("queued") or 0) + n
    if n:
        _log(progress, f"信号解析排队 {n} 条（后台 worker，抓取已继续）")
    return n


def enqueue_list_cards(
    tweet_ids: List[str],
    *,
    progress: ProgressCb = None,
) -> int:
    ids = [str(t).strip() for t in tweet_ids if str(t).strip()]
    if not ids:
        return 0
    _ensure_worker()
    for tid in ids:
        _QUEUE.put(("list_card", {"tweet_id": tid}))
    with _LOCK:
        _STATUS["queued"] = int(_STATUS.get("queued") or 0) + len(ids)
    _log(progress, f"信号解析排队 {len(ids)} 条（后台 worker）")
    return len(ids)



def _maybe_push_parsed_card(card: Dict[str, Any]) -> None:
    """解析完成后按配置增量推送 Cards API（异步路径补洞）。"""
    if not isinstance(card, dict):
        return
    try:
        from signals.push import push_card_if_needed
        from signals.store import get_config

        cfg = get_config() or {}
        sm = str(card.get("source_mode") or "").lower()
        modes = [str(m).lower() for m in (card.get("source_modes") or []) if str(m).strip()]
        list_id = str(card.get("list_id") or "").lower()
        is_binance = ("binance" in sm) or any("binance" in m for m in modes) or list_id.startswith("binance")
        is_kol = ("kol_realtime" in sm) or any("kol_realtime" in m for m in modes)
        if is_binance:
            allow = True
        elif is_kol:
            allow = bool(cfg.get("kol_realtime_push_enabled"))
        else:
            allow = bool(cfg.get("push_enabled") or cfg.get("user_push_enabled"))
        if not allow:
            return
        push_card_if_needed(card)
    except Exception:
        pass


def _process_binance_square(post: Dict[str, Any]) -> None:
    from signals.analyze import analyze_tweet_signal
    from signals.binance_square.cards_sync import square_post_to_card
    from signals.binance_square.store import (
        load_state,
        merge_square_posts,
        post_content_id,
        save_state,
    )
    from signals.store import upsert_card

    text = str(post.get("raw") or post.get("title") or "").strip()
    author = str(post.get("profile_name") or post.get("profile_id") or "").strip()
    urls = [str(u) for u in (post.get("image_urls") or []) if str(u).strip()][:6]
    signal = analyze_tweet_signal(
        text=text or "（无正文）",
        author=author,
        image_urls=urls,
    )
    enriched = dict(post)
    enriched["signal"] = signal

    cid = post_content_id(enriched)
    st = load_state()
    prior = st.get("last_posts") if isinstance(st.get("last_posts"), list) else []
    merged: List[Dict[str, Any]] = []
    replaced = False
    for row in prior:
        if not isinstance(row, dict):
            continue
        if cid and post_content_id(row) == cid:
            merged.append(enriched)
            replaced = True
        else:
            merged.append(row)
    if not replaced:
        merged = merge_square_posts([enriched, *prior])[:200]
    st["last_posts"] = merged[:200]
    save_state(st)

    card = square_post_to_card(enriched)
    upsert_card(card)
    _maybe_push_parsed_card(card)


def _process_list_card(payload: Dict[str, Any]) -> None:
    from signals.analyze import analyze_tweet_signal
    from signals.store import get_card_by_tweet_id, upsert_card

    tid = str(payload.get("tweet_id") or "").strip()
    if not tid:
        return
    card = get_card_by_tweet_id(tid)
    if not card:
        return
    sig = card.get("signal")
    if isinstance(sig, dict) and sig and not signal_parse_pending(sig):
        return

    text = str(card.get("text") or "").strip()
    author = str(card.get("author") or "")
    alts: List[str] = []
    urls: List[str] = []
    for im in card.get("images") or []:
        if not isinstance(im, dict):
            continue
        alt = str(im.get("alt") or "").strip()
        url = str(im.get("url") or im.get("local_path") or "").strip()
        if alt:
            alts.append(alt)
        if url:
            urls.append(url)

    signal = analyze_tweet_signal(
        text=text or "（无文字，见配图）",
        author=author,
        image_alts=alts,
        image_urls=urls,
    )
    updated = dict(card)
    updated["signal"] = signal
    updated["parsed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    updated.pop("cache_only", None)
    upsert_card(updated)
    _maybe_push_parsed_card(updated)
