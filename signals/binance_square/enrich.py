# coding=utf-8
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from signals.analyze import (
    analyze_tweet_signal,
    default_analyze_concurrency,
    default_analyze_timeout_seconds,
)
from signals.binance_square.store import post_content_id

if TYPE_CHECKING:
    from signals.control import RunControl

ProgressCb = Optional[Callable[[str], None]]

_AnalyzeJob = Tuple[int, Dict[str, Any], str, str, str, List[str]]


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
        if not (href and isinstance(sig, dict) and sig):
            continue
        entry = {"signal": dict(sig), "text": _post_text(p)}
        out[href] = entry
        cid = post_content_id(p)
        if cid:
            out[f"id:{cid}"] = entry
    return out


def _wait_control(control: Optional["RunControl"], progress: ProgressCb) -> str:
    if control is None:
        return "ok"
    if control.is_paused():
        _log(progress, "信号解析已暂停，等待继续…")
    return control.check()


def _run_analyze_job(
    job: _AnalyzeJob,
    *,
    timeout: float,
    use_ai: bool,
) -> Tuple[int, Dict[str, Any], float, str]:
    i, p, label, text, author, urls = job
    t0 = time.monotonic()
    if use_ai:
        p = dict(p)
        p["signal"] = analyze_tweet_signal(
            text=text or "（无正文）",
            author=author,
            image_urls=urls,
            timeout_sec=timeout,
            use_ai=True,
        )
    else:
        from signals.analyze import _heuristic

        p = dict(p)
        p["signal"] = _heuristic(text or "（无正文）")
    elapsed = time.monotonic() - t0
    prov = str((p.get("signal") or {}).get("provider") or "")
    return i, p, elapsed, prov


def _log_analyze_done(
    progress: ProgressCb,
    *,
    i: int,
    total: int,
    label: str,
    elapsed: float,
    prov: str,
    batch_elapsed: float,
    done: int,
) -> None:
    avg = batch_elapsed / max(done, 1)
    eta_s = avg * max(0, total - done)
    if prov.startswith("timeout:"):
        _log(
            progress,
            f"  [{i}/{total}] {label} · AI 超时 → 规则兜底 · {elapsed:.1f}s "
            f"(批次 {done}/{total}，均 {avg:.1f}s，约剩 {eta_s:.0f}s)",
        )
    elif prov.startswith("heuristic:skip_llm"):
        _log(
            progress,
            f"  [{i}/{total}] {label} · 跳过 LLM（规则）· {elapsed:.2f}s",
        )
    elif prov == "heuristic" or "cache" in prov:
        _log(progress, f"  [{i}/{total}] {label} · {prov} · {elapsed:.2f}s")
    else:
        _log(
            progress,
            f"  [{i}/{total}] {label} · {prov or 'ok'} · {elapsed:.1f}s "
            f"(均 {avg:.1f}s，约剩 {eta_s:.0f}s)",
        )


def enrich_posts_with_signals(
    posts: List[Dict[str, Any]],
    *,
    prior_posts: Optional[List[Dict[str, Any]]] = None,
    progress: ProgressCb = None,
    use_ai: bool = True,
    control: Optional["RunControl"] = None,
    analyze_timeout_sec: Optional[float] = None,
    concurrency: Optional[int] = None,
) -> List[Dict[str, Any]]:
    cache = _signal_cache_from_posts(prior_posts or [])
    total = len(posts or [])
    timeout = (
        default_analyze_timeout_seconds()
        if analyze_timeout_sec is None
        else float(analyze_timeout_sec)
    )
    workers = default_analyze_concurrency() if concurrency is None else max(1, min(4, int(concurrency)))
    if not use_ai:
        workers = 1

    ordered: List[Optional[Dict[str, Any]]] = [None] * total
    jobs: List[_AnalyzeJob] = []
    ai_timeouts = 0
    batch_t0 = time.monotonic()

    for i, raw in enumerate(posts or [], 1):
        if not isinstance(raw, dict):
            continue
        p = dict(raw)
        href = str(p.get("href") or "").strip()
        text = _post_text(p)
        author = str(p.get("profile_name") or p.get("profile_id") or p.get("author_slug") or "")
        label = author or (href[:48] if href else f"#{i}")
        cid = post_content_id(p)
        cached = (cache.get(f"id:{cid}") if cid else None) or (cache.get(href) if href else None)
        if cached and cached.get("text") == text and isinstance(cached.get("signal"), dict):
            p["signal"] = dict(cached["signal"])
            ordered[i - 1] = p
            _log(progress, f"解析信号 [{i}/{total}] {label} · 缓存 · 0.00s")
            continue

        urls = [str(u) for u in (p.get("image_urls") or []) if str(u).strip()][:6]
        jobs.append((i, p, label, text, author, urls))
        _log(
            progress,
            f"解析信号 [{i}/{total}] {label}…（队列，AI≤{int(timeout)}s×{workers}并发）",
        )

    if not jobs:
        return [x for x in ordered if x is not None]

    job_labels = {j[0]: j[2] for j in jobs}

    def _on_result_fixed(i: int, p: Dict[str, Any], elapsed: float, prov: str) -> None:
        nonlocal ai_timeouts
        ordered[i - 1] = p
        if prov.startswith("timeout:"):
            ai_timeouts += 1
        cached_done = sum(1 for x in ordered if x is not None)
        _log_analyze_done(
            progress,
            i=i,
            total=total,
            label=job_labels.get(i, f"#{i}"),
            elapsed=elapsed,
            prov=prov,
            batch_elapsed=time.monotonic() - batch_t0,
            done=cached_done,
        )

    if workers <= 1:
        for job in jobs:
            if _wait_control(control, progress) == "stop":
                _log(progress, f"用户终止信号解析（已完成 {sum(1 for x in ordered if x)}/{total}）")
                break
            i, p, elapsed, prov = _run_analyze_job(job, timeout=timeout, use_ai=use_ai)
            _on_result_fixed(i, p, elapsed, prov)
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="bs-signal") as pool:
            fut_map = {
                pool.submit(_run_analyze_job, job, timeout=timeout, use_ai=use_ai): job
                for job in jobs
            }
            for fut in as_completed(fut_map):
                if _wait_control(control, progress) == "stop":
                    for f in fut_map:
                        f.cancel()
                    _log(
                        progress,
                        f"用户终止信号解析（已完成 {sum(1 for x in ordered if x)}/{total}）",
                    )
                    break
                job = fut_map[fut]
                try:
                    i, p, elapsed, prov = fut.result()
                    _on_result_fixed(i, p, elapsed, prov)
                except Exception as e:
                    i = job[0]
                    from signals.analyze import _heuristic

                    p = dict(job[1])
                    p["signal"] = _heuristic(_post_text(p) or "（无正文）")
                    p["signal"]["provider"] = f"error:{type(e).__name__}"
                    _on_result_fixed(i, p, 0.0, p["signal"]["provider"])

    out = [x for x in ordered if x is not None]
    batch_sec = time.monotonic() - batch_t0
    _log(
        progress,
        f"信号解析完成 · {len(out)}/{total} 条 · 批次 {batch_sec:.1f}s"
        + (f" · {ai_timeouts} 次 AI 超时" if ai_timeouts else ""),
    )
    if ai_timeouts:
        _log(progress, f"提示：可调低 SIGNALS_ANALYZE_TIMEOUT 或 SIGNALS_ANALYZE_CONCURRENCY=1")
    return out


def fill_missing_signals_heuristic(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """列表 API 用：仅对缺 signal 的条目做规则解析，避免阻塞 UI。"""
    from signals.analyze import _heuristic

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
