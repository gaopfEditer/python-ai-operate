# coding=utf-8
"""
AllNews Monitor HTTP 控制台
对标 console/app.py：抓取 / 候选 / 自动&手动归档 / 素材库
"""

from __future__ import annotations

import json
import os
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

from allnews_mornitor import archive, store
from allnews_mornitor.pipeline import run_crawl
from allnews_mornitor.platforms import loader  # noqa: F401
from allnews_mornitor.platforms import list_platforms, update_defaults, update_platform_config
from allnews_mornitor.scheduler import start_scheduler

STATIC_DIR = Path(__file__).resolve().parent / "static"
_JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


def _json_bytes(data: Any, status: int = 200) -> tuple:
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


def _set_job(job_id: str, **kwargs) -> None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id, {"id": job_id})
        job.update(kwargs)
        _JOBS[job_id] = job


def _get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def _run_job(job_id: str, platforms: Optional[List[str]]) -> None:
    _set_job(job_id, status="running", message="CDP 抓取中…", started_at=datetime.now().isoformat())
    try:
        result = run_crawl(platforms)
        msg = (
            f"完成：抓取 {result.get('total_fetched', 0)}，"
            f"入候选 {result.get('candidates', 0)}，"
            f"门槛过滤 {result.get('rejected', 0)}，"
            f"自动归档 {result.get('archived', 0)}"
        )
        if result.get("errors"):
            msg += f"；失败平台 {list(result['errors'].keys())}"
        _set_job(
            job_id,
            status="done",
            message=msg,
            result=result,
            finished_at=datetime.now().isoformat(),
        )
    except Exception as e:
        _set_job(
            job_id,
            status="error",
            message=str(e),
            detail=traceback.format_exc(),
            finished_at=datetime.now().isoformat(),
        )


def handle_api(method: str, path: str, query: Dict[str, List[str]], body: Dict[str, Any]):
    path = path.rstrip("/") or path

    if path == "/api/health":
        return _json_bytes(
            {
                "ok": True,
                "service": "AllNews Monitor",
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "data_dir": str(store.DATA_DIR),
            }
        )

    if path == "/api/platforms" and method == "GET":
        return _json_bytes(
            {
                "success": True,
                "platforms": list_platforms(),
                "defaults": (store.load_config().get("defaults") or {}),
            }
        )

    if path == "/api/platforms" and method == "POST":
        pid = str(body.get("id") or body.get("platform") or "").strip()
        if not pid:
            return _json_bytes({"success": False, "error": "缺少平台 id"}, 400)
        try:
            updated = update_platform_config(pid, body)
            return _json_bytes({"success": True, "platform": updated})
        except Exception as e:
            return _json_bytes({"success": False, "error": str(e)}, 400)

    if path == "/api/config" and method == "GET":
        cfg = store.load_config()
        return _json_bytes(
            {
                "success": True,
                "defaults": cfg.get("defaults"),
                "archive": cfg.get("archive"),
                "cdp": cfg.get("cdp"),
                "platforms": cfg.get("platforms"),
            }
        )

    if path == "/api/config/defaults" and method == "POST":
        try:
            defaults = update_defaults(body)
            return _json_bytes({"success": True, "defaults": defaults})
        except Exception as e:
            return _json_bytes({"success": False, "error": str(e)}, 400)

    if path == "/api/batch/last" and method == "GET":
        batch = store.load_last_batch()
        platform = (query.get("platform") or [""])[0].strip()
        items = list(batch.get("items") or [])
        if platform:
            items = [x for x in items if str(x.get("platform")) == platform]
        only_cand = (query.get("candidates_only") or [""])[0].strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if only_cand:
            items = [x for x in items if x.get("in_candidates")]
        try:
            limit = int((query.get("limit") or ["200"])[0])
        except Exception:
            limit = 200
        return _json_bytes(
            {
                "success": True,
                "meta": batch.get("meta") or {},
                "total": len(items),
                "items": items[: max(1, limit)],
            }
        )

    if path == "/api/crawl" and method == "POST":
        plats = body.get("platforms")
        if isinstance(plats, str):
            plats = [p.strip() for p in plats.split(",") if p.strip()]
        elif not isinstance(plats, list):
            plats = None
        else:
            plats = [str(p).strip() for p in plats if str(p).strip()]
        job_id = uuid.uuid4().hex[:12]
        _set_job(job_id, status="queued", message="已排队", platforms=plats or [])
        threading.Thread(target=_run_job, args=(job_id, plats), daemon=True).start()
        return _json_bytes({"success": True, "job_id": job_id})

    if path.startswith("/api/jobs/") and method == "GET":
        job_id = path.split("/api/jobs/", 1)[1]
        job = _get_job(job_id)
        if not job:
            return _json_bytes({"success": False, "error": "任务不存在"}, 404)
        return _json_bytes({"success": True, "job": job})

    if path == "/api/candidates" and method == "GET":
        items = store.load_candidates()
        platform = (query.get("platform") or [""])[0].strip()
        if platform:
            items = [x for x in items if str(x.get("platform")) == platform]
        try:
            limit = int((query.get("limit") or ["100"])[0])
        except Exception:
            limit = 100
        return _json_bytes({"success": True, "total": len(items), "items": items[:limit]})

    if path == "/api/archive" and method == "GET":
        items = store.load_archive()
        platform = (query.get("platform") or [""])[0].strip()
        atype = (query.get("type") or [""])[0].strip()
        if platform:
            items = [x for x in items if str(x.get("platform")) == platform]
        if atype:
            items = [x for x in items if str(x.get("archive_type")) == atype]
        try:
            limit = int((query.get("limit") or ["100"])[0])
        except Exception:
            limit = 100
        return _json_bytes({"success": True, "total": len(items), "items": items[:limit]})

    if path == "/api/archive" and method == "POST":
        # 手动归档
        result = archive.manual_archive(
            post_id=str(body.get("post_id") or "").strip(),
            post=body.get("post") if isinstance(body.get("post"), dict) else None,
            note=str(body.get("note") or "").strip(),
        )
        status = 200 if result.get("success") else 400
        return _json_bytes(result, status)

    if path == "/api/analyze" and method == "POST":
        from allnews_mornitor.analyze import analyze_record

        post_id = str(body.get("post_id") or "").strip()
        rec = None
        for it in store.load_archive():
            if str(it.get("post_id")) == post_id:
                rec = it
                break
        if not rec:
            return _json_bytes({"success": False, "error": "归档中未找到"}, 404)
        return _json_bytes(analyze_record(rec))

    if path == "/api/materials" and method == "GET":
        from allnews_mornitor.analyze import list_material_for_creation

        try:
            limit = int((query.get("limit") or ["30"])[0])
        except Exception:
            limit = 30
        return _json_bytes({"success": True, "items": list_material_for_creation(limit)})

    return _json_bytes({"success": False, "error": f"未知接口: {path}"}, 404)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[allnews] {self.address_string()} - {fmt % args}")

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
            data = (STATIC_DIR / "index.html").read_bytes()
            self._send(data, 200, "text/html; charset=utf-8")
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            req = _read_json_body(self)
            body, status, ctype = handle_api("POST", parsed.path, parse_qs(parsed.query), req)
            self._send(body, status, ctype)
            return
        self._send(*_json_bytes({"success": False, "error": "Not Found"}, 404))


