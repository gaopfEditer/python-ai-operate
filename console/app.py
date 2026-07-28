# coding=utf-8
"""
TrendRadar 控制台 HTTP 服务
- 静态页：资讯获取 / 历史缓存 / Prompt 创作 / CDP 发布
- 复用 crawler / create / public 现有能力
"""

from __future__ import annotations

import json
import os
import re
import threading
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


def _run_crawl_job(job_id: str, keyword: str = "") -> None:
    from utils.stdio_encoding import ensure_utf8_stdio, sanitize_for_console, safe_print

    ensure_utf8_stdio()
    _set_job(
        job_id,
        status="running",
        message="正在抓取资讯…",
        started_at=datetime.now().isoformat(),
    )
    prev_kw = os.environ.get("X_SEARCH_KEYWORDS")
    try:
        import sys

        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))

        safe_print("=" * 60)
        safe_print(" [Crawl] 开始抓取")
        safe_print("=" * 60)
        if keyword:
            os.environ["X_SEARCH_KEYWORDS"] = keyword
            safe_print(f" 关键词: {keyword}")
        elif "X_SEARCH_KEYWORDS" in os.environ:
            del os.environ["X_SEARCH_KEYWORDS"]
            safe_print(" 关键词: (使用 config.yaml 默认)")
        else:
            safe_print(" 关键词: (使用 config.yaml 默认)")
        safe_print(" 平台: 按 config.platforms + X CDP 搜索工作流")
        safe_print("-" * 60)

        from crawler.index import main as crawl_main

        crawl_main()
        state = _load_posts_state()
        rows = _flatten_posts(state, keyword=keyword)
        msg = f"抓取完成，匹配 {len(rows)} 条" if keyword else f"抓取完成，缓存约 {len(rows)} 条可见"
        safe_print("-" * 60)
        safe_print(f" [Crawl] {msg}")
        if rows:
            for i, row in enumerate(rows[:5], 1):
                title = sanitize_for_console((row.get("title") or "")[:80])
                safe_print(f"  {i}. {title}")
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
        )
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
    finally:
        if prev_kw is None:
            os.environ.pop("X_SEARCH_KEYWORDS", None)
        else:
            os.environ["X_SEARCH_KEYWORDS"] = prev_kw



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
        job_id = uuid.uuid4().hex[:12]
        _set_job(job_id, status="queued", message="任务已排队", keyword=keyword)
        t = threading.Thread(target=_run_crawl_job, args=(job_id, keyword), daemon=True)
        t.start()
        return _json_bytes({"success": True, "job_id": job_id})

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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
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


def run_server(host: str = "127.0.0.1", port: int = 8787, open_browser: bool = True) -> None:
    from utils.stdio_encoding import ensure_utf8_stdio, safe_print

    ensure_utf8_stdio()
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
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
