# coding=utf-8
"""
TrendRadar 控制台 HTTP 服务
- 静态页：资讯获取 / 历史缓存 / Prompt 创作 / CDP 发布
- 复用 crawler / create / public 现有能力
"""

from __future__ import annotations

import json
import os
import random
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from collections import defaultdict
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATE_PATH = PROJECT_ROOT / "output" / "trendradar_posts_state.json"
ARTICLES_DIR = PROJECT_ROOT / "output" / "articles"

PLATFORM_DISPLAY = {
    "x-cdp": "X",
    "x": "X",
    "twitter": "X",
    "reddit": "Reddit",
    "telegram": "Telegram",
    "tg": "Telegram",
}

# 后台任务状态
_JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()

# 周期性资讯任务
_CRAWL_TASKS: Dict[str, Dict[str, Any]] = {}
_CRAWL_TASKS_LOCK = threading.Lock()
TASKS_PATH = PROJECT_ROOT / "output" / "console_crawl_tasks.json"


def _json_bytes(data: Any, status: int = 200) -> tuple[bytes, int, str]:
    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    return body, status, "application/json; charset=utf-8"


def _read_json_body(handler: SimpleHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _publish_queue_module():
    """确保发布队列/缓存已初始化（避免 resolve_publish_media 等调用崩溃）。"""
    from console import publish_queue as pq

    try:
        pq.cache_root()
    except RuntimeError:
        pq.init(
            PROJECT_ROOT / "output" / "publish_queue.json",
            cache_root=PROJECT_ROOT / "output" / "publish_cache",
        )
    return pq


_STATE_LOCK = threading.Lock()


def _load_posts_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"version": 1, "generated_at": "", "platform_labels": {}, "posts": {}}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        return {"error": str(e), "posts": {}}


def _save_posts_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _STATE_LOCK:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)


def _normalize_tags(value: Any) -> List[str]:
    """标签按逗号/分号/竖线分隔；保留空格（支持多词标签）。"""
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,，;；|]+", value)
    elif isinstance(value, list):
        parts = [str(x) for x in value]
    else:
        parts = [str(value)]
    out: List[str] = []
    seen = set()
    for p in parts:
        tag = re.sub(r"\s+", " ", p).strip()
        if not tag or len(tag) > 40:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return out[:30]


