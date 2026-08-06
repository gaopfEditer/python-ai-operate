# coding=utf-8
"""
共享 CDP / Selenium 浏览器连接（静默优先）。

静默规则（对齐 crawler/index.py）：
1. 第一次：后台建专用抓取标签，允许抢一次焦点 → 立刻还回
2. 之后：禁止 switch_to / new_window / driver.get；只用 Page.navigate
3. 禁止遍历 tab 去匹配 URL（那是抢焦点主因）
"""

from __future__ import annotations

import random
import subprocess
import sys
import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from allnews_mornitor import store

_driver = None
_crawl_handle: Optional[str] = None
_silent_primed: bool = False
_user_hwnd: int = 0
_mac_front_app: str = ""
_fg_guard = None


def get_debugger_url() -> str:
    cfg = store.load_config()
    return str((cfg.get("cdp") or {}).get("debugger_url") or "127.0.0.1:9222")


def silent_enabled() -> bool:
    return bool((store.load_config().get("cdp") or {}).get("silent", True))


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
    global _driver, _crawl_handle, _silent_primed
    _stop_focus_guard()
    try:
        if _driver is not None:
            _driver.quit()
    except Exception:
        pass
    _driver = None
    _crawl_handle = None
    _silent_primed = False


def jitter_sleep(base_ms: int = 2000, ratio: float = 0.35) -> None:
    base = max(200, int(base_ms))
    jitter = int(base * ratio)
    delay = max(150, base + random.randint(-jitter, jitter))
    time.sleep(delay / 1000)


def _capture_user_front() -> None:
    global _user_hwnd, _mac_front_app
    if sys.platform == "win32":
        if _user_hwnd:
            return
        try:
            from utils.window_focus import get_foreground_hwnd

            _user_hwnd = get_foreground_hwnd()
        except Exception:
            _user_hwnd = 0
        return
    if sys.platform == "darwin":
        if _mac_front_app:
            return
        try:
            out = subprocess.check_output(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first application process whose frontmost is true',
                ],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2,
            )
            _mac_front_app = (out or "").strip()
        except Exception:
            _mac_front_app = ""


def _give_back_focus() -> None:
    if sys.platform == "win32":
        try:
            from utils.window_focus import yield_focus_if_chrome_stolen

            yield_focus_if_chrome_stolen(_user_hwnd)
        except Exception:
            pass
        return
    if sys.platform == "darwin" and _mac_front_app:
        # 不要激活 Google Chrome / Chromium
        app = _mac_front_app
        if app.lower() in {"google chrome", "chromium", "chrome", "microsoft edge"}:
            return
        try:
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'tell application "System Events" to set frontmost of process "{app}" to true',
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
            )
        except Exception:
            pass


def _start_focus_guard() -> None:
    global _fg_guard
    if not silent_enabled():
        return
    if _fg_guard is not None:
        return
    if sys.platform == "win32":
        try:
            from utils.window_focus import ForegroundGuardThread

            _fg_guard = ForegroundGuardThread(preferred_hwnd=_user_hwnd, interval=0.04)
            _fg_guard.start()
        except Exception:
            _fg_guard = None
        return
    if sys.platform == "darwin" and _mac_front_app:
        import threading

        stop = threading.Event()

        def _loop():
            while not stop.wait(0.35):
                try:
                    out = subprocess.check_output(
                        [
                            "osascript",
                            "-e",
                            'tell application "System Events" to get name of first application process whose frontmost is true',
                        ],
                        stderr=subprocess.DEVNULL,
                        text=True,
                        timeout=2,
                    )
                    front = (out or "").strip().lower()
                    if front in {"google chrome", "chromium", "chrome", "microsoft edge"}:
                        _give_back_focus()
                except Exception:
                    pass

        t = threading.Thread(target=_loop, name="allnews-fg-guard", daemon=True)
        t.start()
        _fg_guard = (stop, t)


def _stop_focus_guard() -> None:
    global _fg_guard
    guard = _fg_guard
    _fg_guard = None
    if guard is None:
        return
    if sys.platform == "win32":
        try:
            guard.stop()
        except Exception:
            pass
        return
    if isinstance(guard, tuple):
        stop, t = guard
        stop.set()
        try:
            t.join(timeout=1.0)
        except Exception:
            pass
    _give_back_focus()


