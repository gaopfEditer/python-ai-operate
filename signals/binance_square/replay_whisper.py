# coding=utf-8
"""币安 Square 直播回放 → WhisprRT 转写队列。"""
from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from signals.binance_square.store import parse_post_time, post_content_id

SetJobFn = Callable[..., None]

DEFAULT_REPLAY_WHISPER_MAX_DAYS = 2


def replay_media_url(post: Dict[str, Any]) -> str:
    return str(post.get("replay_url") or post.get("video_url") or "").strip()


def default_replay_output_basename(post: Dict[str, Any], *, day: Optional[str] = None) -> str:
    """博主 slug + 当天日期，如 yanchibit20261011。"""
    pid = str(post.get("profile_id") or post.get("author_slug") or "square").lower()
    slug = re.sub(r"[^a-z0-9]", "", pid) or "square"
    if not day:
        tz_cn = timezone(timedelta(hours=8))
        day = datetime.now(tz_cn).strftime("%Y%m%d")
    return f"{slug[:48]}{day}"


def _unique_output_name(post: Dict[str, Any], used: set[str]) -> str:
    from console.whisper_service import sanitize_title

    base = default_replay_output_basename(post)
    url = replay_media_url(post)
    name = sanitize_title(base, url)
    cid = post_content_id(post)
    if name in used and cid:
        suffix = re.sub(r"[^a-z0-9]", "", cid.lower())[-10:] or "x"
        name = sanitize_title(f"{base}_{suffix}", url)
    used.add(name)
    return name


def post_within_replay_whisper_window(
    post: Dict[str, Any],
    *,
    max_days: float = DEFAULT_REPLAY_WHISPER_MAX_DAYS,
    now: Optional[datetime] = None,
) -> bool:
    """仅 2 天内（可配置）且能解析发帖时间的回放才自动转写。"""
    days = max(0.0, float(max_days))
    if days <= 0:
        return False
    dt = parse_post_time(post)
    if dt is None:
        return False
    ref = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    cutoff = ref - timedelta(days=days)
    return dt >= cutoff


def posts_with_replay(
    posts: List[Dict[str, Any]],
    *,
    max_age_days: Optional[float] = None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen_url: set[str] = set()
    window = (
        DEFAULT_REPLAY_WHISPER_MAX_DAYS
        if max_age_days is None
        else float(max_age_days)
    )
    for p in posts or []:
        if not isinstance(p, dict):
            continue
        url = replay_media_url(p)
        if not url or url in seen_url:
            continue
        if max_age_days is not None and not post_within_replay_whisper_window(p, max_days=window):
            continue
        seen_url.add(url)
        out.append(p)
    return out


def start_replay_whisper_jobs(
    posts: List[Dict[str, Any]],
    *,
    set_job: SetJobFn,
    force: bool = False,
    force_cpu: Optional[bool] = None,
    max_age_days: Optional[float] = DEFAULT_REPLAY_WHISPER_MAX_DAYS,
) -> List[Dict[str, str]]:
    """为每条带回放 URL 的帖创建独立 console Job（后台线程）。"""
    from console.whisper_service import transcribe_url_sync

    queued: List[Dict[str, str]] = []
    used_names: set[str] = set()

    for post in posts_with_replay(posts, max_age_days=max_age_days):
        url = replay_media_url(post)
        name = _unique_output_name(post, used_names)
        job_id = uuid.uuid4().hex[:12]
        log_buf: List[str] = []

        def _progress(msg: str, _jid: str = job_id, _buf: List[str] = log_buf) -> None:
            text = str(msg or "")[:800]
            _buf.append(text)
            if len(_buf) > 400:
                del _buf[:120]
            set_job(
                _jid,
                status="running",
                type="whisper",
                message=text[:280],
                logs=list(_buf[-160:]),
            )

        def _worker(
            _jid: str = job_id,
            _url: str = url,
            _name: str = name,
            _buf: List[str] = log_buf,
        ) -> None:
            set_job(
                _jid,
                status="running",
                type="whisper",
                message=f"转写 {_name}…",
                logs=[],
                name=_name,
                url=_url,
                started_at=datetime.now().isoformat(timespec="seconds"),
            )
            try:

                def _on_log(line: str) -> None:
                    _progress(line)

                result = transcribe_url_sync(
                    url=_url,
                    title=_name,
                    force=force,
                    force_cpu=force_cpu,
                    on_log=_on_log,
                )
                ok = bool(result.get("ok"))
                set_job(
                    _jid,
                    status="done" if ok else "error",
                    message=(
                        f"转写完成 · {result.get('name')}"
                        if ok
                        else str(result.get("message") or "转写失败")
                    ),
                    result=result,
                    logs=list(_buf[-200:]),
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                )
            except Exception as exc:
                set_job(
                    _jid,
                    status="error",
                    message=str(exc),
                    logs=list(_buf[-200:]),
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                )

        set_job(job_id, status="queued", type="whisper", message="排队中…", name=name, url=url)
        threading.Thread(
            target=_worker,
            daemon=True,
            name=f"whisper-{job_id[:8]}",
        ).start()
        queued.append({"job_id": job_id, "name": name, "url": url})

    return queued