def _pids_on_port(port: int) -> List[int]:
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:
        return []
    my = os.getpid()
    pids = []
    for line in out.splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid != my:
            pids.append(pid)
    return pids


def _free_port(port: int) -> None:
    pids = _pids_on_port(port)
    if not pids:
        return
    print(f" 端口 {port} 占用中，结束进程: {pids}")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    time.sleep(0.4)
    for pid in _pids_on_port(port):
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass


def run_server(host: str = "127.0.0.1", port: int = 8790, open_browser: bool = True) -> None:
    from utils.stdio_encoding import ensure_utf8_stdio, safe_print

    ensure_utf8_stdio()
    store.ensure_data_dir()
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    cfg = store.load_config()
    host = str((cfg.get("server") or {}).get("host") or host)
    port = int((cfg.get("server") or {}).get("port") or port)
    _free_port(port)
    start_scheduler()
    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    defaults = (cfg.get("defaults") or {})
    safe_print("=" * 60)
    safe_print(" AllNews Monitor")
    safe_print("=" * 60)
    safe_print(f" 地址: {url}")
    safe_print(" 平台: 小红书 / X / 知乎 / 少数派 / 虎嗅 / 36氪")
    safe_print(
        f" 默认频率: 每 {defaults.get('crawl_interval_min', 60)} 分钟；"
        f"候选门槛: 赞≥{(defaults.get('candidate') or {}).get('min_likes', 0)} "
        f"评≥{(defaults.get('candidate') or {}).get('min_comments', 0)}"
    )
    safe_print(" 归档: 入候选后，赞&评 ≥ 中位数自动入库 + 手动精选")
    safe_print(f" 数据: {store.DATA_DIR}")
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
        safe_print("\n已停止 AllNews Monitor")
    finally:
        server.server_close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="AllNews Monitor — 多平台 CDP 头部流量归档")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    cfg = store.load_config().get("server") or {}
    run_server(
        host=args.host or cfg.get("host") or "127.0.0.1",
        port=args.port or int(cfg.get("port") or 8790),
        open_browser=not args.no_browser,
    )


if __name__ == "__main__":
    main()