def _normalize_post_key(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    # 去掉末尾斜杠与 fragment，提升 href/key 匹配率
    s = s.split("#", 1)[0].rstrip("/")
    return s


def _find_post_ref(
    state: Dict[str, Any], platform_id: str = "", key: str = "", href: str = ""
) -> tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
    """
    定位帖子：返回 (platform_id, key, entry)。
    支持 key / href 互查，以及跨平台兜底扫描。
    """
    posts = state.get("posts") if isinstance(state.get("posts"), dict) else {}
    want_key = _normalize_post_key(key)
    want_href = _normalize_post_key(href) or want_key
    candidates = [want_key, want_href]
    # twitter.com <-> x.com
    for c in list(candidates):
        if "://twitter.com/" in c:
            candidates.append(c.replace("://twitter.com/", "://x.com/", 1))
        if "://x.com/" in c:
            candidates.append(c.replace("://x.com/", "://twitter.com/", 1))
    candidates = [c for c in dict.fromkeys(candidates) if c]

    plat_order: List[str] = []
    if platform_id and platform_id in posts:
        plat_order.append(platform_id)
    for p in posts.keys():
        if p not in plat_order:
            plat_order.append(str(p))

    for plat in plat_order:
        bucket = posts.get(plat)
        if not isinstance(bucket, dict):
            continue
        for cand in candidates:
            entry = bucket.get(cand)
            if isinstance(entry, dict):
                return str(plat), cand, entry
            # 有时 dict key 与 href 字段不一致
            for ek, ev in bucket.items():
                if not isinstance(ev, dict):
                    continue
                ek_n = _normalize_post_key(str(ek))
                href_n = _normalize_post_key(str(ev.get("href") or ""))
                if cand in (ek_n, href_n):
                    return str(plat), str(ek), ev
    return None, None, None


def _find_post_entry(
    state: Dict[str, Any], platform_id: str, key: str
) -> Optional[Dict[str, Any]]:
    _, _, entry = _find_post_ref(state, platform_id=platform_id, key=key)
    return entry


def _platform_display_name(platform_id: str, labels: Optional[Dict[str, Any]] = None) -> str:
    pid = str(platform_id or "").strip()
    if not pid:
        return "未知来源"
    if labels and labels.get(pid):
        # 旧标签可能是乱码/过长，优先用规范短名
        mapped = PLATFORM_DISPLAY.get(pid.lower())
        if mapped:
            return mapped
        return str(labels.get(pid))
    return PLATFORM_DISPLAY.get(pid.lower(), pid)


def _interleave_by_platform(rows: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """按平台轮询混排，避免单一来源占满前 N 条。"""
    if not rows:
        return []
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    order: List[str] = []
    for row in rows:
        pid = str(row.get("platform_id") or "unknown")
        if pid not in buckets:
            order.append(pid)
        buckets[pid].append(row)
    if len(order) <= 1:
        return rows[: max(1, limit)]
    out: List[Dict[str, Any]] = []
    idx = {p: 0 for p in order}
    while len(out) < max(1, limit):
        progressed = False
        for p in order:
            i = idx[p]
            if i < len(buckets[p]):
                out.append(buckets[p][i])
                idx[p] = i + 1
                progressed = True
                if len(out) >= max(1, limit):
                    break
        if not progressed:
            break
    return out


def _platform_counts_from_state(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    posts = state.get("posts") if isinstance(state.get("posts"), dict) else {}
    labels = state.get("platform_labels") if isinstance(state.get("platform_labels"), dict) else {}
    out = []
    for pid, bucket in posts.items():
        n = len(bucket) if isinstance(bucket, dict) else 0
        out.append(
            {
                "id": str(pid),
                "name": _platform_display_name(str(pid), labels),
                "count": n,
            }
        )
    out.sort(key=lambda x: (-int(x["count"]), str(x["name"]).lower()))
    return out


def _collect_post_stats(state: Dict[str, Any]) -> Dict[str, Any]:
    posts = state.get("posts") if isinstance(state.get("posts"), dict) else {}
    counts = {"all": 0, "active": 0, "archived": 0, "watch_later": 0, "tagged": 0}
    tag_map: Dict[str, int] = {}
    for bucket in posts.values():
        if not isinstance(bucket, dict):
            continue
        for entry in bucket.values():
            if not isinstance(entry, dict):
                continue
            counts["all"] += 1
            archived = bool(entry.get("archived"))
            later = bool(entry.get("watch_later"))
            tags = _normalize_tags(entry.get("tags"))
            if archived:
                counts["archived"] += 1
            else:
                counts["active"] += 1
            if later:
                counts["watch_later"] += 1
            if tags:
                counts["tagged"] += 1
            for t in tags:
                tag_map[t] = tag_map.get(t, 0) + 1
    tag_list = [
        {"name": name, "count": count}
        for name, count in sorted(tag_map.items(), key=lambda x: (-x[1], x[0].lower()))
    ]
    return {
        "counts": counts,
        "tags": tag_list,
        "platforms": _platform_counts_from_state(state),
    }


def _entry_public_meta(
    platform_id: str, key: str, entry: Dict[str, Any]
) -> Dict[str, Any]:
    return {
        "platform_id": platform_id,
        "key": key,
        "href": str(entry.get("href") or key),
        "title": str(entry.get("title") or ""),
        "archived": bool(entry.get("archived")),
        "archived_at": str(entry.get("archived_at") or ""),
        "watch_later": bool(entry.get("watch_later")),
        "watch_later_at": str(entry.get("watch_later_at") or ""),
        "tags": _normalize_tags(entry.get("tags")),
    }


def _persist_crawl_tasks() -> None:
    TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _CRAWL_TASKS_LOCK:
        dump = []
        for t in _CRAWL_TASKS.values():
            dump.append(
                {
                    "id": t.get("id"),
                    "keyword": t.get("keyword"),
                    "name": t.get("name") or t.get("keyword") or "",
                    "note": t.get("note") or "",
                    "schedule_mode": t.get("schedule_mode") or "interval",
                    "interval_min": t.get("interval_min", 30),
                    "jitter_min": t.get("jitter_min", 10),
                    "daily_hour": t.get("daily_hour", 9),
                    "expand": bool(t.get("expand", True)),
                    "platforms": t.get("platforms") or ["x-cdp", "reddit", "telegram"],
                    "enabled": bool(t.get("enabled", True)),
                    "created_at": t.get("created_at"),
                    "updated_at": t.get("updated_at") or t.get("created_at"),
                    "stopped_at": t.get("stopped_at"),
                    "last_run_at": t.get("last_run_at"),
                    "next_run_at": t.get("next_run_at"),
                    "last_status": t.get("last_status"),
                    "last_message": t.get("last_message"),
                    "run_count": t.get("run_count", 0),
                    "expansion": t.get("expansion"),
                }
            )
    with open(TASKS_PATH, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "tasks": dump}, f, ensure_ascii=False, indent=2)


def _next_interval_seconds(interval_min: int = 30, jitter_min: int = 10) -> int:
    base = max(5, int(interval_min or 30))
    jitter = max(0, int(jitter_min or 0))
    delta = random.randint(-jitter, jitter) if jitter else 0
    minutes = max(5, base + delta)
    return minutes * 60


def _seconds_until_daily(daily_hour: int = 9, jitter_min: int = 10) -> int:
    """距下次每日定点执行的秒数。"""
    hour = max(0, min(23, int(daily_hour if daily_hour is not None else 9)))
    now = datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    wait = (target - now).total_seconds()
    jitter = max(0, int(jitter_min or 0))
    if jitter:
        wait += random.randint(-jitter, jitter) * 60
    return max(60, int(wait))


def _task_wait_seconds(task: Dict[str, Any]) -> int:
    mode = str(task.get("schedule_mode") or "interval").strip().lower()
    if mode == "daily":
        return _seconds_until_daily(
            int(task.get("daily_hour") if task.get("daily_hour") is not None else 9),
            int(task.get("jitter_min") or 0),
        )
    return _next_interval_seconds(
        int(task.get("interval_min") or 30),
        int(task.get("jitter_min") or 10),
    )


def _schedule_label(task: Dict[str, Any]) -> str:
    mode = str(task.get("schedule_mode") or "interval").strip().lower()
    if mode == "daily":
        hour = int(task.get("daily_hour") if task.get("daily_hour") is not None else 9)
        return f"每天 {hour:02d}:00"
    interval = int(task.get("interval_min") or 30)
    jitter = int(task.get("jitter_min") or 0)
    if interval >= 1440 and interval % 1440 == 0:
        days = interval // 1440
        base = f"每 {days} 天" if days > 1 else "每天(间隔)"
    elif interval >= 60 and interval % 60 == 0:
        base = f"每 {interval // 60} 小时"
    else:
        base = f"每 {interval} 分钟"
    if jitter:
        return f"{base} ±{jitter} 分"
    return base


def _public_task_view(task: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": task.get("id"),
        "keyword": task.get("keyword"),
        "name": task.get("name") or task.get("keyword") or "",
        "note": task.get("note") or "",
        "schedule_mode": task.get("schedule_mode") or "interval",
        "schedule_label": _schedule_label(task),
        "interval_min": task.get("interval_min", 30),
        "jitter_min": task.get("jitter_min", 10),
        "daily_hour": task.get("daily_hour", 9),
        "expand": bool(task.get("expand", True)),
        "platforms": task.get("platforms") or [],
        "enabled": bool(task.get("enabled", True)),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at") or task.get("created_at"),
        "stopped_at": task.get("stopped_at"),
        "last_run_at": task.get("last_run_at"),
        "next_run_at": task.get("next_run_at"),
        "last_status": task.get("last_status"),
        "last_message": task.get("last_message"),
        "run_count": task.get("run_count", 0),
        "expansion": task.get("expansion"),
        "running": bool(task.get("_running")),
        "last_job_id": task.get("last_job_id"),
    }


def _normalize_task_platforms(platforms: Optional[List[str]]) -> List[str]:
    if not platforms:
        return ["x-cdp", "reddit", "telegram"]
    out = []
    seen = set()
    for p in platforms:
        pid = str(p).strip()
        if not pid:
            continue
        key = pid.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(pid)
    return out or ["x-cdp"]


def _find_reusable_task(keyword: str) -> Optional[Dict[str, Any]]:
    """按关键词复用历史任务（不区分大小写）。"""
    kw = (keyword or "").strip().lower()
    if not kw:
        return None
    with _CRAWL_TASKS_LOCK:
        for t in _CRAWL_TASKS.values():
            if str(t.get("keyword") or "").strip().lower() == kw:
                return t
    return None


def _ensure_task_runtime(task: Dict[str, Any]) -> None:
    if not isinstance(task.get("_stop"), threading.Event):
        task["_stop"] = threading.Event()
    task.setdefault("_running", False)


def _spawn_schedule_thread(task_id: str) -> None:
    with _CRAWL_TASKS_LOCK:
        task = _CRAWL_TASKS.get(task_id)
        if not task or not task.get("enabled"):
            return
        th = task.get("_thread")
        if isinstance(th, threading.Thread) and th.is_alive():
            return
        _ensure_task_runtime(task)
        stop_event: threading.Event = task["_stop"]
        stop_event.clear()
    thread = threading.Thread(target=_schedule_loop, args=(task_id,), daemon=True)
    thread.start()
    with _CRAWL_TASKS_LOCK:
        t = _CRAWL_TASKS.get(task_id)
        if t:
            t["_thread"] = thread


def _load_crawl_tasks() -> int:
    """从磁盘恢复历史周期任务；已启用的会自动续跑。"""
    if not TASKS_PATH.exists():
        return 0
    try:
        with open(TASKS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return 0
    raw_tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(raw_tasks, list):
        return 0
    restored = 0
    enabled_ids: List[str] = []
    with _CRAWL_TASKS_LOCK:
        for item in raw_tasks:
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("id") or "").strip() or uuid.uuid4().hex[:10]
            keyword = str(item.get("keyword") or "").strip()
            if not keyword:
                continue
            mode = str(item.get("schedule_mode") or "interval").strip().lower()
            if mode not in ("interval", "daily"):
                mode = "interval"
            task = {
                "id": task_id,
                "keyword": keyword,
                "name": str(item.get("name") or keyword),
                "note": str(item.get("note") or ""),
                "schedule_mode": mode,
                "interval_min": max(5, int(item.get("interval_min") or 30)),
                "jitter_min": max(0, int(item.get("jitter_min") or 0)),
                "daily_hour": max(0, min(23, int(item.get("daily_hour") if item.get("daily_hour") is not None else 9))),
                "expand": bool(item.get("expand", True)),
                "platforms": _normalize_task_platforms(item.get("platforms")),
                "enabled": bool(item.get("enabled", False)),
                "created_at": item.get("created_at") or datetime.now().isoformat(timespec="seconds"),
                "updated_at": item.get("updated_at") or item.get("created_at"),
                "stopped_at": item.get("stopped_at"),
                "last_run_at": item.get("last_run_at"),
                "next_run_at": item.get("next_run_at"),
                "last_status": item.get("last_status") or ("idle" if not item.get("enabled") else "restored"),
                "last_message": item.get("last_message") or "已从历史恢复",
                "run_count": int(item.get("run_count") or 0),
                "expansion": item.get("expansion"),
                "_stop": threading.Event(),
                "_running": False,
            }
            if not task["enabled"]:
                task["_stop"].set()
            _CRAWL_TASKS[task_id] = task
            restored += 1
            if task["enabled"]:
                enabled_ids.append(task_id)
    for tid in enabled_ids:
        _spawn_schedule_thread(tid)
    return restored


def _apply_task_fields(task: Dict[str, Any], body: Dict[str, Any]) -> None:
    if "keyword" in body and str(body.get("keyword") or "").strip():
        task["keyword"] = str(body.get("keyword")).strip()
        if not task.get("name") or task.get("name") == task.get("id"):
            task["name"] = task["keyword"]
    if "name" in body and str(body.get("name") or "").strip():
        task["name"] = str(body.get("name")).strip()
    if "note" in body:
        task["note"] = str(body.get("note") or "").strip()
    if "schedule_mode" in body:
        mode = str(body.get("schedule_mode") or "interval").strip().lower()
        task["schedule_mode"] = mode if mode in ("interval", "daily") else "interval"
    if "interval_min" in body:
        try:
            task["interval_min"] = max(5, int(body.get("interval_min") or 30))
        except Exception:
            pass
    if "jitter_min" in body:
        try:
            task["jitter_min"] = max(0, int(body.get("jitter_min") or 0))
        except Exception:
            pass
    if "daily_hour" in body:
        try:
            task["daily_hour"] = max(0, min(23, int(body.get("daily_hour"))))
        except Exception:
            pass
    if "expand" in body:
        task["expand"] = bool(body.get("expand"))
    if "platforms" in body:
        plats = body.get("platforms")
        if isinstance(plats, str):
            plats = [p.strip() for p in re.split(r"[,，;；|\s]+", plats) if p.strip()]
        if isinstance(plats, list):
            task["platforms"] = _normalize_task_platforms(plats)
    task["updated_at"] = datetime.now().isoformat(timespec="seconds")



def _flatten_posts(
    state: Dict[str, Any],
    keyword: str = "",
    platform: str = "",
    view: str = "all",
    tag: str = "",
) -> List[Dict[str, Any]]:
    posts = state.get("posts") or {}
    labels = state.get("platform_labels") or {}
    kw = (keyword or "").strip().lower()
    plat = (platform or "").strip()
    view_mode = (view or "all").strip().lower()
    tag_filter = (tag or "").strip().lower()
    rows: List[Dict[str, Any]] = []

    for platform_id, bucket in posts.items():
        if plat and str(platform_id) != plat:
            continue
        if not isinstance(bucket, dict):
            continue
        for key, entry in bucket.items():
            if not isinstance(entry, dict):
                continue
            archived = bool(entry.get("archived"))
            watch_later = bool(entry.get("watch_later"))
            tags = _normalize_tags(entry.get("tags"))
            if view_mode == "active" and archived:
                continue
            if view_mode == "archived" and not archived:
                continue
            if view_mode in ("watch_later", "later") and not watch_later:
                continue
            if tag_filter and tag_filter not in [t.lower() for t in tags]:
                continue
            title = str(entry.get("title") or "")
            content = str(entry.get("content") or entry.get("raw") or "")
            summary = str(entry.get("summary") or "").strip()
            href = str(entry.get("href") or key)
            tags_hay = " ".join(tags)
            hay = f"{title} {content} {summary} {href} {tags_hay}".lower()
            if kw and kw not in hay:
                continue
            display = _platform_display_name(str(platform_id), labels)
            source = str(entry.get("source") or display)
            rows.append(
                {
                    "platform_id": str(platform_id),
                    "platform_name": display,
                    "source": source,
                    "key": key,
                    "href": href,
                    "title": title,
                    "raw": entry.get("raw") or "",
                    "content": entry.get("content") or "",
                    "summary": summary,
                    "author": entry.get("author") or "",
                    "fetched_at": entry.get("fetched_at") or "",
                    "first_fetched_at": entry.get("first_fetched_at") or entry.get("fetched_at") or "",
                    "star": entry.get("star", 0),
                    "isUseful": entry.get("isUseful", False),
                    "rank": entry.get("rank"),
                    "archived": archived,
                    "archived_at": str(entry.get("archived_at") or ""),
                    "watch_later": watch_later,
                    "watch_later_at": str(entry.get("watch_later_at") or ""),
                    "tags": tags,
                    "subreddit": str(entry.get("subreddit") or ""),
                    "chat": str(entry.get("chat") or ""),
                }
            )

    def sort_key(item: Dict[str, Any]):
        return str(item.get("fetched_at") or ""), str(item.get("title") or "")

    rows.sort(key=sort_key, reverse=True)
    return rows


def _set_job(job_id: str, **kwargs) -> None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id, {"id": job_id})
        job.update(kwargs)
        _JOBS[job_id] = job


def _get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def _prepare_search_plan(
    keyword: str,
    expand: bool = True,
    platforms: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """衍生关键词并整理各平台查询。"""
    plats = [str(p).strip() for p in (platforms or ["x-cdp", "reddit", "telegram"]) if str(p).strip()]
    plan: Dict[str, Any] = {
        "keyword": keyword,
        "expand": expand,
        "platforms": plats,
        "seeds": [keyword] if keyword else [],
        "twitter_queries": [],
        "reddit_queries": [keyword] if keyword else [],
        "telegram_queries": [keyword] if keyword else [],
        "expansion": None,
    }
    if not keyword:
        return plan

    if expand:
        from console.keyword_expand import expand_keyword

        expansion = expand_keyword(keyword)
        plan["expansion"] = expansion
        if expansion.get("success"):
            seeds = expansion.get("seeds") or [keyword]
            plan["seeds"] = seeds
            plan["twitter_queries"] = expansion.get("twitter_queries") or []
            plan["reddit_queries"] = expansion.get("reddit_queries") or seeds[:4]
            plan["telegram_queries"] = expansion.get("telegram_queries") or seeds[:4]
    else:
        plan["twitter_queries"] = []
        plan["reddit_queries"] = [keyword]
        plan["telegram_queries"] = [keyword]
    return plan


def _run_crawl_job(
    job_id: str,
    keyword: str = "",
    expand: bool = True,
    platforms: Optional[List[str]] = None,
    task_id: Optional[str] = None,
) -> None:
    from utils.stdio_encoding import ensure_utf8_stdio, sanitize_for_console, safe_print

    ensure_utf8_stdio()
    _set_job(
        job_id,
        status="running",
        message="正在准备抓取…",
        started_at=datetime.now().isoformat(),
        keyword=keyword,
        expand=expand,
        platforms=platforms or [],
        task_id=task_id,
    )
    prev_kw = os.environ.get("X_SEARCH_KEYWORDS")
    prev_queries = os.environ.get("X_SEARCH_QUERIES")
    try:
        import sys

        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))

        safe_print("=" * 60)
        safe_print(" [Crawl] 开始抓取")
        safe_print("=" * 60)
        if keyword:
            safe_print(f" 主题: {keyword}")
        else:
            safe_print(" 主题: (使用 config.yaml 默认)")

        plan = _prepare_search_plan(keyword, expand=expand, platforms=platforms)
        _set_job(
            job_id,
            message="衍生词已就绪，开始抓取…",
            expansion=plan.get("expansion"),
            plan={
                "seeds": plan.get("seeds"),
                "twitter_queries": plan.get("twitter_queries"),
                "reddit_queries": plan.get("reddit_queries"),
                "telegram_queries": plan.get("telegram_queries"),
                "platforms": plan.get("platforms"),
            },
        )
        if plan.get("expansion"):
            provider = (plan["expansion"] or {}).get("provider") or "ai"
            safe_print(f" 衍生来源: {provider}")
            tw = plan.get("twitter_queries") or []
            if tw:
                safe_print(f" Twitter 查询 {len(tw)} 条:")
                for q in tw[:6]:
                    safe_print(f"   · {sanitize_for_console(q)}")

        plats = {p.lower() for p in (plan.get("platforms") or [])}
        run_x = (not plats) or any(p in plats for p in ("x-cdp", "x", "twitter", "all"))
        run_reddit = (not plats) or any(p in plats for p in ("reddit", "all"))
        run_tg = (not plats) or any(p in plats for p in ("telegram", "tg", "all"))

        if run_x:
            if plan.get("twitter_queries"):
                os.environ["X_SEARCH_QUERIES"] = " | ".join(plan["twitter_queries"][:8])
                # 同时给 seeds，便于无 queries 兜底路径
                os.environ["X_SEARCH_KEYWORDS"] = ",".join((plan.get("seeds") or [keyword])[:8])
            elif keyword:
                os.environ.pop("X_SEARCH_QUERIES", None)
                os.environ["X_SEARCH_KEYWORDS"] = keyword
            else:
                os.environ.pop("X_SEARCH_KEYWORDS", None)
                os.environ.pop("X_SEARCH_QUERIES", None)

            safe_print(" 平台: X CDP 搜索工作流")
            safe_print("-" * 60)
            from crawler.index import main as crawl_main

            crawl_main()
        else:
            safe_print(" 跳过 X CDP（未选平台）")

        extra_summary = {}
        if run_reddit or run_tg:
            from console.extra_sources import run_extra_searches

            extra_platforms = []
            if run_reddit:
                extra_platforms.append("reddit")
            if run_tg:
                extra_platforms.append("telegram")
            safe_print(f" 额外源: {', '.join(extra_platforms)}")
            extra_summary = run_extra_searches(
                reddit_queries=plan.get("reddit_queries") if run_reddit else [],
                telegram_queries=plan.get("telegram_queries") if run_tg else [],
                platforms=extra_platforms,
            )

        state = _load_posts_state()
        # 列表过滤用主题词，避免衍生长查询匹配不到标题
        filter_kw = keyword
        rows = _flatten_posts(state, keyword=filter_kw)
        plat_counts = defaultdict(int)
        for row in rows:
            plat_counts[str(row.get("platform_id") or "?")] += 1
        plat_bits = []
        for pid, n in sorted(plat_counts.items(), key=lambda x: (-x[1], x[0])):
            plat_bits.append(f"{_platform_display_name(pid)} {n}")
        msg = f"抓取完成，匹配 {len(rows)} 条"
        if plat_bits:
            msg += "｜" + " / ".join(plat_bits)
        if extra_summary:
            msg += (
                f"（本轮 Reddit +{extra_summary.get('reddit', 0)} / "
                f"Telegram +{extra_summary.get('telegram', 0)}）"
            )
            errs = extra_summary.get("errors") or []
            if errs:
                # 把关键原因带进状态栏（截断避免过长）
                tip = str(errs[0])
                if len(tip) > 160:
                    tip = tip[:157] + "..."
                msg += f"；注意：{tip}"
        safe_print("-" * 60)
        safe_print(f" [Crawl] {msg}")
        if extra_summary and (extra_summary.get("errors") or []):
            safe_print(" 额外源说明:")
            for e in (extra_summary.get("errors") or [])[:5]:
                safe_print(f"  ! {sanitize_for_console(str(e))}")
            if int(extra_summary.get("telegram") or 0) == 0 and any(
                "Telegram" in str(e) for e in (extra_summary.get("errors") or [])
            ):
                safe_print(
                    "  提示: Telegram 需先运行 python messages/telegram_listener.py 登录生成会话"
                )
            if int(extra_summary.get("reddit") or 0) == 0:
                safe_print(
                    "  提示: Reddit 官方常 403；已尝试 Arctic Shift 兜底，请确认 HTTPS_PROXY 可用"
                )
        if rows:
            for i, row in enumerate(rows[:5], 1):
                title = sanitize_for_console((row.get("title") or "")[:80])
                src = row.get("platform_name") or row.get("platform_id")
                safe_print(f"  {i}. [{src}] {title}")
            if len(rows) > 5:
                safe_print(f"  ... 另有 {len(rows) - 5} 条，请在页面查看")
        safe_print("=" * 60)
        _set_job(
            job_id,
            status="done",
            message=msg,
            finished_at=datetime.now().isoformat(),
            matched_count=len(rows),
            keyword=keyword,
            extra=extra_summary,
            matched_platforms=[
                {
                    "id": pid,
                    "name": _platform_display_name(pid),
                    "count": n,
                }
                for pid, n in sorted(plat_counts.items(), key=lambda x: (-x[1], x[0]))
            ],
        )
        if task_id:
            with _CRAWL_TASKS_LOCK:
                t = _CRAWL_TASKS.get(task_id)
                if t:
                    t["last_run_at"] = datetime.now().isoformat(timespec="seconds")
                    t["last_status"] = "done"
                    t["last_message"] = msg
                    t["run_count"] = int(t.get("run_count") or 0) + 1
                    t["expansion"] = plan.get("expansion")
            _persist_crawl_tasks()
    except Exception as e:
        err = sanitize_for_console(str(e))
        safe_print("=" * 60)
        safe_print(f" [Crawl] 失败: {err}")
        safe_print("=" * 60)
        _set_job(
            job_id,
            status="error",
            message=err,
            detail=sanitize_for_console(traceback.format_exc()),
            finished_at=datetime.now().isoformat(),
        )
        if task_id:
            with _CRAWL_TASKS_LOCK:
                t = _CRAWL_TASKS.get(task_id)
                if t:
                    t["last_run_at"] = datetime.now().isoformat(timespec="seconds")
                    t["last_status"] = "error"
                    t["last_message"] = err
                    t["run_count"] = int(t.get("run_count") or 0) + 1
            _persist_crawl_tasks()
    finally:
        if prev_kw is None:
            os.environ.pop("X_SEARCH_KEYWORDS", None)
        else:
            os.environ["X_SEARCH_KEYWORDS"] = prev_kw
        if prev_queries is None:
            os.environ.pop("X_SEARCH_QUERIES", None)
        else:
            os.environ["X_SEARCH_QUERIES"] = prev_queries


