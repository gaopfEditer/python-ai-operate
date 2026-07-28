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
import threading
import time
import traceback
import uuid
import webbrowser
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATE_PATH = PROJECT_ROOT / "output" / "trendradar_posts_state.json"
ARTICLES_DIR = PROJECT_ROOT / "output" / "articles"

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


def _load_posts_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"version": 1, "generated_at": "", "platform_labels": {}, "posts": {}}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        return {"error": str(e), "posts": {}}


def _persist_crawl_tasks() -> None:
    TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _CRAWL_TASKS_LOCK:
        dump = []
        for t in _CRAWL_TASKS.values():
            dump.append(
                {
                    "id": t.get("id"),
                    "keyword": t.get("keyword"),
                    "interval_min": t.get("interval_min", 30),
                    "jitter_min": t.get("jitter_min", 10),
                    "expand": bool(t.get("expand", True)),
                    "platforms": t.get("platforms") or ["x-cdp", "reddit", "telegram"],
                    "enabled": bool(t.get("enabled", True)),
                    "created_at": t.get("created_at"),
                    "last_run_at": t.get("last_run_at"),
                    "next_run_at": t.get("next_run_at"),
                    "last_status": t.get("last_status"),
                    "last_message": t.get("last_message"),
                    "run_count": t.get("run_count", 0),
                    "expansion": t.get("expansion"),
                }
            )
    with open(TASKS_PATH, "w", encoding="utf-8") as f:
        json.dump({"tasks": dump}, f, ensure_ascii=False, indent=2)


def _next_interval_seconds(interval_min: int = 30, jitter_min: int = 10) -> int:
    base = max(5, int(interval_min or 30))
    jitter = max(0, int(jitter_min or 0))
    delta = random.randint(-jitter, jitter) if jitter else 0
    minutes = max(5, base + delta)
    return minutes * 60


def _public_task_view(task: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": task.get("id"),
        "keyword": task.get("keyword"),
        "interval_min": task.get("interval_min", 30),
        "jitter_min": task.get("jitter_min", 10),
        "expand": bool(task.get("expand", True)),
        "platforms": task.get("platforms") or [],
        "enabled": bool(task.get("enabled", True)),
        "created_at": task.get("created_at"),
        "last_run_at": task.get("last_run_at"),
        "next_run_at": task.get("next_run_at"),
        "last_status": task.get("last_status"),
        "last_message": task.get("last_message"),
        "run_count": task.get("run_count", 0),
        "expansion": task.get("expansion"),
        "running": bool(task.get("_running")),
        "last_job_id": task.get("last_job_id"),
    }


