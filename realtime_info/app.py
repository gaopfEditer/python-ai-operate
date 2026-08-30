# coding=utf-8
"""独立 HTTP：TradingView Webhook + 简易健康检查。

Console 审阅 API 挂在 console/app.py。
也可：python -m realtime_info 仅跑 webhook/轮询。
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realtime_info.config import load_settings, module_enabled  # noqa: E402
from realtime_info.storage.db import init_db, stats  # noqa: E402

logger = logging.getLogger(__name__)


def _json_response(handler: BaseHTTPRequestHandler, code: int, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler: BaseHTTPRequestHandler) -> Any:
    n = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(n) if n > 0 else b""
    if not raw:
        return {}
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except Exception:
        return text


def _check_secret(handler: BaseHTTPRequestHandler, query: Dict[str, list]) -> bool:
    cfg = load_settings()
    server = cfg.get("server") if isinstance(cfg.get("server"), dict) else {}
    secret = str(server.get("webhook_secret") or "").strip()
    if not secret:
        return True
    hdr = (handler.headers.get("X-Webhook-Secret") or "").strip()
    q = (query.get("secret") or [""])[0]
    return hdr == secret or q == secret


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/health"):
            _json_response(
                self,
                200,
                {"ok": True, "service": "realtime_info", "stats": stats()},
            )
            return
        _json_response(self, 404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not _check_secret(self, query):
            _json_response(self, 401, {"ok": False, "error": "bad secret"})
            return
        if parsed.path in ("/hooks/tradingview", "/webhook/tradingview"):
            if not module_enabled("tv"):
                _json_response(self, 403, {"ok": False, "error": "tv module disabled"})
                return
            from realtime_info.collectors.tv_webhook import handle_tv_webhook

            body = _read_body(self)
            # 支持 skip_llm=1 联调
            skip = (query.get("skip_llm") or ["0"])[0] in ("1", "true", "yes")
            result = handle_tv_webhook(body, skip_llm=skip)
            code = 200 if result.get("ok") else 400
            _json_response(self, code, result)
            return
        _json_response(self, 404, {"ok": False, "error": "not found"})


def run_poll_loop(stop: threading.Event) -> None:
    """后台轮询 C / A（KOL 需 CDP，默认不自动猛跑）。"""
    while not stop.is_set():
        try:
            if module_enabled("oi_funding"):
                from realtime_info.collectors.oi_funding import run_oi_funding_once

                run_oi_funding_once(skip_llm=True)
            if module_enabled("onchain"):
                from realtime_info.collectors.onchain_free import run_onchain_once

                run_onchain_once(skip_llm=True)
        except Exception as e:
            logger.exception("poll: %s", e)
        cfg = load_settings()
        mods = cfg.get("modules") if isinstance(cfg.get("modules"), dict) else {}
        oi = mods.get("oi_funding") if isinstance(mods.get("oi_funding"), dict) else {}
        wait = float(oi.get("poll_seconds") or 600)
        stop.wait(wait)


def main(argv: Optional[list] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )
    init_db()
    cfg = load_settings()
    server_cfg = cfg.get("server") if isinstance(cfg.get("server"), dict) else {}
    host = str(server_cfg.get("host") or "127.0.0.1")
    port = int(server_cfg.get("port") or 8788)

    stop = threading.Event()
    poller = threading.Thread(target=run_poll_loop, args=(stop,), daemon=True)
    poller.start()

    httpd = ThreadingHTTPServer((host, port), Handler)
    logger.info("realtime_info webhook on http://%s:%s/hooks/tradingview", host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        stop.set()
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