def _schedule_loop(task_id: str) -> None:
    while True:
        with _CRAWL_TASKS_LOCK:
            task = _CRAWL_TASKS.get(task_id)
            if not task or not task.get("enabled"):
                return
            stop_event: threading.Event = task["_stop"]
            keyword = str(task.get("keyword") or "")
            expand = bool(task.get("expand", True))
            platforms = list(task.get("platforms") or [])
            wait_sec = _task_wait_seconds(task)

        next_at = datetime.now().timestamp() + wait_sec
        with _CRAWL_TASKS_LOCK:
            t = _CRAWL_TASKS.get(task_id)
            if t:
                t["next_run_at"] = datetime.fromtimestamp(next_at).isoformat(timespec="seconds")
        _persist_crawl_tasks()

        if stop_event.wait(wait_sec):
            return

        with _CRAWL_TASKS_LOCK:
            task = _CRAWL_TASKS.get(task_id)
            if not task or not task.get("enabled"):
                return
            if task.get("_running"):
                continue
            task["_running"] = True

        job_id = uuid.uuid4().hex[:12]
        _set_job(job_id, status="queued", message="周期任务触发", keyword=keyword, task_id=task_id)
        try:
            with _CRAWL_TASKS_LOCK:
                t = _CRAWL_TASKS.get(task_id)
                if t:
                    t["last_job_id"] = job_id
            _run_crawl_job(
                job_id,
                keyword=keyword,
                expand=expand,
                platforms=platforms,
                task_id=task_id,
            )
        finally:
            with _CRAWL_TASKS_LOCK:
                t = _CRAWL_TASKS.get(task_id)
                if t:
                    t["_running"] = False


