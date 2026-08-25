# coding=utf-8
"""CDP 发布共用：连接已登录 Chrome、开标签、传媒体。"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import List, Optional, Sequence

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


def connect_cdp(debugger_url: str = "127.0.0.1:9222"):
    """连接已启动的 Chrome（需 --remote-debugging-port）。"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    # 避免代理干扰 CDP
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
    logger.info("CDP 已连接: %s", debugger_url)
    return driver


def open_url_new_tab(driver, url: str) -> None:
    """新标签打开 URL（尽量不替换用户当前标签）。"""
    before = set(driver.window_handles or [])
    try:
        driver.execute_cdp_cmd(
            "Target.createTarget",
            {"url": url, "background": False},
        )
        for _ in range(40):
            now = list(driver.window_handles or [])
            new_ones = [h for h in now if h not in before]
            if new_ones:
                driver.switch_to.window(new_ones[-1])
                return
            time.sleep(0.08)
    except Exception:
        pass
    try:
        driver.switch_to.new_window("tab")
    except Exception:
        driver.execute_script("window.open('about:blank','_blank');")
        driver.switch_to.window(driver.window_handles[-1])
    driver.get(url)


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
        # 再扫一次（部分 UI 点「媒体」后才挂载 input）
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
    import sys

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
