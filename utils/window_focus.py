# coding=utf-8
"""Windows 前台窗口保护：允许首次抢焦点，之后只还焦点、不最小化关窗。"""

from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager
from typing import Iterator, List, Optional


def _win_user32():
    if sys.platform != "win32":
        return None
    import ctypes

    return ctypes.windll.user32


def get_foreground_hwnd() -> int:
    user32 = _win_user32()
    if not user32:
        return 0
    try:
        return int(user32.GetForegroundWindow() or 0)
    except Exception:
        return 0


def set_foreground_hwnd(hwnd: int) -> None:
    """把焦点还给指定窗口（不要求最小化 Chrome）。"""
    user32 = _win_user32()
    if not user32 or not hwnd:
        return
    try:
        user32.AllowSetForegroundWindow(-1)
    except Exception:
        pass
    try:
        # SW_SHOWNOACTIVATE=4 不够；对用户窗口需要真正前台
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    except Exception:
        pass
    try:
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def enum_chrome_hwnds() -> List[int]:
    user32 = _win_user32()
    if not user32:
        return []
    import ctypes
    from ctypes import wintypes

    results: List[int] = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
    )

    def _cb(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value or ""
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            class_name = cls.value or ""
            if class_name.startswith("Chrome_WidgetWin_") and title:
                results.append(int(hwnd))
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(EnumWindowsProc(_cb), 0)
    except Exception:
        pass
    return results


def chrome_is_foreground() -> bool:
    fg = get_foreground_hwnd()
    return bool(fg) and fg in set(enum_chrome_hwnds())


def yield_focus_if_chrome_stolen(preferred_hwnd: int) -> None:
    """
    若当前前台是 Chrome，而 preferred 是用户原窗口，则还回焦点。
    不最小化、不关窗——窗口仍在，只是不再置顶打扰。
    """
    if not preferred_hwnd:
        return
    try:
        chrome = set(enum_chrome_hwnds())
        if preferred_hwnd in chrome:
            return
        fg = get_foreground_hwnd()
        if fg in chrome or fg == 0:
            set_foreground_hwnd(preferred_hwnd)
    except Exception:
        pass


class ForegroundGuardThread:
    """首次抢焦点之后：高频检测，Chrome 再抢就立刻还回去（不最小化窗口）。"""

    def __init__(self, preferred_hwnd: int = 0, interval: float = 0.05):
        self.preferred_hwnd = preferred_hwnd or get_foreground_hwnd()
        self.interval = max(0.03, float(interval))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if sys.platform != "win32":
            return
        if self._thread and self._thread.is_alive():
            return

        def _loop():
            while not self._stop.is_set():
                try:
                    yield_focus_if_chrome_stolen(self.preferred_hwnd)
                except Exception:
                    pass
                self._stop.wait(self.interval)

        self._thread = threading.Thread(target=_loop, name="fg-guard", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        yield_focus_if_chrome_stolen(self.preferred_hwnd)


@contextmanager
def preserve_foreground(enabled: bool = True) -> Iterator[Optional[int]]:
    if not enabled or sys.platform != "win32":
        yield None
        return
    prev = get_foreground_hwnd()
    guard = ForegroundGuardThread(preferred_hwnd=prev)
    guard.start()
    try:
        yield prev
    finally:
        guard.stop()


# 兼容旧调用名（不再最小化，避免“窗口没了”）
def minimize_chrome_noactivate() -> None:
    return
