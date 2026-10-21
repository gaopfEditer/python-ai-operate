"""
WhisprRT FastAPI 应用工厂（供 Console ASGI 挂载）。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from console.whisprrt.api.router import api_router
from console.whisprrt.core.logging import configure_whisprrt_log_levels

_PKG_DIR = Path(__file__).resolve().parent


def create_whisprrt_app() -> FastAPI:
    configure_whisprrt_log_levels()
    app = FastAPI(title="实时语音转写")
    app.mount(
        "/static",
        StaticFiles(directory=str(_PKG_DIR / "static")),
        name="whisprrt_static",
    )
    templates = Jinja2Templates(directory=str(_PKG_DIR / "templates"))

    app.include_router(api_router)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse(request, "index.html")

    return app
