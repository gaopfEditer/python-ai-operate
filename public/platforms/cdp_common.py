# coding=utf-8
"""CDP 发布共用：连接已登录 Chrome、复用末页签导航、传媒体。"""

from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional, Sequence

logger = logging.getLogger(__name__)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v", ".avi", ".mkv"}


def normalize_media_paths(paths: Optional[Sequence[str]]) -> List[str]:
    out: List[str] = []
    for p in paths or []:
        ap = str(Path(p).expanduser().resolve())
        if not ap:
            continue
        if not os.path.isfile(ap):
            raise FileNotFoundError(f"媒体文件不存在: {ap}")
        out.append(ap)
    return out


def split_media(paths: Sequence[str]) -> tuple[List[str], List[str]]:
    images, videos = [], []
    for p in paths:
        ext = Path(p).suffix.lower()
        if ext in VIDEO_EXTS:
            videos.append(p)
        else:
            images.append(p)
    return images, videos


@contextmanager
def preserve_os_focus() -> Iterator[None]:
    """导航前后尽量保持系统前台窗口（避免 Chrome 抢焦点）。"""
    prev = None
    try:
        if sys.platform == "win32":
            import ctypes

            prev = ctypes.windll.user32.GetForegroundWindow()
        elif sys.platform == "darwin":
            try:
                eth = Path(__file__).resolve().parents[2].parent / "auto-deal-eth"
                if str(eth) not in sys.path:
                    sys.path.insert(0, str(eth))
                from binance.cdp_silent import frontmost_unix_pid

                prev = frontmost_unix_pid()
            except Exception:
                prev = None
    except Exception:
        prev = None
    try:
        yield
    finally:
        if prev is None:
            return
        try:
            time.sleep(0.05)
            if sys.platform == "win32":
                import ctypes

                ctypes.windll.user32.SetForegroundWindow(prev)
            elif sys.platform == "darwin":
                from binance.cdp_silent import activate_unix_pid

                activate_unix_pid(int(prev))
        except Exception:
            pass