def _ensure_crawl_tab(driver) -> str:
    """专用抓取标签：已 primed 后绝不 switch_to。"""
    global _crawl_handle, _silent_primed

    handles = list(driver.window_handles or [])

    if _silent_primed and _crawl_handle:
        if _crawl_handle in handles:
            return _crawl_handle
        print("[allnews] 静默抓取标签丢失，将重建（可能再抢一次焦点）")
        _silent_primed = False
        _crawl_handle = None

    if _crawl_handle and _crawl_handle in handles:
        try:
            if driver.current_window_handle != _crawl_handle:
                driver.switch_to.window(_crawl_handle)
        except Exception:
            _crawl_handle = None
        if _crawl_handle:
            return _crawl_handle

    # 后台建标签，减少置顶
    created = None
    try:
        before = set(handles)
        driver.execute_cdp_cmd(
            "Target.createTarget",
            {"url": "about:blank", "background": True},
        )
        for _ in range(30):
            now = list(driver.window_handles or [])
            new_ones = [h for h in now if h not in before]
            if new_ones:
                created = new_ones[-1]
                break
            time.sleep(0.08)
    except Exception:
        created = None

    if not created:
        try:
            driver.switch_to.new_window("tab")
            created = driver.current_window_handle
        except Exception:
            driver.execute_script("window.open('about:blank','_blank');")
            created = driver.window_handles[-1]

    # 仅此一次切到专用标签，让 Selenium 附着
    try:
        driver.switch_to.window(created)
    except Exception:
        pass
    _crawl_handle = created
    return created


def navigate(driver, url: str) -> None:
    """
    静默导航：
    - 第一次建专用 tab（可抢一次）→ 还焦点 → primed
    - 之后只 Page.navigate / location.href，禁止遍历 switch_to
    """
    global _silent_primed

    target = (url or "").strip()
    if not target:
        return

    if not silent_enabled():
        # 非静默：仍避免扫描全部 tab，直接新开或当前页打开
        try:
            driver.switch_to.new_window("tab")
        except Exception:
            pass
        driver.get(target)
        return

    first = not _silent_primed
    if first:
        _capture_user_front()
        print("[allnews] 静默：第一次允许抢焦点，打开专用抓取标签…")
        _ensure_crawl_tab(driver)
    else:
        if not _crawl_handle:
            _ensure_crawl_tab(driver)
        # 已锁定：即使不在 crawl 标签也不 switch_to
        try:
            cur = driver.current_window_handle
        except Exception:
            cur = None
        if cur != _crawl_handle:
            print("[allnews] 已静默锁定，跳过 switch_to，改用 CDP navigate")

    try:
        driver.execute_cdp_cmd("Page.navigate", {"url": target})
    except Exception:
        if first:
            driver.get(target)
        else:
            # 禁止 get（常会置顶）
            try:
                driver.execute_script("window.location.href = arguments[0];", target)
            except Exception:
                pass

    for _ in range(50):
        try:
            ready = driver.execute_script("return document.readyState")
            if ready in ("interactive", "complete"):
                break
        except Exception:
            pass
        time.sleep(0.1)

    if first:
        _silent_primed = True
        _give_back_focus()
        _start_focus_guard()
        print("[allnews] 静默已锁定：后续只 navigate，不再切标签")
    else:
        _give_back_focus()


# 兼容旧名
def navigate_dedicated_tab(driver, url: str) -> None:
    navigate(driver, url)


def scroll_page(driver, rounds: int = 6, step: int = 900, wait_ms: int = 1200) -> None:
    for _ in range(max(1, rounds)):
        try:
            driver.execute_script(f"window.scrollBy(0, {int(step)});")
        except Exception:
            break
        if silent_enabled() and _silent_primed:
            _give_back_focus()
        jitter_sleep(wait_ms, 0.4)


def exec_js(driver, script: str) -> Any:
    return driver.execute_script(script)


@contextmanager
def cdp_session() -> Iterator[Any]:
    """
    整段抓取生命周期：记录用户前台 → 抓取 → 停止守护并还焦点。
    多平台应共用同一次 session，避免反复 primed。
    """
    driver = get_driver()
    if silent_enabled():
        _capture_user_front()
    try:
        yield driver
    except Exception:
        reset_driver()
        raise
    finally:
        if silent_enabled():
            _stop_focus_guard()
            _give_back_focus()


@contextmanager
def borrow_driver(driver=None) -> Iterator[Any]:
    """平台适配器用：有外部 driver 则复用，否则自开短 session。"""
    if driver is not None:
        yield driver
        return
    with cdp_session() as d:
        yield d