def _flatten_posts(state: Dict[str, Any], keyword: str = "", platform: str = "") -> List[Dict[str, Any]]:
    posts = state.get("posts") or {}
    labels = state.get("platform_labels") or {}
    kw = (keyword or "").strip().lower()
    plat = (platform or "").strip()
    rows: List[Dict[str, Any]] = []

    for platform_id, bucket in posts.items():
        if plat and str(platform_id) != plat:
            continue
        if not isinstance(bucket, dict):
            continue
        for key, entry in bucket.items():
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title") or "")
            content = str(entry.get("content") or entry.get("raw") or "")
            href = str(entry.get("href") or key)
            hay = f"{title} {content} {href}".lower()
            if kw and kw not in hay:
                continue
            rows.append(
                {
                    "platform_id": str(platform_id),
                    "platform_name": labels.get(str(platform_id), str(platform_id)),
                    "key": key,
                    "href": href,
                    "title": title,
                    "raw": entry.get("raw") or "",
                    "content": entry.get("content") or "",
                    "author": entry.get("author") or "",
                    "fetched_at": entry.get("fetched_at") or "",
                    "first_fetched_at": entry.get("first_fetched_at") or entry.get("fetched_at") or "",
                    "star": entry.get("star", 0),
                    "isUseful": entry.get("isUseful", False),
                    "rank": entry.get("rank"),
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
        msg = f"抓取完成，匹配 {len(rows)} 条"
        if extra_summary:
            msg += (
                f"（Reddit +{extra_summary.get('reddit', 0)} / "
                f"Telegram +{extra_summary.get('telegram', 0)}）"
            )
        safe_print("-" * 60)
        safe_print(f" [Crawl] {msg}")
        if rows:
            for i, row in enumerate(rows[:5], 1):
                title = sanitize_for_console((row.get("title") or "")[:80])
                safe_print(f"  {i}. [{row.get('platform_id')}] {title}")
            if len(rows) > 5:
                safe_print(f"  ... 另有 {len(rows) - 5} 条，请在页面「历史缓存」查看")
        safe_print("=" * 60)
        _set_job(
            job_id,
            status="done",
            message=msg,
            finished_at=datetime.now().isoformat(),
            matched_count=len(rows),
            keyword=keyword,
            extra=extra_summary,
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
            interval_min = int(task.get("interval_min") or 30)
            jitter_min = int(task.get("jitter_min") or 10)
            keyword = str(task.get("keyword") or "")
            expand = bool(task.get("expand", True))
            platforms = list(task.get("platforms") or [])

        wait_sec = _next_interval_seconds(interval_min, jitter_min)
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


def _start_crawl_task(
    keyword: str,
    interval_min: int = 30,
    jitter_min: int = 10,
    expand: bool = True,
    platforms: Optional[List[str]] = None,
    run_now: bool = True,
) -> Dict[str, Any]:
    task_id = uuid.uuid4().hex[:10]
    stop_event = threading.Event()
    plats = platforms or ["x-cdp", "reddit", "telegram"]
    task = {
        "id": task_id,
        "keyword": keyword,
        "interval_min": max(5, int(interval_min or 30)),
        "jitter_min": max(0, int(jitter_min or 0)),
        "expand": bool(expand),
        "platforms": plats,
        "enabled": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
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

    if run_now:
        job_id = uuid.uuid4().hex[:12]
        _set_job(job_id, status="queued", message="周期任务首次执行", keyword=keyword, task_id=task_id)

        def _first():
            with _CRAWL_TASKS_LOCK:
                t = _CRAWL_TASKS.get(task_id)
                if t:
                    t["_running"] = True
            try:
                _run_crawl_job(
                    job_id,
                    keyword=keyword,
                    expand=expand,
                    platforms=plats,
                    task_id=task_id,
                )
            finally:
                with _CRAWL_TASKS_LOCK:
                    t = _CRAWL_TASKS.get(task_id)
                    if t:
                        t["_running"] = False

        threading.Thread(target=_first, daemon=True).start()
        task["last_job_id"] = job_id

    th = threading.Thread(target=_schedule_loop, args=(task_id,), daemon=True)
    th.start()
    with _CRAWL_TASKS_LOCK:
        task["_thread"] = th
    return _public_task_view(task)


def _stop_crawl_task(task_id: str) -> bool:
    with _CRAWL_TASKS_LOCK:
        task = _CRAWL_TASKS.get(task_id)
        if not task:
            return False
        task["enabled"] = False
        task["last_message"] = "已停止"
        stop_event = task.get("_stop")
        if isinstance(stop_event, threading.Event):
            stop_event.set()
    _persist_crawl_tasks()
    return True


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
        import sys

        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from crawler.index import CONFIG

        platforms = CONFIG.get("PLATFORMS") or []
        return _json_bytes({"success": True, "platforms": platforms})

    if path == "/api/platforms/publish" and method == "GET":
        import sys

        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from public.index import list_platforms

        return _json_bytes({"success": True, "platforms": list_platforms()})

    if path == "/api/posts" and method == "GET":
        keyword = (query.get("keyword") or [""])[0]
        platform = (query.get("platform") or [""])[0]
        try:
            limit = int((query.get("limit") or ["100"])[0])
        except Exception:
            limit = 100
        state = _load_posts_state()
        rows = _flatten_posts(state, keyword=keyword, platform=platform)
        return _json_bytes(
            {
                "success": True,
                "generated_at": state.get("generated_at") or "",
                "total": len(rows),
                "items": rows[: max(1, limit)],
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
            task = _start_crawl_task(
                keyword=keyword,
                interval_min=interval_min,
                jitter_min=jitter_min,
                expand=expand,
                platforms=platforms,
                run_now=bool(body.get("run_now", True)),
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
        with _CRAWL_TASKS_LOCK:
            items = [_public_task_view(t) for t in _CRAWL_TASKS.values()]
        items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
        return _json_bytes({"success": True, "items": items})

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
        task = _start_crawl_task(
            keyword=keyword,
            interval_min=interval_min,
            jitter_min=jitter_min,
            expand=bool(body.get("expand", True)),
            platforms=platforms,
            run_now=bool(body.get("run_now", True)),
        )
        return _json_bytes({"success": True, "task": task})

    if path.startswith("/api/crawl/tasks/") and method in ("DELETE", "POST"):
        task_id = path.split("/api/crawl/tasks/", 1)[1].strip("/").split("/")[0]
        action = ""
        if method == "POST":
            action = str(body.get("action") or "").strip().lower()
            if path.rstrip("/").endswith("/stop"):
                action = "stop"
        if method == "DELETE" or action == "stop":
            ok = _stop_crawl_task(task_id)
            if not ok:
                return _json_bytes({"success": False, "error": "任务不存在"}, 404)
            return _json_bytes({"success": True, "id": task_id, "stopped": True})
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

        import sys

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
        content = str(body.get("content") or "").strip()
        file_path = str(body.get("file") or "").strip()
        tags = str(body.get("tags") or "").strip() or None
        platforms = body.get("platforms")
        if isinstance(platforms, str):
            platforms = [p.strip() for p in platforms.split(",") if p.strip()]
        if not isinstance(platforms, list):
            platforms = None

        if file_path and (not title or not content):
            art = _read_article(file_path)
            if not art.get("success"):
                return _json_bytes(art, 400)
            title = title or art["title"]
            content = content or art["content"]

        if not title or not content:
            return _json_bytes({"success": False, "error": "请提供标题和正文，或选择文章文件"}, 400)

        use_cdp = bool(body.get("use_cdp", True))
        debugger_url = str(body.get("debugger_url") or "").strip()

        import sys

        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from public.index import publish_content

        result = publish_content(
            content={"title": title, "content": content},
            platform_ids=platforms,
            tags=tags,
            use_cdp=use_cdp,
            debugger_url=debugger_url or None,
        )
        return _json_bytes(result)

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
            req_body = _read_json_body(self)
            body, status, ctype = handle_api("POST", parsed.path, parse_qs(parsed.query), req_body)
            self._send(body, status, ctype)
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


def run_server(host: str = "127.0.0.1", port: int = 8787, open_browser: bool = True) -> None:
    from utils.stdio_encoding import ensure_utf8_stdio, safe_print

    ensure_utf8_stdio()
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    _free_port(port, log=safe_print)
    server = ThreadingHTTPServer((host, port), ConsoleHandler)
    url = f"http://{host}:{port}/"
    safe_print("=" * 60)
    safe_print(" TrendRadar Console")
    safe_print("=" * 60)
    safe_print(f" 地址: {url}")
    safe_print(" 功能: 资讯获取 / 历史缓存 / Prompt 创作 / CDP 发布")
    safe_print(" 抓取日志: 页面点「开始抓取」后，本窗口会打印 [Crawl] 进度")
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
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