def connect_cdp(debugger_url: str = "127.0.0.1:9222"):
    """连接已启动的 Chrome（需 --remote-debugging-port）。连接本身不 switch_to，不抢焦点。"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    for var in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        os.environ.pop(var, None)

    options = Options()
    options.add_experimental_option("debuggerAddress", debugger_url.strip())
    driver = webdriver.Chrome(options=options)
    logger.info("CDP 已连接: %s（不抢焦点）", debugger_url)
    return driver


def _try_silent_cdp_goto(driver, url: str) -> bool:
    """优先走 auto-deal-eth 静默 CDP（不 activate / 不 switch_to）。"""
    try:
        eth = Path(__file__).resolve().parents[2].parent / "auto-deal-eth"
        if eth.is_dir() and str(eth) not in sys.path:
            sys.path.insert(0, str(eth))
        from binance.cdp_navigation import cdp_goto

        cdp_goto(driver, url, page_load_timeout=60, log_prefix="publish-cdp")
        return True
    except Exception as e:
        logger.debug("静默 CDP 导航不可用: %s", e)
        return False


def open_url_new_tab(driver, url: str) -> None:
    """在最后一个已有页签打开 URL：优先静默 CDP（不抢焦点、不新建标签）。"""
    url = (url or "").strip()
    if not url:
        return

    if _try_silent_cdp_goto(driver, url):
        return

    with preserve_os_focus():
        handles = list(driver.window_handles or [])
        if not handles:
            try:
                driver.execute_cdp_cmd(
                    "Target.createTarget",
                    {"url": "about:blank", "background": True},
                )
                time.sleep(0.12)
                handles = list(driver.window_handles or [])
            except Exception:
                try:
                    driver.switch_to.new_window("tab")
                    handles = list(driver.window_handles or [])
                except Exception:
                    driver.execute_script("window.open('about:blank','_blank');")
                    handles = list(driver.window_handles or [])

        if handles:
            last = handles[-1]
            try:
                driver.switch_to.window(last)
            except Exception:
                for h in reversed(handles):
                    try:
                        driver.switch_to.window(h)
                        break
                    except Exception:
                        continue

        try:
            driver.execute_cdp_cmd("Page.navigate", {"url": url})
        except Exception:
            driver.get(url)

        for _ in range(30):
            try:
                cur = (driver.current_url or "").strip()
                if cur and (url.startswith("about:") or cur != "about:blank"):
                    break
            except Exception:
                pass
            time.sleep(0.08)


def wait_css(driver, css: str, timeout: float = 20):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, css))
    )


def find_file_inputs(driver, prefer: str = "any") -> list:
    """
    prefer: any | image | video
    """
    from selenium.webdriver.common.by import By

    inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
    scored = []
    for inp in inputs:
        try:
            if not inp.is_enabled():
                continue
        except Exception:
            continue
        accept = (inp.get_attribute("accept") or "").lower()
        score = 1
        if prefer == "image":
            if "video" in accept and "image" not in accept and "*" not in accept:
                continue
            if "image" in accept or not accept:
                score = 10
        elif prefer == "video":
            if "image" in accept and "video" not in accept and "*" not in accept:
                continue
            if "video" in accept or not accept or "*" in accept:
                score = 10
        scored.append((score, inp))
    scored.sort(key=lambda x: -x[0])
    return [x[1] for x in scored]


def upload_files(driver, paths: Sequence[str], prefer: str = "any", settle_s: float = 2.5) -> int:
    """通过隐藏 file input 上传；多文件用换行拼接路径。"""
    paths = list(paths)
    if not paths:
        return 0
    inputs = find_file_inputs(driver, prefer=prefer)
    if not inputs:
        time.sleep(0.8)
        inputs = find_file_inputs(driver, prefer=prefer)
    if not inputs:
        raise RuntimeError(f"未找到可用的 file input（prefer={prefer}）")
    payload = "\n".join(paths)
    inputs[0].send_keys(payload)
    time.sleep(max(0.5, settle_s))
    return len(paths)


def human_pause(a: float = 0.4, b: float = 1.0) -> None:
    import random

    time.sleep(max(0.1, a + random.random() * max(0.0, b - a)))


def type_text_human(
    driver,
    element,
    text: str,
    *,
    min_delay: float = 0.04,
    max_delay: float = 0.14,
    pause_every: int = 36,
    clear_first: bool = True,
) -> None:
    """逐字输入，模拟人工打字延迟。"""
    import random

    from selenium.webdriver.common.keys import Keys

    if not text:
        return
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click(); arguments[0].focus();", element)
    human_pause(0.15, 0.35)
    mod = Keys.COMMAND if sys.platform == "darwin" else Keys.CONTROL
    if clear_first:
        try:
            element.send_keys(mod, "a")
            element.send_keys(Keys.BACKSPACE)
        except Exception:
            pass
        human_pause(0.08, 0.2)
    else:
        try:
            driver.execute_script(
                """
                const el = arguments[0];
                el.focus();
                if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
                  const len = (el.value || '').length;
                  el.setSelectionRange(len, len);
                  return;
                }
                const sel = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(el);
                range.collapse(false);
                sel.removeAllRanges();
                sel.addRange(range);
                """,
                element,
            )
        except Exception:
            try:
                element.send_keys(mod, Keys.END)
            except Exception:
                pass
        human_pause(0.08, 0.18)
    for i, ch in enumerate(text):
        element.send_keys(ch)
        if ch == "\n":
            time.sleep(random.uniform(0.1, 0.22))
        elif i > 0 and pause_every > 0 and i % pause_every == 0:
            time.sleep(random.uniform(0.18, 0.5))
        else:
            time.sleep(random.uniform(min_delay, max_delay))
