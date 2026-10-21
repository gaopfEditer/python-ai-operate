# coding=utf-8
"""Console + WhisprRT 组合 ASGI 应用（单端口 HTTP + WebSocket）。"""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping, MutableMapping, Optional
from urllib.parse import parse_qs

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import Mount, Route

from console.app import STATIC_DIR, handle_api


def _cors_headers() -> Dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Publish-Token",
        "Cache-Control": "no-store",
    }


def _parse_api_body(content_type: Optional[str], raw: bytes) -> Dict[str, Any]:
    if not raw:
        return {}
    ctype = (content_type or "").lower()
    if "multipart/form-data" in ctype:
        from console.publish_api import parse_multipart

        return parse_multipart(raw, content_type or "")
    try:
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def _console_api(request: Request) -> Response:
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=_cors_headers())

    path = request.url.path
    if not path.startswith("/api/"):
        return Response(status_code=404, content=b"Not Found")

    query = parse_qs(request.url.query)
    body: Dict[str, Any] = {}
    if request.method in ("POST", "PUT", "PATCH"):
        raw = await request.body()
        body = _parse_api_body(request.headers.get("content-type"), raw)

    headers: MutableMapping[str, str] = request.headers
    payload, status, ctype = handle_api(
        request.method,
        path,
        query,
        body,
        headers=headers,
    )
    media = ctype.split(";")[0].strip() if ctype else "application/json"
    return Response(
        content=payload,
        status_code=status,
        media_type=media,
        headers=_cors_headers(),
    )


async def _serve_index(_request: Request) -> Response:
    index = STATIC_DIR / "index.html"
    return FileResponse(index, media_type="text/html; charset=utf-8")


async def _whisprrt_unavailable(_request: Request) -> Response:
    msg = (
        "WhisprRT 实时监听未加载（缺少依赖或 PortAudio）。"
        "请安装 requirements.txt 中的 faster-whisper、sounddevice，"
        "并在 Linux/macOS 上安装 PortAudio 后重启 Console。"
    )
    return Response(msg, status_code=503, media_type="text/plain; charset=utf-8")


def create_console_asgi_app() -> Starlette:
    from starlette.staticfiles import StaticFiles

    routes = [
        Route(
            "/api/{rest:path}",
            endpoint=_console_api,
            methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        ),
        Route("/", endpoint=_serve_index, methods=["GET"]),
        Route("/index.html", endpoint=_serve_index, methods=["GET"]),
        Route("/taxonomy", endpoint=_serve_index, methods=["GET"]),
    ]
    try:
        from console.whisprrt.fastapi_factory import create_whisprrt_app

        routes.append(Mount("/whisprrt", app=create_whisprrt_app()))
    except Exception as exc:
        print(f"[console] WhisprRT 未挂载: {exc}", flush=True)
        routes.append(Route("/whisprrt", endpoint=_whisprrt_unavailable, methods=["GET"]))
        routes.append(Route("/whisprrt/{rest:path}", endpoint=_whisprrt_unavailable))

    routes.append(Mount("/", app=StaticFiles(directory=str(STATIC_DIR)), name="console_static"))
    return Starlette(routes=routes)