def _run_task_once(task_id: str) -> Optional[str]:
    """立即执行一次已有任务，返回 job_id。"""
    with _CRAWL_TASKS_LOCK:
        task = _CRAWL_TASKS.get(task_id)
        if not task:
            return None
        if task.get("_running"):
            return str(task.get("last_job_id") or "")
        keyword = str(task.get("keyword") or "")
        expand = bool(task.get("expand", True))
        platforms = list(task.get("platforms") or [])
        task["_running"] = True
    job_id = uuid.uuid4().hex[:12]
    _set_job(job_id, status="queued", message="手动触发执行", keyword=keyword, task_id=task_id)

    def _worker():
        try:
            _run_crawl_job(
                job_id,
                keyword=keyword,
                expand=expand,
                platforms=platforms,
                task_id=task_id,
            )
        finally:
            with _CRAWL_TASKS_LOCK:
                t = _CRAWL_TASKS.get(task_id)
                if t:
                    t["_running"] = False

    with _CRAWL_TASKS_LOCK:
        t = _CRAWL_TASKS.get(task_id)
        if t:
            t["last_job_id"] = job_id
            t["last_message"] = "已手动触发"
            t["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _persist_crawl_tasks()
    threading.Thread(target=_worker, daemon=True).start()
    return job_id


def _start_crawl_task(
    keyword: str,
    interval_min: int = 30,
    jitter_min: int = 10,
    expand: bool = True,
    platforms: Optional[List[str]] = None,
    run_now: bool = True,
    schedule_mode: str = "interval",
    daily_hour: int = 9,
    name: str = "",
    note: str = "",
    reuse: bool = True,
) -> Dict[str, Any]:
    keyword = (keyword or "").strip()
    plats = _normalize_task_platforms(platforms)
    mode = (schedule_mode or "interval").strip().lower()
    if mode not in ("interval", "daily"):
        mode = "interval"

    existing = _find_reusable_task(keyword) if reuse else None
    if existing:
        task_id = str(existing.get("id"))
        with _CRAWL_TASKS_LOCK:
            task = _CRAWL_TASKS.get(task_id)
            if task:
                _apply_task_fields(
                    task,
                    {
                        "keyword": keyword,
                        "name": name or task.get("name") or keyword,
                        "note": note if note is not None else task.get("note") or "",
                        "schedule_mode": mode,
                        "interval_min": interval_min,
                        "jitter_min": jitter_min,
                        "daily_hour": daily_hour,
                        "expand": expand,
                        "platforms": plats,
                    },
                )
                task["enabled"] = True
                task["stopped_at"] = None
                task["last_status"] = "queued" if run_now else "idle"
                task["last_message"] = "已复用历史任务并启动"
                _ensure_task_runtime(task)
                stop_event: threading.Event = task["_stop"]
                # 先停旧循环，再清事件并拉起
                stop_event.set()
                task["_stop"] = threading.Event()
                existing = task
            else:
                existing = None
        if existing:
            _persist_crawl_tasks()
            time.sleep(0.05)
            _spawn_schedule_thread(task_id)
            job_id = _run_task_once(task_id) if run_now else None
            with _CRAWL_TASKS_LOCK:
                view = _public_task_view(_CRAWL_TASKS[task_id])
            if job_id:
                view["last_job_id"] = job_id
            return view

    task_id = uuid.uuid4().hex[:10]
    stop_event = threading.Event()
    now = datetime.now().isoformat(timespec="seconds")
    task = {
        "id": task_id,
        "keyword": keyword,
        "name": (name or keyword).strip() or keyword,
        "note": (note or "").strip(),
        "schedule_mode": mode,
        "interval_min": max(5, int(interval_min or 30)),
        "jitter_min": max(0, int(jitter_min or 0)),
        "daily_hour": max(0, min(23, int(daily_hour if daily_hour is not None else 9))),
        "expand": bool(expand),
        "platforms": plats,
        "enabled": True,
        "created_at": now,
        "updated_at": now,
        "stopped_at": None,
        "last_run_at": None,
        "next_run_at": None,
        "last_status": "queued" if run_now else "idle",
        "last_message": "已创建周期任务",
        "run_count": 0,
        "expansion": None,
        "_stop": stop_event,
        "_running": False,
    }
    with _CRAWL_TASKS_LOCK:
        _CRAWL_TASKS[task_id] = task
    _persist_crawl_tasks()

    job_id = None
    if run_now:
        job_id = _run_task_once(task_id)

    _spawn_schedule_thread(task_id)
    with _CRAWL_TASKS_LOCK:
        view = _public_task_view(_CRAWL_TASKS[task_id])
    if job_id:
        view["last_job_id"] = job_id
    return view


def _stop_crawl_task(task_id: str) -> bool:
    with _CRAWL_TASKS_LOCK:
        task = _CRAWL_TASKS.get(task_id)
        if not task:
            return False
        task["enabled"] = False
        task["stopped_at"] = datetime.now().isoformat(timespec="seconds")
        task["updated_at"] = task["stopped_at"]
        task["last_message"] = "已停止（仍保留在历史任务库）"
        task["last_status"] = "stopped"
        task["next_run_at"] = None
        stop_event = task.get("_stop")
        if isinstance(stop_event, threading.Event):
            stop_event.set()
    _persist_crawl_tasks()
    return True


def _resume_crawl_task(task_id: str, run_now: bool = False) -> Optional[Dict[str, Any]]:
    with _CRAWL_TASKS_LOCK:
        task = _CRAWL_TASKS.get(task_id)
        if not task:
            return None
        task["enabled"] = True
        task["stopped_at"] = None
        task["updated_at"] = datetime.now().isoformat(timespec="seconds")
        task["last_message"] = "已重新启动"
        task["last_status"] = "idle"
        _ensure_task_runtime(task)
        stop_event: threading.Event = task["_stop"]
        stop_event.clear()
    _persist_crawl_tasks()
    _spawn_schedule_thread(task_id)
    job_id = None
    if run_now:
        job_id = _run_task_once(task_id)
    with _CRAWL_TASKS_LOCK:
        view = _public_task_view(_CRAWL_TASKS[task_id])
    if job_id:
        view["last_job_id"] = job_id
    return view


def _delete_crawl_task(task_id: str) -> bool:
    """从历史库永久删除。"""
    with _CRAWL_TASKS_LOCK:
        task = _CRAWL_TASKS.get(task_id)
        if not task:
            return False
        task["enabled"] = False
        stop_event = task.get("_stop")
        if isinstance(stop_event, threading.Event):
            stop_event.set()
        del _CRAWL_TASKS[task_id]
    _persist_crawl_tasks()
    return True


def _update_crawl_task(task_id: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    with _CRAWL_TASKS_LOCK:
        task = _CRAWL_TASKS.get(task_id)
        if not task:
            return None
        _apply_task_fields(task, body)
        # 若正在运行，重启调度线程以应用新间隔（通过 stop + respawn）
        need_respawn = bool(task.get("enabled"))
        if need_respawn:
            stop_event = task.get("_stop")
            if isinstance(stop_event, threading.Event):
                stop_event.set()
            task["_stop"] = threading.Event()
    _persist_crawl_tasks()
    if need_respawn:
        # 稍等旧循环退出
        time.sleep(0.05)
        _spawn_schedule_thread(task_id)
    with _CRAWL_TASKS_LOCK:
        return _public_task_view(_CRAWL_TASKS[task_id])

def _list_articles(limit: int = 50) -> List[Dict[str, Any]]:
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(ARTICLES_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    items = []
    for path in files[: max(1, limit)]:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            text = ""
        title = path.stem
        for line in text.splitlines():
            if line.startswith("#"):
                title = line.lstrip("#").strip() or title
                break
        items.append(
            {
                "path": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "name": path.name,
                "title": title,
                "mtime": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "size": path.stat().st_size,
            }
        )
    return items


def _read_article(rel_path: str) -> Dict[str, Any]:
    path = (PROJECT_ROOT / rel_path).resolve()
    if not str(path).startswith(str(ARTICLES_DIR.resolve())):
        return {"success": False, "error": "非法路径"}
    if not path.exists():
        return {"success": False, "error": "文件不存在"}
    text = path.read_text(encoding="utf-8")
    title = path.stem
    body = text
    lines = text.splitlines()
    if lines and lines[0].startswith("#"):
        title = lines[0].lstrip("#").strip()
        body = "\n".join(lines[1:]).strip()
        # 去掉前置元信息块
        if body.startswith("**生成时间**"):
            parts = re.split(r"\n---\n", body, maxsplit=1)
            if len(parts) == 2:
                body = parts[1].strip()
    return {"success": True, "path": rel_path, "title": title, "content": body, "raw": text}


def _save_article(topic: str, content: str, meta: Optional[Dict[str, Any]] = None) -> str:
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]+', "_", (topic or "untitled")[:40]).strip() or "untitled"
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe}.md"
    path = ARTICLES_DIR / filename
    meta = meta or {}
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {topic}\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        if meta.get("platform"):
            f.write(f"**平台**: {meta['platform']}\n\n")
        if meta.get("style"):
            f.write(f"**风格**: {meta['style']}\n\n")
        f.write("---\n\n")
        f.write(content or "")
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def handle_api(method: str, path: str, query: Dict[str, List[str]], body: Dict[str, Any]) -> tuple[bytes, int, str]:
    if path == "/api/health":
        return _json_bytes(
            {
                "ok": True,
                "service": "TrendRadar Console",
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "state_exists": STATE_PATH.exists(),
            }
        )

    if path == "/api/platforms/crawl":
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from crawler.index import CONFIG

        platforms = CONFIG.get("PLATFORMS") or []
        return _json_bytes({"success": True, "platforms": platforms})

    if path == "/api/platforms/publish" and method == "GET":
        fallback = [
            {"id": "binance_square", "name": "币安广场", "enabled": True, "type": "binance_square"},
            {"id": "okx", "name": "OKX", "enabled": True, "type": "okx"},
            {"id": "bitget", "name": "Bitget", "enabled": True, "type": "bitget"},
            {"id": "reddit", "name": "Reddit", "enabled": True, "type": "reddit"},
            {"id": "x", "name": "X / Twitter", "enabled": True, "type": "x"},
        ]
        try:
            if str(PROJECT_ROOT) not in sys.path:
                sys.path.insert(0, str(PROJECT_ROOT))
            from public.index import list_platforms

            platforms = list_platforms() or []
            if not platforms:
                platforms = fallback
            return _json_bytes({"success": True, "platforms": platforms})
        except Exception as e:
            return _json_bytes({"success": True, "platforms": fallback, "warning": str(e)})

    if path == "/api/posts" and method == "GET":
        keyword = (query.get("keyword") or [""])[0]
        platform = (query.get("platform") or [""])[0]
        view = (query.get("view") or ["all"])[0]
        tag = (query.get("tag") or [""])[0]
        try:
            limit = int((query.get("limit") or ["100"])[0])
        except Exception:
            limit = 100
        state = _load_posts_state()
        rows = _flatten_posts(
            state, keyword=keyword, platform=platform, view=view, tag=tag
        )
        # 未指定平台时按来源混排，避免全是 X
        if not (platform or "").strip():
            items = _interleave_by_platform(rows, max(1, limit))
        else:
            items = rows[: max(1, limit)]
        matched_platform_counts: Dict[str, int] = defaultdict(int)
        for row in rows:
            matched_platform_counts[str(row.get("platform_id") or "unknown")] += 1
        matched_platforms = [
            {
                "id": pid,
                "name": _platform_display_name(pid, state.get("platform_labels") or {}),
                "count": count,
            }
            for pid, count in sorted(
                matched_platform_counts.items(), key=lambda x: (-x[1], x[0])
            )
        ]
        try:
            from utils.summary_zh import generate_zh_summary

            dirty = False
            for row in items:
                if str(row.get("summary") or "").strip():
                    continue
                title = str(row.get("title") or "")
                raw = str(row.get("raw") or row.get("content") or "")
                if not (title or raw):
                    continue
                summary = generate_zh_summary(title, raw)
                if not summary:
                    continue
                row["summary"] = summary
                entry = _find_post_entry(
                    state, str(row.get("platform_id") or ""), str(row.get("key") or "")
                )
                if isinstance(entry, dict):
                    entry["summary"] = summary
                    dirty = True
            if dirty:
                try:
                    _save_posts_state(state)
                except Exception:
                    pass
        except Exception:
            pass
        return _json_bytes(
            {
                "success": True,
                "generated_at": state.get("generated_at") or "",
                "total": len(rows),
                "items": items,
                "view": view,
                "tag": tag,
                "matched_platforms": matched_platforms,
                "platform": platform,
                **_collect_post_stats(state),
            }
        )

    if path == "/api/posts/stats" and method == "GET":
        state = _load_posts_state()
        stats = _collect_post_stats(state)
        return _json_bytes(
            {
                "success": True,
                "generated_at": state.get("generated_at") or "",
                **stats,
            }
        )

    if path == "/api/posts/meta" and method == "POST":
        platform_id = str(body.get("platform_id") or "").strip()
        key = str(body.get("key") or body.get("href") or "").strip()
        href = str(body.get("href") or "").strip()
        action = str(body.get("action") or "").strip().lower()
        if not key and not href:
            return _json_bytes({"success": False, "error": "缺少 key 或 href"}, 400)
        if action not in {
            "archive",
            "unarchive",
            "toggle_archive",
            "watch_later",
            "unwatch_later",
            "toggle_watch_later",
            "set_tags",
            "add_tags",
            "remove_tags",
            "clear_tags",
        }:
            return _json_bytes({"success": False, "error": f"不支持的 action: {action}"}, 400)

        state = _load_posts_state()
        found_plat, found_key, entry = _find_post_ref(
            state, platform_id=platform_id, key=key, href=href
        )
        if not isinstance(entry, dict) or not found_plat or not found_key:
            return _json_bytes({"success": False, "error": "未找到该帖子"}, 404)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tags = _normalize_tags(entry.get("tags"))

        if action == "archive":
            entry["archived"] = True
            entry["archived_at"] = now
        elif action == "unarchive":
            entry["archived"] = False
            entry.pop("archived_at", None)
        elif action == "toggle_archive":
            entry["archived"] = not bool(entry.get("archived"))
            if entry["archived"]:
                entry["archived_at"] = now
            else:
                entry.pop("archived_at", None)
        elif action == "watch_later":
            entry["watch_later"] = True
            entry["watch_later_at"] = now
        elif action == "unwatch_later":
            entry["watch_later"] = False
            entry.pop("watch_later_at", None)
        elif action == "toggle_watch_later":
            entry["watch_later"] = not bool(entry.get("watch_later"))
            if entry["watch_later"]:
                entry["watch_later_at"] = now
            else:
                entry.pop("watch_later_at", None)
        elif action == "set_tags":
            tags = _normalize_tags(body.get("tags"))
            entry["tags"] = tags
            entry["tags_updated_at"] = now
        elif action == "add_tags":
            extra = _normalize_tags(body.get("tags"))
            if not extra:
                return _json_bytes({"success": False, "error": "标签不能为空"}, 400)
            merged = list(tags)
            seen = {t.lower() for t in merged}
            for t in extra:
                if t.lower() not in seen:
                    merged.append(t)
                    seen.add(t.lower())
            tags = merged[:30]
            entry["tags"] = tags
            entry["tags_updated_at"] = now
        elif action == "remove_tags":
            remove = {t.lower() for t in _normalize_tags(body.get("tags"))}
            if not remove:
                return _json_bytes({"success": False, "error": "未指定要移除的标签"}, 400)
            tags = [t for t in tags if t.lower() not in remove]
            entry["tags"] = tags
            entry["tags_updated_at"] = now
        elif action == "clear_tags":
            entry["tags"] = []
            entry["tags_updated_at"] = now

        try:
            _save_posts_state(state)
        except Exception as e:
            return _json_bytes({"success": False, "error": f"保存失败: {e}"}, 500)

        stats = _collect_post_stats(state)
        return _json_bytes(
            {
                "success": True,
                "item": _entry_public_meta(found_plat, found_key, entry),
                "counts": stats["counts"],
                "tags": stats["tags"],
            }
        )

    if path == "/api/crawl" and method == "POST":
        keyword = str(body.get("keyword") or "").strip()
        expand = bool(body.get("expand", True)) if keyword else False
        platforms = body.get("platforms")
        if isinstance(platforms, str):
            platforms = [p.strip() for p in re.split(r"[,，;；|\s]+", platforms) if p.strip()]
        elif not isinstance(platforms, list):
            platforms = ["x-cdp", "reddit", "telegram"]
        else:
            platforms = [str(p).strip() for p in platforms if str(p).strip()]

        scheduled = bool(body.get("scheduled") or body.get("task") or body.get("recurring"))
        if scheduled:
            if not keyword:
                return _json_bytes({"success": False, "error": "任务化抓取需要填写关键词"}, 400)
            try:
                interval_min = int(body.get("interval_min") or 30)
            except Exception:
                interval_min = 30
            try:
                jitter_min = int(body.get("jitter_min") or 10)
            except Exception:
                jitter_min = 10
            try:
                daily_hour = int(body.get("daily_hour") if body.get("daily_hour") is not None else 9)
            except Exception:
                daily_hour = 9
            schedule_mode = str(body.get("schedule_mode") or "interval").strip().lower()
            task = _start_crawl_task(
                keyword=keyword,
                interval_min=interval_min,
                jitter_min=jitter_min,
                expand=expand,
                platforms=platforms,
                run_now=bool(body.get("run_now", True)),
                schedule_mode=schedule_mode,
                daily_hour=daily_hour,
                name=str(body.get("name") or ""),
                note=str(body.get("note") or ""),
                reuse=bool(body.get("reuse", True)),
            )
            return _json_bytes(
                {
                    "success": True,
                    "scheduled": True,
                    "task": task,
                    "job_id": task.get("last_job_id"),
                }
            )

        job_id = uuid.uuid4().hex[:12]
        _set_job(
            job_id,
            status="queued",
            message="任务已排队",
            keyword=keyword,
            expand=expand,
            platforms=platforms,
        )
        t = threading.Thread(
            target=_run_crawl_job,
            args=(job_id, keyword, expand, platforms, None),
            daemon=True,
        )
        t.start()
        return _json_bytes({"success": True, "job_id": job_id, "scheduled": False})

    if path == "/api/keywords/expand" and method == "POST":
        keyword = str(body.get("keyword") or "").strip()
        if not keyword:
            return _json_bytes({"success": False, "error": "请填写关键词"}, 400)
        from console.keyword_expand import expand_keyword

        return _json_bytes(expand_keyword(keyword))

    if path == "/api/crawl/tasks" and method == "GET":
        status = ((query.get("status") or ["all"])[0] or "all").strip().lower()
        with _CRAWL_TASKS_LOCK:
            items = [_public_task_view(t) for t in _CRAWL_TASKS.values()]
        if status in ("active", "enabled", "running"):
            items = [t for t in items if t.get("enabled")]
        elif status in ("stopped", "disabled", "history"):
            items = [t for t in items if not t.get("enabled")]
        items.sort(
            key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""),
            reverse=True,
        )
        return _json_bytes(
            {
                "success": True,
                "items": items,
                "counts": {
                    "all": len(_CRAWL_TASKS),
                    "active": sum(1 for t in _CRAWL_TASKS.values() if t.get("enabled")),
                    "stopped": sum(1 for t in _CRAWL_TASKS.values() if not t.get("enabled")),
                },
            }
        )

    if path == "/api/crawl/tasks" and method == "POST":
        keyword = str(body.get("keyword") or "").strip()
        if not keyword:
            return _json_bytes({"success": False, "error": "请填写关键词"}, 400)
        platforms = body.get("platforms") or ["x-cdp", "reddit", "telegram"]
        if isinstance(platforms, str):
            platforms = [p.strip() for p in re.split(r"[,，;；|\s]+", platforms) if p.strip()]
        try:
            interval_min = int(body.get("interval_min") or 30)
        except Exception:
            interval_min = 30
        try:
            jitter_min = int(body.get("jitter_min") or 10)
        except Exception:
            jitter_min = 10
        try:
            daily_hour = int(body.get("daily_hour") if body.get("daily_hour") is not None else 9)
        except Exception:
            daily_hour = 9
        task = _start_crawl_task(
            keyword=keyword,
            interval_min=interval_min,
            jitter_min=jitter_min,
            expand=bool(body.get("expand", True)),
            platforms=platforms,
            run_now=bool(body.get("run_now", True)),
            schedule_mode=str(body.get("schedule_mode") or "interval"),
            daily_hour=daily_hour,
            name=str(body.get("name") or ""),
            note=str(body.get("note") or ""),
            reuse=bool(body.get("reuse", True)),
        )
        return _json_bytes({"success": True, "task": task, "job_id": task.get("last_job_id")})

    if path.startswith("/api/crawl/tasks/") and method in ("DELETE", "POST"):
        parts = [p for p in path.split("/api/crawl/tasks/", 1)[1].strip("/").split("/") if p]
        task_id = parts[0] if parts else ""
        action = ""
        if method == "POST":
            action = str(body.get("action") or "").strip().lower()
            if len(parts) > 1:
                action = parts[1].strip().lower() or action
        if method == "DELETE" or action in ("stop", "disable"):
            ok = _stop_crawl_task(task_id)
            if not ok:
                return _json_bytes({"success": False, "error": "任务不存在"}, 404)
            with _CRAWL_TASKS_LOCK:
                task = _CRAWL_TASKS.get(task_id)
                view = _public_task_view(task) if task else {"id": task_id}
            return _json_bytes({"success": True, "stopped": True, "task": view})
        if action in ("start", "resume", "enable"):
            view = _resume_crawl_task(task_id, run_now=bool(body.get("run_now", False)))
            if not view:
                return _json_bytes({"success": False, "error": "任务不存在"}, 404)
            return _json_bytes({"success": True, "task": view, "job_id": view.get("last_job_id")})
        if action in ("run", "run_now", "trigger"):
            job_id = _run_task_once(task_id)
            if job_id is None:
                return _json_bytes({"success": False, "error": "任务不存在"}, 404)
            with _CRAWL_TASKS_LOCK:
                view = _public_task_view(_CRAWL_TASKS[task_id])
            return _json_bytes({"success": True, "job_id": job_id, "task": view})
        if action in ("update", "edit", "patch"):
            view = _update_crawl_task(task_id, body)
            if not view:
                return _json_bytes({"success": False, "error": "任务不存在"}, 404)
            return _json_bytes({"success": True, "task": view})
        if action in ("delete", "remove", "purge"):
            ok = _delete_crawl_task(task_id)
            if not ok:
                return _json_bytes({"success": False, "error": "任务不存在"}, 404)
            return _json_bytes({"success": True, "deleted": True, "id": task_id})
        return _json_bytes({"success": False, "error": "未知操作"}, 400)

    if path.startswith("/api/jobs/") and method == "GET":
        job_id = path.split("/api/jobs/", 1)[1].strip("/")
        job = _get_job(job_id)
        if not job:
            return _json_bytes({"success": False, "error": "任务不存在"}, 404)
        return _json_bytes({"success": True, "job": job})

    if path == "/api/articles" and method == "GET":
        try:
            limit = int((query.get("limit") or ["50"])[0])
        except Exception:
            limit = 50
        return _json_bytes({"success": True, "items": _list_articles(limit)})

    if path == "/api/article" and method == "GET":
        rel = (query.get("path") or [""])[0]
        return _json_bytes(_read_article(rel))

    # ---------- 语料库 corpus（拆解 / CRUD / 再生成） ----------
    if path == "/api/corpus/stats" and method == "GET":
        from corpus.db import init_db, stats as corpus_stats

        init_db()
        return _json_bytes({"success": True, **corpus_stats()})

    if path == "/api/corpus/templates" and method == "GET":
        from corpus.db import init_db, list_templates

        init_db()
        try:
            limit = int((query.get("limit") or ["50"])[0])
        except Exception:
            limit = 50
        items = list_templates(
            emotion=(query.get("emotion") or [""])[0],
            tag=(query.get("tag") or [""])[0],
            quality=(query.get("quality") or [""])[0],
            status=(query.get("status") or ["active"])[0] or "active",
            keyword=(query.get("keyword") or [""])[0],
            platform=(query.get("platform") or [""])[0],
            material_category=(query.get("material_category") or [""])[0],
            category_template=(
                True
                if (query.get("category_template") or [""])[0] in ("1", "true", "yes")
                else False
                if (query.get("category_template") or [""])[0] in ("0", "false", "no")
                else None
            ),
            limit=limit,
        )
        return _json_bytes({"success": True, "total": len(items), "items": items})

    if path.startswith("/api/corpus/templates/") and method == "GET":
        from corpus.db import get_template, init_db, list_template_history

        init_db()
        parts = [p for p in path.split("/api/corpus/templates/", 1)[1].strip("/").split("/") if p]
        if not parts:
            return _json_bytes({"success": False, "error": "无效 id"}, 400)
        try:
            tid = int(parts[0])
        except Exception:
            return _json_bytes({"success": False, "error": "无效 id"}, 400)
        if len(parts) > 1 and parts[1] == "history":
            try:
                limit = int((query.get("limit") or ["30"])[0])
            except Exception:
                limit = 30
            return _json_bytes(
                {
                    "success": True,
                    "items": list_template_history(tid, limit=limit),
                    "template_id": tid,
                }
            )
        item = get_template(tid)
        if not item:
            return _json_bytes({"success": False, "error": "模板不存在"}, 404)
        return _json_bytes({"success": True, "item": item})

    if path == "/api/corpus/templates" and method == "POST":
        from corpus.db import create_template, init_db

        init_db()
        item = create_template(
            source_platform=str(body.get("source_platform") or body.get("platform") or ""),
            source_url=str(body.get("source_url") or body.get("url") or body.get("href") or ""),
            source_key=str(body.get("source_key") or body.get("key") or ""),
            source_title=str(body.get("source_title") or body.get("title") or ""),
            raw_text=str(body.get("raw_text") or body.get("raw") or body.get("content") or ""),
            pattern=str(body.get("pattern") or ""),
            emotion=str(body.get("emotion") or ""),
            tension=str(body.get("tension") or ""),
            keywords=body.get("keywords") if isinstance(body.get("keywords"), list) else [],
            hooks=str(body.get("hooks") or ""),
            tags=body.get("tags") if isinstance(body.get("tags"), list) else [],
            weight=float(body.get("weight") or 1.0),
            quality=str(body.get("quality") or "unrated"),
            status=str(body.get("status") or "active"),
            provenance=body.get("provenance") if isinstance(body.get("provenance"), dict) else {},
            factors=body.get("factors") if isinstance(body.get("factors"), dict) else {},
        )
        return _json_bytes({"success": True, "item": item})

    if path.startswith("/api/corpus/templates/") and method == "POST":
        from corpus.db import (
            archive_template,
            delete_template,
            get_template,
            init_db,
            update_template,
        )

        init_db()
        parts = [p for p in path.split("/api/corpus/templates/", 1)[1].strip("/").split("/") if p]
        try:
            tid = int(parts[0])
        except Exception:
            return _json_bytes({"success": False, "error": "无效 id"}, 400)
        action = str(body.get("action") or (parts[1] if len(parts) > 1 else "update")).strip().lower()
        if action in ("update", "edit", "patch"):
            item = update_template(tid, body, history_reason="manual_edit")
            if not item:
                return _json_bytes({"success": False, "error": "模板不存在"}, 404)
            return _json_bytes({"success": True, "item": item})
        if action in ("archive",):
            item = archive_template(tid)
            return _json_bytes({"success": True, "item": item})
        if action in ("restore", "unarchive"):
            item = update_template(tid, {"status": "active"}, history_reason="restore")
            return _json_bytes({"success": True, "item": item})
        if action in ("delete", "remove"):
            ok = delete_template(tid, hard=bool(body.get("hard")))
            return _json_bytes({"success": ok, "deleted": ok, "id": tid})
        if action in ("rate_good", "good"):
            item = update_template(
                tid,
                {"quality": "good", "weight": float((get_template(tid) or {}).get("weight") or 1) + 0.3},
                history_reason="rate_good",
            )
            return _json_bytes({"success": True, "item": item})
        if action in ("rate_bad", "bad"):
            item = update_template(tid, {"quality": "bad"}, history_reason="rate_bad")
            return _json_bytes({"success": True, "item": item})
        if action in ("add_tags",):
            cur = get_template(tid)
            if not cur:
                return _json_bytes({"success": False, "error": "模板不存在"}, 404)
            tags = list(cur.get("tags") or [])
            extra = body.get("tags") if isinstance(body.get("tags"), list) else []
            for t in extra:
                if t and t not in tags:
                    tags.append(str(t))
            item = update_template(tid, {"tags": tags}, history_reason="add_tags")
            return _json_bytes({"success": True, "item": item})
        if action in ("set_material_category", "material_category"):
            from corpus.db import patch_template_factors

            cat = str(body.get("material_category") or body.get("category") or "").strip()
            item = patch_template_factors(
                tid,
                {"material_category": cat},
                history_reason="set_material_category",
            )
            if not item:
                return _json_bytes({"success": False, "error": "模板不存在"}, 404)
            return _json_bytes({"success": True, "item": item})
        if action in ("set_category_template", "category_template"):
            from corpus.db import patch_template_factors

            enabled = body.get("enabled")
            if enabled is None:
                enabled = body.get("is_category_template")
            if enabled is None:
                cur = get_template(tid) or {}
                factors = cur.get("factors") or {}
                enabled = not bool(factors.get("is_category_template"))
            cat = str(body.get("material_category") or body.get("category") or "").strip()
            patch: Dict[str, Any] = {"is_category_template": bool(enabled)}
            if cat:
                patch["material_category"] = cat
            elif enabled:
                cur = get_template(tid) or {}
                existing = str((cur.get("factors") or {}).get("material_category") or "").strip()
                if not existing:
                    return _json_bytes(
                        {"success": False, "error": "请先选择素材类目或指定 material_category"},
                        400,
                    )
            item = patch_template_factors(tid, patch, history_reason="set_category_template")
            if not item:
                return _json_bytes({"success": False, "error": "模板不存在"}, 404)
            return _json_bytes({"success": True, "item": item})
        if action in ("restore_history", "rollback"):
            from corpus.db import list_template_history

            hid = body.get("history_id")
            hist = list_template_history(tid, limit=100)
            snap = None
            for h in hist:
                if hid is None or int(h.get("id") or 0) == int(hid):
                    snap = h.get("snapshot") or {}
                    if hid is not None:
                        break
            if not snap:
                return _json_bytes({"success": False, "error": "历史快照不存在"}, 404)
            fields = {
                k: snap.get(k)
                for k in (
                    "pattern",
                    "emotion",
                    "tension",
                    "keywords",
                    "hooks",
                    "tags",
                    "weight",
                    "quality",
                    "status",
                    "source_title",
                    "raw_text",
                    "factors",
                    "provenance",
                )
                if snap.get(k) is not None
            }
            item = update_template(tid, fields, history_reason=f"rollback:{hid or 'latest'}")
            return _json_bytes({"success": True, "item": item})
        return _json_bytes({"success": False, "error": f"未知操作: {action}"}, 400)

    if path == "/api/corpus/deconstruct" and method == "POST":
        from corpus.deconstruct import deconstruct_post, import_and_deconstruct

        posts = body.get("posts")
        if isinstance(posts, list) and posts:
            return _json_bytes(import_and_deconstruct(posts))

        title = str(body.get("title") or "")
        raw_text = str(body.get("raw") or body.get("content") or body.get("summary") or "")
        platform = str(body.get("platform") or body.get("platform_id") or "")
        url = str(body.get("url") or body.get("href") or "")
        source_key = str(body.get("key") or body.get("source_key") or "")
        tags = body.get("tags") if isinstance(body.get("tags"), list) else []
        fetched_at = str(body.get("fetched_at") or "")
        author = str(body.get("author") or "")

        # 仅传 key 时从本地缓存补全正文，便于列表一键拆解
        if source_key or url:
            state = _load_posts_state()
            _, found_key, entry = _find_post_ref(
                state, platform_id=platform, key=source_key, href=url
            )
            if isinstance(entry, dict):
                title = title or str(entry.get("title") or "")
                raw_text = raw_text or str(
                    entry.get("content")
                    or entry.get("raw")
                    or entry.get("summary")
                    or entry.get("title")
                    or ""
                )
                platform = platform or str(entry.get("platform_id") or "")
                url = url or str(entry.get("href") or found_key or "")
                source_key = source_key or str(found_key or entry.get("key") or url)
                fetched_at = fetched_at or str(entry.get("fetched_at") or "")
                author = author or str(entry.get("author") or "")
                if not tags and isinstance(entry.get("tags"), list):
                    tags = list(entry.get("tags") or [])

        result = deconstruct_post(
            title=title,
            raw_text=raw_text,
            platform=platform,
            url=url,
            source_key=source_key,
            tags=tags,
            collect_meta={
                "via": platform or "console",
                "fetched_at": fetched_at,
                "author": author,
            },
        )
        status = 200 if result.get("success") else 400
        return _json_bytes(result, status)

    if path == "/api/corpus/generate" and method == "POST":
        from corpus.generate import compose_from_templates, regenerate_from_template
        from corpus.lab import lab_compose

        # Post Lab 多版本模式
        if body.get("lab") or body.get("mode") == "lab" or body.get("variants"):
            ids = body.get("template_ids") if isinstance(body.get("template_ids"), list) else []
            tid_list = []
            for x in ids:
                try:
                    tid_list.append(int(x))
                except Exception:
                    pass
            if body.get("template_id") is not None and not tid_list:
                try:
                    tid_list = [int(body.get("template_id"))]
                except Exception:
                    pass
            result = lab_compose(
                template_ids=tid_list,
                topic=str(body.get("topic") or "").strip(),
                formula_id=str(body.get("formula") or body.get("formula_id") or "contrarian"),
                prompt_profile_id=str(
                    body.get("prompt_profile")
                    or body.get("profile")
                    or body.get("prompt_profile_id")
                    or "general"
                ),
                platform_style=str(body.get("platform_style") or body.get("style") or "X/Twitter"),
                extra_prompt=str(body.get("prompt") or body.get("extra_prompt") or ""),
                variant_count=int(body.get("variant_count") or 3),
                bump_weight=bool(body.get("bump_weight", True)),
                material_category=str(
                    body.get("material_category") or body.get("material") or ""
                ).strip(),
            )
            status = 200 if result.get("success") else 400
            return _json_bytes(result, status)

        ids = body.get("template_ids")
        tid_list = []
        if isinstance(ids, list) and ids:
            for x in ids:
                try:
                    tid_list.append(int(x))
                except Exception:
                    pass
        elif body.get("template_id") is not None:
            try:
                tid_list = [int(body.get("template_id"))]
            except Exception:
                tid_list = []
        if not tid_list:
            return _json_bytes({"success": False, "error": "缺少 template_id / template_ids"}, 400)

        topic = str(body.get("topic") or "").strip()
        style = str(body.get("platform_style") or body.get("style") or "通用")
        extra = str(body.get("prompt") or body.get("extra_prompt") or "")
        bump = bool(body.get("bump_weight", True))
        if len(tid_list) == 1:
            result = regenerate_from_template(
                template_id=tid_list[0],
                topic=topic,
                platform_style=style,
                extra_prompt=extra,
                bump_weight=bump,
            )
        else:
            result = compose_from_templates(
                template_ids=tid_list,
                topic=topic,
                platform_style=style,
                extra_prompt=extra,
                bump_weight=bump,
            )
        if result.get("success") and body.get("save_article") and result.get("content"):
            saved = _save_article(
                str(body.get("topic") or "语料再生成"),
                result["content"],
                {"platform": body.get("platform_style") or "语料", "style": "爆款模板"},
            )
            result["saved_path"] = saved
        status = 200 if result.get("success") else 400
        return _json_bytes(result, status)

    if path == "/api/corpus/lab/formulas" and method == "GET":
        from corpus.lab import list_formulas

        return _json_bytes({"success": True, "items": list_formulas()})

    if path == "/api/corpus/lab/materials" and method == "GET":
        from corpus.materials import material_category_stats

        return _json_bytes({"success": True, **material_category_stats()})

    if path == "/api/corpus/lab/profiles" and method == "GET":
        from corpus.lab import list_prompt_profiles, is_profiles_customized

        return _json_bytes(
            {
                "success": True,
                "items": list_prompt_profiles(),
                "customized": is_profiles_customized(),
            }
        )

    if path == "/api/corpus/lab/profiles/config" and method == "GET":
        from corpus.lab import list_prompt_profiles_full, is_profiles_customized

        return _json_bytes(
            {
                "success": True,
                "items": list_prompt_profiles_full(),
                "customized": is_profiles_customized(),
            }
        )

    if path == "/api/corpus/lab/profiles/config" and method == "POST":
        from corpus.lab import reset_prompt_profiles, save_prompt_profiles

        if body.get("reset"):
            return _json_bytes(reset_prompt_profiles())
        profiles = body.get("profiles")
        if not isinstance(profiles, list):
            return _json_bytes({"success": False, "error": "profiles 须为数组"}, 400)
        result = save_prompt_profiles(profiles)
        status = 200 if result.get("success") else 400
        return _json_bytes(result, status)

    if path == "/api/corpus/lab/tweak" and method == "POST":
        from corpus.lab import tweak_content

        result = tweak_content(
            content=str(body.get("content") or ""),
            tweak_id=str(body.get("tweak") or body.get("tweak_id") or "sharper_hook"),
            custom=str(body.get("custom") or ""),
            topic=str(body.get("topic") or ""),
        )
        status = 200 if result.get("success") else 400
        return _json_bytes(result, status)

    if path == "/api/corpus/lab/feature" and method == "POST":
        from corpus.lab import feature_variant

        tids = []
        raw_ids = body.get("template_ids") if isinstance(body.get("template_ids"), list) else []
        for x in raw_ids:
            try:
                tids.append(int(x))
            except Exception:
                pass
        gid = body.get("generation_id")
        try:
            gid_int = int(gid) if gid is not None and str(gid).strip() != "" else None
        except Exception:
            gid_int = None
        cards = body.get("source_cards") if isinstance(body.get("source_cards"), list) else None
        cot = body.get("cot") if isinstance(body.get("cot"), list) else None
        result = feature_variant(
            content=str(body.get("content") or ""),
            topic=str(body.get("topic") or ""),
            hook=str(body.get("hook") or ""),
            variant_id=str(body.get("variant_id") or body.get("id") or ""),
            variant_label=str(body.get("variant_label") or body.get("label") or ""),
            formula_id=str(body.get("formula") or body.get("formula_id") or ""),
            generation_id=gid_int,
            template_ids=tids,
            source_cards=cards,
            cot=[str(x) for x in (cot or [])],
            platform_style=str(body.get("platform_style") or body.get("style") or "X/Twitter"),
            note=str(body.get("note") or ""),
        )
        status = 200 if result.get("success") else 400
        return _json_bytes(result, status)

    if path == "/api/corpus/capture" and method == "POST":
        from corpus.lab import quick_capture

        result = quick_capture(
            str(body.get("text") or body.get("content") or ""),
            source_url=str(body.get("url") or body.get("href") or ""),
        )
        status = 200 if result.get("success") else 400
        return _json_bytes(result, status)

    if path == "/api/corpus/synthesize" and method == "POST":
        from corpus.synthesize import pick_random_posts, synthesize_from_posts

        mode = str(body.get("mode") or "specified").strip().lower()
        posts = body.get("posts") if isinstance(body.get("posts"), list) else []
        keys = body.get("keys") if isinstance(body.get("keys"), list) else []
        refs = body.get("refs") if isinstance(body.get("refs"), list) else []
        need_cache = bool(keys or refs) or mode in ("random", "sample")
        if need_cache:
            state = _load_posts_state()
            pool = _flatten_posts(
                state,
                keyword=str(body.get("keyword") or ""),
                platform=str(body.get("platform") or ""),
                view=str(body.get("view") or "all"),
                tag=str(body.get("tag") or ""),
            )
            if mode in ("random", "sample") and not keys and not refs:
                try:
                    n = int(body.get("count") or body.get("n") or 3)
                except Exception:
                    n = 3
                posts = pick_random_posts(pool, n)
            else:
                if keys:
                    want = {str(k) for k in keys}
                    posts = [
                        p
                        for p in pool
                        if str(p.get("key") or "") in want or str(p.get("href") or "") in want
                    ]
                for ref in refs:
                    if not isinstance(ref, dict):
                        continue
                    found_plat, found_key, entry = _find_post_ref(
                        state,
                        platform_id=str(ref.get("platform_id") or ""),
                        key=str(ref.get("key") or ""),
                        href=str(ref.get("href") or ""),
                    )
                    if isinstance(entry, dict):
                        posts.append(
                            {
                                "title": entry.get("title"),
                                "raw": entry.get("content") or entry.get("raw"),
                                "content": entry.get("content") or entry.get("raw"),
                                "summary": entry.get("summary"),
                                "platform_id": found_plat
                                or ref.get("platform_id")
                                or entry.get("platform_id"),
                                "key": found_key or ref.get("key") or entry.get("key"),
                                "href": entry.get("href"),
                                "tags": entry.get("tags") or [],
                            }
                        )
        result = synthesize_from_posts(
            posts,
            tags=body.get("tags") if isinstance(body.get("tags"), list) else [],
            note=str(body.get("note") or ""),
        )
        status = 200 if result.get("success") else 400
        return _json_bytes(result, status)

    if path == "/api/corpus/generations" and method == "GET":
        from corpus.db import init_db, list_generations

        init_db()
        tid = None
        if (query.get("template_id") or [""])[0]:
            try:
                tid = int((query.get("template_id") or [""])[0])
            except Exception:
                tid = None
        try:
            limit = int((query.get("limit") or ["30"])[0])
        except Exception:
            limit = 30
        featured_flag = str((query.get("featured") or [""])[0]).lower()
        featured_only = featured_flag in ("1", "true", "yes", "featured")
        return _json_bytes(
            {
                "success": True,
                "items": list_generations(
                    template_id=tid, featured_only=featured_only, limit=limit
                ),
            }
        )

    if path == "/api/corpus/taxonomy" and method == "GET":
        from corpus.taxonomy import TAG_TREE, flatten_tag_options

        return _json_bytes(
            {
                "success": True,
                "tree": TAG_TREE,
                "options": [
                    {"domain": d, "primary": p, "secondary": s}
                    for d, p, s in flatten_tag_options()
                ],
            }
        )

    if path == "/api/corpus/xgrowth/run" and method == "POST":
        job_id = uuid.uuid4().hex[:12]
        try:
            limit = int(body.get("limit") or 8)
        except Exception:
            limit = 8
        try:
            min_velocity = int(body.get("min_velocity") or 0)
        except Exception:
            min_velocity = 0
        include_potential = bool(body.get("include_potential", True))
        open_tweet = bool(body.get("open_tweet", True))

        def _progress(msg: str) -> None:
            _set_job(job_id, message=str(msg or "")[:300])

        def _worker() -> None:
            _set_job(
                job_id,
                status="running",
                type="xgrowth_viral",
                message="开始抓取 xgrowth 热榜…",
                started_at=datetime.now().isoformat(timespec="seconds"),
            )
            try:
                from corpus.xgrowth import run_xgrowth_viral_pipeline

                result = run_xgrowth_viral_pipeline(
                    limit=limit,
                    include_potential=include_potential,
                    open_tweet=open_tweet,
                    min_velocity=min_velocity,
                    progress=_progress,
                )
                _set_job(
                    job_id,
                    status="done" if result.get("success") else "error",
                    message=(
                        f"完成：成功 {result.get('ok', 0)} / 失败 {result.get('fail', 0)}"
                        if result.get("success")
                        else str(result.get("error") or "失败")
                    ),
                    result=result,
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                )
            except Exception as e:
                _set_job(
                    job_id,
                    status="error",
                    message=str(e),
                    error=str(e),
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                )

        _set_job(
            job_id,
            status="queued",
            type="xgrowth_viral",
            message="排队中",
            limit=limit,
            include_potential=include_potential,
            open_tweet=open_tweet,
            min_velocity=min_velocity,
        )
        threading.Thread(target=_worker, name=f"xgrowth-{job_id}", daemon=True).start()
        return _json_bytes({"success": True, "job_id": job_id})

    if path == "/api/create" and method == "POST":
        topic = str(body.get("topic") or "").strip()
        if not topic:
            return _json_bytes({"success": False, "error": "请填写主题或关键词"}, 400)
        requirements = str(body.get("prompt") or body.get("requirements") or "").strip()
        platform = str(body.get("platform") or "通用").strip() or "通用"
        content_type = str(body.get("type") or "技术文章").strip() or "技术文章"
        style = str(body.get("style") or "专业").strip() or "专业"
        try:
            words = int(body.get("words") or 2000)
        except Exception:
            words = 2000

        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from create.index import generate_article_by_topic

        result = generate_article_by_topic(
            topic=topic,
            requirements=requirements,
            platform=platform,
            content_type=content_type,
            word_count=words,
            style=style,
        )
        saved = ""
        if result.get("success") and result.get("content"):
            saved = _save_article(
                topic,
                result["content"],
                {"platform": platform, "style": style},
            )
            result["saved_path"] = saved
        return _json_bytes(result)

    if path == "/api/publish" and method == "POST":
        title = str(body.get("title") or "").strip()
        content = str(body.get("content") or body.get("text") or "").strip()
        file_path = str(body.get("file") or "").strip()
        tags = str(body.get("tags") or "").strip() or None
        platforms = body.get("platforms")
        if isinstance(platforms, str):
            platforms = [p.strip() for p in platforms.split(",") if p.strip()]
        if not isinstance(platforms, list):
            platforms = None

        media_paths = []
        try:
            pq = _publish_queue_module()
            media_paths = pq.resolve_publish_media(body)
        except ValueError as e:
            return _json_bytes({"success": False, "error": str(e)}, 400)
        except Exception as e:
            return _json_bytes({"success": False, "error": f"媒体处理失败: {e}"}, 500)

        if file_path and not content:
            art = _read_article(file_path)
            if not art.get("success"):
                return _json_bytes(art, 400)
            title = title or art["title"]
            content = content or art["content"]

        use_cdp = body.get("use_cdp", True)
        if isinstance(use_cdp, str):
            use_cdp = use_cdp.strip().lower() not in ("0", "false", "no", "off")
        else:
            use_cdp = bool(use_cdp)
        debugger_url = str(body.get("debugger_url") or "").strip()
        submit = body.get("submit", True)
        if isinstance(submit, str):
            submit = submit.strip().lower() not in ("0", "false", "no", "off")
        else:
            submit = bool(submit)

        # 控制台 CDP 发布：正文或图片至少其一，不要求标题
        if not content and not media_paths:
            return _json_bytes(
                {"success": False, "error": "请填写正文或上传图片"}, 400
            )

        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        try:
            from public.index import publish_content

            result = publish_content(
                content={"title": title, "content": content},
                platform_ids=platforms,
                tags=tags,
                use_cdp=use_cdp,
                debugger_url=debugger_url or None,
                media_paths=media_paths,
                submit=submit,
            )
            result["media_paths"] = media_paths
            return _json_bytes(result)
        except Exception as e:
            return _json_bytes({"success": False, "error": str(e)}, 500)

    # —— 定时发布队列 ——
    if path == "/api/publish/queue" and method == "GET":
        pq = _publish_queue_module()

        status = (query.get("status") or [""])[0].strip() or None
        include_done = (query.get("include_done") or ["1"])[0] not in ("0", "false", "no")
        return _json_bytes(
            {
                "success": True,
                "items": pq.list_items(status=status, include_done=include_done),
                "stats": pq.stats(),
                "cache_root": str(pq.cache_root()),
            }
        )

    if path == "/api/publish/queue" and method == "POST":
        pq = _publish_queue_module()

        try:
            item = pq.add_item(body)
            return _json_bytes({"success": True, "item": item, "stats": pq.stats()})
        except ValueError as e:
            return _json_bytes({"success": False, "error": str(e)}, 400)
        except Exception as e:
            return _json_bytes({"success": False, "error": str(e)}, 500)

    if path == "/api/publish/cache/save" and method == "POST":
        from console import publish_queue as pq

        try:
            item = pq.save_draft(body, enqueue=False)
            return _json_bytes({"success": True, "item": item, "stats": pq.stats()})
        except ValueError as e:
            return _json_bytes({"success": False, "error": str(e)}, 400)
        except Exception as e:
            return _json_bytes({"success": False, "error": str(e)}, 500)

    if path == "/api/publish/cache/months" and method == "GET":
        from console import publish_queue as pq

        return _json_bytes(
            {
                "success": True,
                "months": pq.list_months(),
                "cache_root": str(pq.cache_root()),
            }
        )

    if path == "/api/publish/cache" and method == "GET":
        from console import publish_queue as pq

        month = (query.get("month") or [""])[0].strip()
        if not month:
            month = datetime.now().strftime("%Y-%m")
        try:
            items = pq.list_cache_month(month)
            return _json_bytes(
                {
                    "success": True,
                    "month": month,
                    "items": items,
                    "cache_root": str(pq.cache_root()),
                }
            )
        except ValueError as e:
            return _json_bytes({"success": False, "error": str(e)}, 400)

    if path == "/api/publish/cache/content" and method == "GET":
        from console import publish_queue as pq

        rel = (query.get("rel") or [""])[0].strip()
        try:
            text = pq.read_content_md(rel)
            return _json_bytes({"success": True, "rel": rel, "content_md": text})
        except Exception as e:
            return _json_bytes({"success": False, "error": str(e)}, 400)

    if path == "/api/publish/cache/reveal" and method == "POST":
        from console import publish_queue as pq

        rel = str(body.get("rel") or body.get("path") or body.get("storage_dir") or "").strip()
        try:
            result = pq.reveal_in_finder(rel)
            return _json_bytes(result)
        except Exception as e:
            return _json_bytes({"success": False, "error": str(e)}, 400)

    if path == "/api/publish/cache/file" and method == "GET":
        from console import publish_queue as pq
        import mimetypes

        rel = (query.get("rel") or [""])[0].strip()
        try:
            fpath = pq.resolve_cache_path(rel)
            if not fpath.is_file():
                return _json_bytes({"success": False, "error": "文件不存在"}, 404)
            data = fpath.read_bytes()
            ctype = mimetypes.guess_type(str(fpath))[0] or "application/octet-stream"
            return data, 200, ctype
        except Exception as e:
            return _json_bytes({"success": False, "error": str(e)}, 400)

    if path == "/api/publish/queue/clear-done" and method == "POST":
        from console import publish_queue as pq

        n = pq.clear_done()
        return _json_bytes({"success": True, "cleared": n, "stats": pq.stats()})

    if path.startswith("/api/publish/queue/") and method in ("GET", "POST", "DELETE"):
        from console import publish_queue as pq

        rest = path[len("/api/publish/queue/") :].strip("/")
        parts = [p for p in rest.split("/") if p]
        if not parts:
            return _json_bytes({"success": False, "error": "缺少队列 id"}, 400)
        item_id = parts[0]
        action = parts[1] if len(parts) > 1 else ""

        if method == "GET":
            item = pq.get_item(item_id)
            if not item:
                return _json_bytes({"success": False, "error": "条目不存在"}, 404)
            return _json_bytes({"success": True, "item": item})

        if method == "DELETE" or action in ("delete", "remove"):
            remove_files = False
            if method == "DELETE":
                remove_files = (query.get("remove_files") or ["0"])[0] in ("1", "true", "yes")
            else:
                remove_files = bool(body.get("remove_files"))
            ok = pq.delete_item(item_id, remove_files=remove_files)
            if not ok:
                return _json_bytes({"success": False, "error": "条目不存在"}, 404)
            return _json_bytes({"success": True, "stats": pq.stats()})

        if action in ("run", "publish", "now"):
            result = pq.publish_now(item_id)
            code = 200 if result.get("success") else 400
            return _json_bytes(result, code)

        if action in ("update", "patch", "") or method == "POST":
            try:
                item = pq.update_item(item_id, body)
            except ValueError as e:
                return _json_bytes({"success": False, "error": str(e)}, 400)
            if not item:
                return _json_bytes({"success": False, "error": "条目不存在"}, 404)
            return _json_bytes({"success": True, "item": item, "stats": pq.stats()})

        return _json_bytes({"success": False, "error": f"未知操作: {action}"}, 404)

    # ——— X List 交易信号 ———
    if path == "/api/signals/config" and method == "GET":
        from signals.push import channels_summary
        from signals.schedule import describe_schedule, estimate_daily_runs
        from signals.store import get_config, load_state
        from signals.cycle_watcher import status as cycle_status
        from signals.watcher import status as watch_status
        from signals.store import resolve_signals_debugger_url

        st = load_state()
        cfg = get_config()
        return _json_bytes(
            {
                "success": True,
                "config": cfg,
                "debugger_url_effective": resolve_signals_debugger_url(cfg),
                "windows": (st.get("windows") or [])[:12],
                "card_count": len(st.get("cards") or []),
                "seen_count": len(st.get("seen_tweet_ids") or []),
                "pushed_count": len(st.get("pushed_tweet_ids") or []),
                "channels": channels_summary(),
                "schedule": describe_schedule(),
                "daily_estimate": estimate_daily_runs(
                    str(cfg.get("deep_sleep_mode") or "sleep")
                ),
                "watch": watch_status(),
                "cycle": cycle_status(),
            }
        )

    if path == "/api/signals/config" and method == "POST":
        from signals.cycle_watcher import set_cycle, start_cycle_watcher
        from signals.store import resolve_signals_debugger_url, save_config
        from signals.watcher import set_watch, start_watcher

        cfg = save_config(body if isinstance(body, dict) else {})
        # 同步监听开关
        if "watch_enabled" in (body or {}) or "deep_sleep_mode" in (body or {}):
            set_watch(
                bool(cfg.get("watch_enabled")),
                deep_sleep_mode=str(cfg.get("deep_sleep_mode") or "sleep"),
            )
        elif cfg.get("watch_enabled"):
            start_watcher(force=True)
        if "cycle_enabled" in (body or {}):
            set_cycle(bool(cfg.get("cycle_enabled")))
        elif cfg.get("cycle_enabled"):
            start_cycle_watcher(force=True)
        return _json_bytes(
            {
                "success": True,
                "config": cfg,
                "debugger_url_effective": resolve_signals_debugger_url(cfg),
            }
        )

    if path == "/api/signals/cycle" and method == "GET":
        from signals.cycle_watcher import status as cycle_status

        return _json_bytes({"success": True, "cycle": cycle_status()})

    if path == "/api/signals/cycle" and method == "POST":
        from signals.cycle_watcher import set_cycle, status as cycle_status

        enabled = bool(body.get("enabled", body.get("cycle_enabled", False)))
        st = set_cycle(enabled)
        return _json_bytes({"success": True, "cycle": st or cycle_status()})

    if path == "/api/signals/watch" and method == "GET":
        from signals.schedule import describe_schedule
        from signals.watcher import status as watch_status

        return _json_bytes(
            {
                "success": True,
                "watch": watch_status(),
                "schedule": describe_schedule(),
            }
        )

    if path == "/api/signals/watch" and method == "POST":
        from signals.watcher import set_watch, status as watch_status

        enabled = bool(body.get("enabled", body.get("watch_enabled", False)))
        mode = body.get("deep_sleep_mode")
        st = set_watch(enabled, deep_sleep_mode=mode)
        return _json_bytes({"success": True, "watch": st or watch_status()})

    if path == "/api/signals/channels" and method == "GET":
        from signals.push import channels_summary, load_channels_config

        return _json_bytes(
            {
                "success": True,
                "summary": channels_summary(),
                "config": load_channels_config(),
            }
        )

    if path == "/api/signals/push" and method == "POST":
        """手动把已存卡片增量/强制推送到 Cards API。"""
        from signals.push import push_cards_batch
        from signals.store import list_cards

        force = bool(body.get("force"))
        only_trade = body.get("only_trade")
        items = list_cards(
            list_id=str(body.get("list_id") or ""),
            only_trade=bool(only_trade) if only_trade is not None else False,
            limit=int(body.get("limit") or 80),
        )
        # 若指定 tweet_ids
        ids = body.get("tweet_ids") if isinstance(body.get("tweet_ids"), list) else None
        if ids:
            idset = {str(x) for x in ids}
            items = [c for c in items if str(c.get("tweet_id") or "") in idset]
        result = push_cards_batch(items, force=force)
        return _json_bytes({"success": True, **result})

    if path == "/api/signals/push-test" and method == "POST":
        """用测试数据验证频道映射 → Cards API（不写已推送库）。"""
        from signals.push import push_test_message

        result = push_test_message(
            handle=str(body.get("handle") or body.get("author") or ""),
            channel_id=str(body.get("channelId") or body.get("channel_id") or ""),
            channel_name=str(body.get("channelName") or body.get("channel_name") or ""),
            body=str(body.get("body") or ""),
            dry_run=bool(body.get("dry_run")),
            all_mapped=bool(body.get("all_mapped")),
        )
        if not result.get("success") and not result.get("dry_run"):
            try:
                from utils.stdio_encoding import safe_print, sanitize_for_console
                import json as _json

                safe_print("=" * 60)
                safe_print(" [signals-test] 测试推送失败")
                for it in result.get("items") or []:
                    if it.get("success"):
                        continue
                    safe_print(
                        f" · {it.get('channelName')} ({it.get('channelId')}) "
                        f"@{it.get('handle') or '-'}"
                    )
                    safe_print(
                        f"   原因: {sanitize_for_console(it.get('error_detail') or it.get('error') or '?')}"
                    )
                    req = it.get("request") or {}
                    safe_print(f"   URL: {req.get('url') or it.get('url') or '?'}")
                    safe_print(
                        f"   Headers: {sanitize_for_console(_json.dumps(req.get('headers') or {}, ensure_ascii=False))}"
                    )
                    safe_print(
                        f"   Body: {sanitize_for_console(_json.dumps(it.get('payload') or req.get('body') or {}, ensure_ascii=False, indent=2))}"
                    )
                    resp = it.get("response")
                    if resp:
                        safe_print(
                            f"   Response: {sanitize_for_console(_json.dumps(resp, ensure_ascii=False))}"
                        )
                safe_print("=" * 60)
            except Exception:
                pass
        code = 200 if result.get("success") else 400
        return _json_bytes({"success": bool(result.get("success")), **result}, code)

    if path == "/api/signals/cards" and method == "GET":
        from signals.push import enrich_card_channel, load_channels_config
        from signals.store import list_cards, load_state

        try:
            limit = int((query.get("limit") or ["80"])[0])
        except Exception:
            limit = 80
        only_trade = str((query.get("trade") or [""])[0]).lower() in ("1", "true", "yes")
        lid = (query.get("list_id") or [""])[0]
        cfg_ch = load_channels_config()
        items = [
            enrich_card_channel(c, cfg_ch)
            for c in list_cards(list_id=lid, only_trade=only_trade, limit=limit)
        ]
        st = load_state()
        return _json_bytes(
            {
                "success": True,
                "items": items,
                "windows": (st.get("windows") or [])[:8],
                "config": st.get("config") or {},
                "pushed_count": len(st.get("pushed_tweet_ids") or []),
                "channels": {
                    "mappings": [
                        {
                            "handle": k,
                            "channelId": (v or {}).get("channelId"),
                            "channelName": (v or {}).get("channelName"),
                        }
                        for k, v in (cfg_ch.get("channels") or {}).items()
                        if isinstance(v, dict)
                    ]
                },
            }
        )

    if path == "/api/signals/run" and method == "POST":
        job_id = uuid.uuid4().hex[:12]

        from signals.control import RunControl, register, unregister

        ctl = register(job_id, RunControl(job_id))
        log_buf: List[str] = []

        def _progress(msg: str) -> None:
            text = str(msg or "")[:800]
            try:
                from utils.stdio_encoding import safe_print, sanitize_for_console

                safe_print(f" [signals] {sanitize_for_console(text)}")
            except Exception:
                print(f"[signals] {text}", flush=True)
            log_buf.append(text)
            if len(log_buf) > 400:
                del log_buf[:120]
            st = ctl.status()
            _set_job(
                job_id,
                status="paused" if st == "paused" else "running",
                message=text[:300],
                logs=list(log_buf[-120:]),
                control_status=st,
            )

        def _worker() -> None:
            try:
                from utils.stdio_encoding import safe_print

                safe_print("=" * 60)
                safe_print(" [signals] 列表交易信号 · 开始")
                safe_print("=" * 60)
            except Exception:
                pass
            _set_job(
                job_id,
                status="running",
                type="signals_list",
                message="开始抓取列表…",
                logs=[],
                control_status="running",
                started_at=datetime.now().isoformat(timespec="seconds"),
            )
            try:
                from signals.pipeline import run_list_signal_pipeline

                push_flag = body.get("push")
                if push_flag is None:
                    push_flag = body.get("push_enabled")
                result = run_list_signal_pipeline(
                    list_id=str(body.get("list_id") or body.get("list_url") or ""),
                    cutoff_hours=body.get("cutoff_hours"),
                    max_tweets=body.get("max_tweets"),
                    ignore_windows=bool(body.get("ignore_windows")),
                    skip_non_trade=body.get("skip_non_trade"),
                    reparse_seen=bool(body.get("reparse_seen")),
                    push=None if push_flag is None else bool(push_flag),
                    force_push=bool(body.get("force_push")),
                    progress=_progress,
                    control=ctl,
                )
                aborted = bool(result.get("aborted"))
                if aborted:
                    final_status = "cancelled"
                elif result.get("success"):
                    final_status = "done"
                else:
                    final_status = "error"
                _set_job(
                    job_id,
                    status=final_status,
                    message=result.get("message") or result.get("error") or "完成",
                    logs=list(log_buf[-120:]),
                    control_status=ctl.status(),
                    result={
                        k: result.get(k)
                        for k in (
                            "list_id",
                            "list_url",
                            "fetched",
                            "candidates",
                            "parsed",
                            "skipped",
                            "window",
                            "cutoff_hours",
                            "floor",
                            "push",
                            "message",
                            "error",
                            "aborted",
                            "item_logs",
                        )
                        if k in result
                    },
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                )
                try:
                    from utils.stdio_encoding import safe_print

                    safe_print("-" * 60)
                    safe_print(
                        f" [signals] 结束 · {result.get('message') or result.get('error') or final_status}"
                    )
                    safe_print("=" * 60)
                except Exception:
                    pass
            except Exception as e:
                _set_job(
                    job_id,
                    status="error",
                    message=str(e),
                    logs=list(log_buf[-120:]),
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                )
                try:
                    from utils.stdio_encoding import safe_print

                    safe_print(f" [signals] 失败: {e}")
                    safe_print("=" * 60)
                except Exception:
                    pass
            finally:
                unregister(job_id)

        _set_job(
            job_id,
            status="queued",
            type="signals_list",
            message="排队中…",
            logs=[],
            control_status="running",
        )
        threading.Thread(target=_worker, daemon=True).start()
        return _json_bytes({"success": True, "job_id": job_id})

    if path == "/api/signals/user/run" and method == "POST":
        job_id = uuid.uuid4().hex[:12]

        from signals.control import RunControl, register, unregister

        ctl = register(job_id, RunControl(job_id))
        log_buf: List[str] = []

        def _progress_u(msg: str) -> None:
            text = str(msg or "")[:800]
            try:
                from utils.stdio_encoding import safe_print, sanitize_for_console

                safe_print(f" [signals-user] {sanitize_for_console(text)}")
            except Exception:
                print(f"[signals-user] {text}", flush=True)
            log_buf.append(text)
            if len(log_buf) > 400:
                del log_buf[:120]
            st = ctl.status()
            _set_job(
                job_id,
                status="paused" if st == "paused" else "running",
                message=text[:300],
                logs=list(log_buf[-120:]),
                control_status=st,
            )

        def _worker_user() -> None:
            try:
                from utils.stdio_encoding import safe_print

                safe_print("=" * 60)
                safe_print(" [signals-user] 博主回溯 · 开始")
                safe_print("=" * 60)
            except Exception:
                pass
            _set_job(
                job_id,
                status="running",
                type="signals_user",
                message="开始抓取博主时间线…",
                logs=[],
                control_status="running",
                started_at=datetime.now().isoformat(timespec="seconds"),
            )
            try:
                from signals.pipeline import run_user_signal_pipeline

                push_flag = body.get("push")
                if push_flag is None:
                    push_flag = body.get("push_enabled")
                result = run_user_signal_pipeline(
                    profile_url=str(
                        body.get("profile_url")
                        or body.get("user_url")
                        or body.get("user_handle")
                        or ""
                    ),
                    user_handle=str(body.get("user_handle") or ""),
                    weeks=body.get("weeks"),
                    max_tweets=body.get("max_tweets"),
                    skip_non_trade=body.get("skip_non_trade"),
                    reparse_seen=bool(body.get("reparse_seen")),
                    push=None if push_flag is None else bool(push_flag),
                    force_push=bool(body.get("force_push")),
                    progress=_progress_u,
                    control=ctl,
                )
                aborted = bool(result.get("aborted"))
                if aborted:
                    final_status = "cancelled"
                elif result.get("success"):
                    final_status = "done"
                else:
                    final_status = "error"
                _set_job(
                    job_id,
                    status=final_status,
                    message=result.get("message") or result.get("error") or "完成",
                    logs=list(log_buf[-120:]),
                    control_status=ctl.status(),
                    result={
                        k: result.get(k)
                        for k in (
                            "handle",
                            "profile_url",
                            "scope_id",
                            "weeks",
                            "since",
                            "fetched",
                            "candidates",
                            "parsed",
                            "skipped",
                            "trade_count",
                            "reused_cache",
                            "window",
                            "push",
                            "message",
                            "error",
                            "aborted",
                            "item_logs",
                        )
                        if k in result
                    },
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                )
            except Exception as e:
                _set_job(
                    job_id,
                    status="error",
                    message=str(e),
                    logs=list(log_buf[-120:]),
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                )
            finally:
                unregister(job_id)

        _set_job(
            job_id,
            status="queued",
            type="signals_user",
            message="排队中…",
            logs=[],
            control_status="running",
        )
        threading.Thread(target=_worker_user, daemon=True).start()
        return _json_bytes({"success": True, "job_id": job_id})

    if path == "/api/signals/user/clear-cache" and method == "POST":
        from signals.store import clear_user_cache, parse_user_handle

        raw = str(
            body.get("profile_url")
            or body.get("user_url")
            or body.get("user_handle")
            or ""
        ).strip()
        handle = parse_user_handle(raw) or str(body.get("user_handle") or "").strip().lstrip("@")
        result = clear_user_cache(handle)
        if not result.get("success"):
            return _json_bytes(result, 400)
        return _json_bytes(
            {
                **result,
                "message": f"已清除 @{result.get('handle')} 缓存 {result.get('removed_cards', 0)} 条",
            }
        )

    if path == "/api/signals/control" and method == "POST":
        from signals.control import control_action, get as get_sig_ctl

        action = str(body.get("action") or "").strip().lower()
        job_id = str(body.get("job_id") or "").strip()
        out = control_action(job_id, action)
        if not out.get("success"):
            return _json_bytes(out, 400)
        jid = str(out.get("job_id") or job_id)
        ctl = get_sig_ctl(jid)
        st = (ctl.status() if ctl else out.get("status")) or ""
        if jid:
            if st == "paused":
                _set_job(jid, status="paused", control_status="paused", message="已暂停")
            elif action in ("resume", "continue"):
                _set_job(jid, status="running", control_status="running", message="已继续")
            elif action in ("stop", "cancel", "abort"):
                _set_job(jid, control_status="stopped", message="正在终止…")
        return _json_bytes(out)

    if path == "/api/signals/media" and method == "GET":
        import mimetypes

        from signals.store import resolve_media

        rel = (query.get("rel") or [""])[0].strip()
        try:
            fpath = resolve_media(rel)
            if not fpath.is_file():
                return _json_bytes({"success": False, "error": "文件不存在"}, 404)
            data = fpath.read_bytes()
            ctype = mimetypes.guess_type(str(fpath))[0] or "application/octet-stream"
            return data, 200, ctype
        except Exception as e:
            return _json_bytes({"success": False, "error": str(e)}, 400)

    if path == "/api/signals/cards/ws-config" and method == "GET":
        from signals.cards_api import ws_config

        return _json_bytes({"success": True, **ws_config()})

    if path == "/api/signals/cards/remote" and method == "GET":
        from signals.cards_api import fetch_cards
        from signals.push import resolve_channel

        try:
            days = int((query.get("days") or ["7"])[0])
        except Exception:
            days = 7
        channel_id = (query.get("channelId") or query.get("channel_id") or [""])[0]
        symbol = (query.get("symbol") or query.get("coin") or [""])[0]
        sources = (query.get("sources") or query.get("source") or ["x"])[0]
        try:
            limit = int((query.get("limit") or ["200"])[0])
        except Exception:
            limit = 200
        handle = (query.get("handle") or [""])[0]
        if handle and not channel_id:
            ch = resolve_channel(str(handle))
            channel_id = ch.get("channelId") or ""
        result = fetch_cards(
            days=days,
            channel_id=str(channel_id or ""),
            symbol=str(symbol or ""),
            sources=str(sources or "x"),
            limit=limit,
        )
        if not result.get("success"):
            code = 502
            payload = {
                "success": False,
                **result,
                "message": result.get("hint") or result.get("error") or "Cards API 不可用",
            }
            return _json_bytes(payload, code)
        return _json_bytes({"success": True, **result})

    if path == "/api/signals/cards/validate" and method == "POST":
        from signals.cards_api import start_validate
        from signals.push import resolve_channel

        try:
            days = int(body.get("days") or 7)
        except Exception:
            days = 7
        channel_id = str(body.get("channelId") or body.get("channel_id") or "")
        symbol = str(body.get("symbol") or body.get("coin") or "")
        sources = str(body.get("sources") or body.get("source") or "x")
        handle = str(body.get("handle") or "")
        if handle and not channel_id:
            ch = resolve_channel(handle)
            channel_id = ch.get("channelId") or ""
        card_ids = body.get("cardIds") if isinstance(body.get("cardIds"), list) else None
        try:
            limit = int(body.get("limit") or 200)
        except Exception:
            limit = 200
        result = start_validate(
            days=days,
            channel_id=channel_id,
            symbol=symbol,
            sources=sources,
            limit=limit,
            card_ids=card_ids,
        )
        code = 202 if result.get("success") else 400
        return _json_bytes(result, code)

    if path.startswith("/api/signals/cards/validate/") and method == "GET":
        from signals.cards_api import poll_validate

        job_id = path.split("/api/signals/cards/validate/", 1)[-1].strip("/")
        result = poll_validate(job_id)
        code = 200 if result.get("success") else 404
        return _json_bytes(result, code)

    # ——— 推文卡片（粘贴链接解析） ———
    if path == "/api/tweet-cards" and method == "GET":
        from tweet_cards.pipeline import list_tweet_cards

        try:
            limit = int((query.get("limit") or ["40"])[0])
        except Exception:
            limit = 40
        keyword = (query.get("keyword") or [""])[0]
        return _json_bytes(list_tweet_cards(limit=limit, keyword=keyword))

    if path == "/api/tweet-cards/ingest" and method == "POST":
        job_id = uuid.uuid4().hex[:12]
        raw = str(body.get("text") or body.get("url") or body.get("input") or "")

        def _progress(msg: str) -> None:
            _set_job(job_id, message=str(msg or "")[:300])

        def _worker() -> None:
            _set_job(
                job_id,
                status="running",
                type="tweet_cards_ingest",
                message="开始解析推文…",
                started_at=datetime.now().isoformat(timespec="seconds"),
            )
            try:
                from tweet_cards.pipeline import ingest_tweet_input

                result = ingest_tweet_input(raw, progress=_progress)
                _set_job(
                    job_id,
                    status="done" if result.get("success") else "error",
                    message=result.get("message") or result.get("error") or "完成",
                    result={
                        k: result.get(k)
                        for k in (
                            "ok_count",
                            "fail_count",
                            "failed",
                            "cards",
                            "stats",
                            "message",
                            "error",
                        )
                        if k in result
                    },
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                )
            except Exception as e:
                _set_job(
                    job_id,
                    status="error",
                    message=str(e),
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                )

        _set_job(job_id, status="queued", type="tweet_cards_ingest", message="排队中…")
        threading.Thread(target=_worker, daemon=True).start()
        return _json_bytes({"success": True, "job_id": job_id})

    if path.startswith("/api/tweet-cards/") and method == "DELETE":
        from tweet_cards.store import delete_card

        tid = path[len("/api/tweet-cards/") :].strip("/")
        if not tid:
            return _json_bytes({"success": False, "error": "缺少 tweet_id"}, 400)
        ok = delete_card(tid)
        return _json_bytes(
            {"success": ok, "error": None if ok else "未找到"},
            200 if ok else 404,
        )

    return _json_bytes({"success": False, "error": f"未知接口: {path}"}, 404)


class ConsoleHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[console] {self.address_string()} - {fmt % args}")

    def _send(self, payload: bytes, status: int, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            body, status, ctype = handle_api("GET", parsed.path, parse_qs(parsed.query), {})
            self._send(body, status, ctype)
            return
        if parsed.path in ("/", "/index.html"):
            index = STATIC_DIR / "index.html"
            data = index.read_bytes()
            self._send(data, 200, "text/html; charset=utf-8")
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            try:
                req_body = _read_json_body(self)
                body, status, ctype = handle_api(
                    "POST", parsed.path, parse_qs(parsed.query), req_body
                )
                self._send(body, status, ctype)
            except Exception as e:
                traceback.print_exc()
                self._send(*_json_bytes({"success": False, "error": str(e)}, 500))
            return
        self._send(*_json_bytes({"success": False, "error": "Not Found"}, 404))

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            body, status, ctype = handle_api("DELETE", parsed.path, parse_qs(parsed.query), {})
            self._send(body, status, ctype)
            return
        self._send(*_json_bytes({"success": False, "error": "Not Found"}, 404))


def _pids_listening_on_port(port: int) -> List[int]:
    """返回正在监听指定端口的进程 PID（排除当前进程）。"""
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return []
    my_pid = os.getpid()
    pids: List[int] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid = int(line)
        except ValueError:
            continue
        if pid != my_pid and pid not in pids:
            pids.append(pid)
    return pids


def _free_port(port: int, log=print) -> None:
    """启动前释放端口：先 SIGTERM，仍占用则 SIGKILL。"""
    pids = _pids_listening_on_port(port)
    if not pids:
        return
    log(f" 端口 {port} 已被占用，正在结束进程: {', '.join(map(str, pids))}")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError as e:
            log(f" 无法结束进程 {pid}: {e}")
    deadline = time.time() + 2.0
    while time.time() < deadline:
        alive = _pids_listening_on_port(port)
        if not alive:
            log(f" 端口 {port} 已释放")
            return
        time.sleep(0.15)
    for pid in _pids_listening_on_port(port):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    time.sleep(0.2)
    still = _pids_listening_on_port(port)
    if still:
        raise OSError(f"端口 {port} 仍被占用: {', '.join(map(str, still))}")
    log(f" 端口 {port} 已强制释放")


def run_server(host: str = "127.0.0.1", port: int = 8787, open_browser: bool = False) -> None:
    from utils.stdio_encoding import ensure_utf8_stdio, safe_print

    ensure_utf8_stdio()
    if not os.environ.get("CARDS_API_KEY", "").strip():
        try:
            from signals.push import resolve_cards_api_key

            os.environ["CARDS_API_KEY"] = resolve_cards_api_key()
        except Exception:
            pass
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    restored = _load_crawl_tasks()
    queue_n = 0
    try:
        from console import publish_queue as pq

        queue_n = pq.init(
            PROJECT_ROOT / "output" / "publish_queue.json",
            cache_root=PROJECT_ROOT / "output" / "publish_cache",
        )
    except Exception as e:
        safe_print(f" 发布队列初始化跳过: {e}")
    try:
        from corpus.db import init_db as init_corpus_db

        init_corpus_db()
    except Exception as e:
        safe_print(f" 语料库初始化跳过: {e}")
    watch_on = False
    cycle_on = False
    try:
        from signals.cycle_watcher import start_cycle_watcher
        from signals.store import get_config as _sig_cfg
        from signals.watcher import start_watcher

        _sc = _sig_cfg() or {}
        watch_on = bool(_sc.get("watch_enabled"))
        cycle_on = bool(_sc.get("cycle_enabled"))
        if watch_on:
            start_watcher(force=True)
        if cycle_on:
            start_cycle_watcher(force=True)
    except Exception as e:
        safe_print(f" 列表信号监听初始化跳过: {e}")
    _free_port(port, log=safe_print)
    server = ThreadingHTTPServer((host, port), ConsoleHandler)
    url = f"http://{host}:{port}/"
    safe_print("=" * 60)
    safe_print(" TrendRadar Console")
    safe_print("=" * 60)
    safe_print(f" 地址: {url}")
    safe_print(" 功能: 资讯获取 / 列表信号(分时CDP) / 语料库 / Prompt 创作 / CDP 发布")
    try:
        from utils.crawl_cdp import resolve_crawl_debugger_url

        cdp_host = resolve_crawl_debugger_url()
    except Exception:
        cdp_host = "127.0.0.1:9223"
    safe_print(f" 抓取 CDP: {cdp_host}（可改 config crawler.x_cdp.debugger_url 或 CDP_DEBUGGER_URL）")
    safe_print(" 抓取日志: 资讯「开始抓取」→ [Crawl]；列表信号 → [signals]（含发帖人/正文/时间/是否交易信号）")
    if restored:
        active = sum(1 for t in _CRAWL_TASKS.values() if t.get("enabled"))
        safe_print(f" 周期任务库: 已恢复 {restored} 条（运行中 {active}）")
    if queue_n:
        safe_print(f" 发布队列: 已恢复 {queue_n} 条（到点自动发）")
    if watch_on:
        safe_print(" 列表信号: 分时自动监听已开启（北京时间阶梯频率）")
    if cycle_on:
        safe_print(" 列表信号: 周期抓取已开启（5–15 分钟随机间隔，首次最多 8h）")
    safe_print(" 按 Ctrl+C 停止")
    safe_print("=" * 60)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        safe_print("")
        safe_print("=" * 60)
        safe_print(" 已停止控制台服务")
        safe_print("=" * 60)
    finally:
        server.server_close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="TrendRadar 一体化控制台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--browser", action="store_true", help="启动后自动打开浏览器")
    parser.add_argument("--no-browser", action="store_true", help="（已默认不打开，可忽略）")
    args = parser.parse_args()
    open_browser = bool(args.browser) and not args.no_browser
    run_server(host=args.host, port=args.port, open_browser=open_browser)


if __name__ == "__main__":
    main()
