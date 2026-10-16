# coding=utf-8
"""CDP 网页文生图：Gemini / X Grok 统一入口。"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUTO_DEAL_ETH_ROOT = Path(os.environ.get("AUTO_DEAL_ETH_ROOT", PROJECT_ROOT.parent / "auto-deal-eth"))


def normalize_engine(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in ("grok", "x", "x-grok", "twitter"):
        return "grok"
    return "gemini"


def engine_page_url(engine: str) -> str:
    if engine == "grok":
        return os.getenv("GROK_WEB_URL", "https://x.com/i/grok").strip()
    return os.getenv("GEMINI_WEB_URL", "https://gemini.google.com/app").strip()


def _ensure_auto_deal_eth() -> None:
    root = str(AUTO_DEAL_ETH_ROOT.resolve())
    if not AUTO_DEAL_ETH_ROOT.is_dir():
        raise FileNotFoundError(f"未找到 auto-deal-eth：{AUTO_DEAL_ETH_ROOT}")
    if root not in sys.path:
        sys.path.insert(0, root)


def apply_debugger_url(debugger_url: str) -> None:
    raw = str(debugger_url or "").strip()
    if not raw:
        return
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    port = raw.rsplit(":", 1)[-1] if ":" in raw else raw
    if port.isdigit():
        os.environ["CHROME_DEBUG_PORT"] = port
        os.environ["USE_REMOTE_DEBUGGING"] = "True"


def open_engine_tab(driver, debugger_url: str, engine: str):
    """激活已有同站页签，否则新开 blank。"""
    import requests as _req

    base = engine_page_url(engine)
    debugger = (
        debugger_url.strip()
        or os.environ.get("CDP_DEBUGGER_URL")
        or os.environ.get("BROWSER_DEBUGGER_URL")
        or ""
    )
    if debugger:
        try:
            resp = _req.get(f"http://{debugger}/json", timeout=5)
            tabs = resp.json() if resp.status_code == 200 else []
            p1 = urlparse(base)
            for tab in tabs:
                tab_url = str(tab.get("url") or "")
                if not tab_url or tab_url in ("about:blank", "chrome://newtab/"):
                    continue
                try:
                    p2 = urlparse(tab_url)
                    host_match = p1.netloc == p2.netloc
                    path_match = (p1.path.rstrip("/") or "/") == (p2.path.rstrip("/") or "/")
                    if engine == "grok" and "x.com" in p2.netloc and "/grok" in (p2.path or ""):
                        host_match = True
                        path_match = True
                    if host_match and path_match:
                        tid = str(tab.get("id") or tab.get("targetId") or "")
                        if tid:
                            _req.post(f"http://{debugger}/json/activate", json={"id": tid}, timeout=5)
                        for h in list(driver.window_handles or []):
                            try:
                                driver.switch_to.window(h)
                                cur = (driver.current_url or "").lower()
                                if engine == "grok" and "x.com" in cur and "grok" in cur:
                                    return driver, h
                                if base.replace("https://", "").replace("http://", "") in cur.replace(
                                    "https://", ""
                                ).replace("http://", ""):
                                    return driver, h
                            except Exception:
                                continue
                except Exception:
                    continue
        except Exception:
            pass

    main_handle = driver.current_window_handle if driver.window_handles else None
    driver.execute_script("window.open('about:blank');")
    time.sleep(0.5)
    handles = list(driver.window_handles)
    new_handle = next((h for h in handles if h != main_handle), handles[-1])
    driver.switch_to.window(new_handle)
    return driver, new_handle


def generate_image_cdp_web(
    prompt: str,
    *,
    out_dir: str,
    tag: str,
    engine: str = "gemini",
    debugger_url: str = "",
    keep_browser_open: bool = False,
) -> Dict[str, Any]:
    """在已登录的 CDP Chrome 中通过 Gemini 或 Grok 网页出图。"""
    eng = normalize_engine(engine)
    _ensure_auto_deal_eth()
    apply_debugger_url(debugger_url)

    if eng == "grok":
        from corpus.grok_web_automation import generate_image_with_grok_web

        return generate_image_with_grok_web(
            prompt,
            out_dir=out_dir,
            tag=tag,
            keep_browser_open=keep_browser_open,
        )

    from gemini_web_automation import generate_image_with_gemini_web

    return generate_image_with_gemini_web(
        prompt,
        out_dir=out_dir,
        tag=tag,
        keep_browser_open=keep_browser_open,
    )


def gen_realtime_image(
    *,
    item_id: str,
    prompt_text: str,
    engine: str = "gemini",
    debugger_url: str = "",
    max_retries: int = 5,
    retry_delay: float = 20,
    human_pause=None,
) -> Dict[str, Any]:
    """实时发送配图：落盘到 output/rt_images，返回相对 path。"""
    out_dir = PROJECT_ROOT / "output" / "rt_images"
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"rt_{item_id[:8]}" if len(item_id) >= 8 else f"rt_{uuid.uuid4().hex[:8]}"
    eng = normalize_engine(engine)
    last_err = ""

    for attempt in range(1, max_retries + 1):
        try:
            result = generate_image_cdp_web(
                prompt_text,
                out_dir=str(out_dir),
                tag=tag,
                engine=eng,
                debugger_url=debugger_url,
                keep_browser_open=False,
            )
            images = result.get("images") or []
            if images:
                saved_path = Path(images[0])
                if saved_path.is_file() and saved_path.stat().st_size > 4096:
                    rel = saved_path.resolve().relative_to(PROJECT_ROOT.resolve())
                    return {"success": True, "path": str(rel), "engine": eng}
                last_err = f"图片文件无效或过小: {saved_path}"
            else:
                last_err = str(result.get("error") or "未返回图片路径")

            if attempt < max_retries and human_pause:
                human_pause(retry_delay * 0.8, retry_delay * 1.2)
                continue
            if attempt >= max_retries:
                return {"success": False, "error": f"重试{max_retries}次仍失败: {last_err}", "engine": eng}
        except Exception as e:
            last_err = str(e)
            if attempt < max_retries and human_pause:
                human_pause(retry_delay * 0.8, retry_delay * 1.2)
            elif attempt >= max_retries:
                return {"success": False, "error": f"重试{max_retries}次仍异常: {last_err}", "engine": eng}

    return {"success": False, "error": last_err or "生图失败", "engine": eng}
