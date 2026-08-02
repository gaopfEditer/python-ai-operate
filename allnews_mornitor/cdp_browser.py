# coding=utf-8
"""共享 CDP / Selenium 浏览器连接（复用已开启远程调试的 Chrome）。"""

from __future__ import annotations

import random
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from allnews_mornitor import store

_driver = None


def get_debugger_url() -> str:
    cfg = store.load_config()
    return str((cfg.get("cdp") or {}).get("debugger_url") or "127.0.0.1:9222")


def get_driver(force_new: bool = False):
    """连接已启动的 Chrome CDP。"""
    global _driver
    if _driver is not None and not force_new:
        try:
            _ = _driver.window_handles
            return _driver
        except Exception:
            _driver = None

    from selenium import webdriver

    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", get_debugger_url())
    _driver = webdriver.Chrome(options=options)
    return _driver


def reset_driver() -> None:
    global _driver
    try:
        if _driver is not None:
            _driver.quit()
    except Exception:
        pass
    _driver = None


def jitter_sleep(base_ms: int = 2000, ratio: float = 0.35) -> None:
    base = max(200, int(base_ms))
    jitter = int(base * ratio)
    delay = max(150, base + random.randint(-jitter, jitter))
    time.sleep(delay / 1000)


def navigate_dedicated_tab(driver, url: str) -> None:
    """
    不替换用户当前页：已有同 URL tab 则切换刷新，否则新建 tab。
    """
    from selenium.common.exceptions import WebDriverException
    from urllib.parse import urlparse

    target = (url or "").strip()
    matched = None
    for handle in list(driver.window_handles):
        try:
            driver.switch_to.window(handle)
            cur = (driver.current_url or "").split("#")[0].rstrip("/")
            want = target.split("#")[0].rstrip("/")
            if cur == want or (want and want in cur):
                matched = handle
                break
            # 同站路径宽松匹配
            pu, cu = urlparse(want), urlparse(cur)
            if pu.netloc and pu.netloc == cu.netloc and pu.path and pu.path == cu.path:
                matched = handle
                break
        except WebDriverException:
            continue

    if matched:
        driver.switch_to.window(matched)
        try:
            driver.execute_script("location.reload();")
        except WebDriverException:
            driver.refresh()
        return

    try:
        driver.switch_to.new_window("tab")
    except WebDriverException:
        driver.execute_script("window.open('about:blank','_blank');")
        driver.switch_to.window(driver.window_handles[-1])
    driver.get(target)


def scroll_page(driver, rounds: int = 6, step: int = 900, wait_ms: int = 1200) -> None:
    for _ in range(max(1, rounds)):
        try:
            driver.execute_script(f"window.scrollBy(0, {int(step)});")
        except Exception:
            break
        jitter_sleep(wait_ms, 0.4)


def exec_js(driver, script: str) -> Any:
    return driver.execute_script(script)


@contextmanager
def cdp_session():
    driver = get_driver()
    try:
        yield driver
    except Exception:
        reset_driver()
        raise
