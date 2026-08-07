# coding=utf-8
"""
共享 CDP 浏览器连接（不抢焦点）。

静默模式（默认）：
- 经 Chrome 远程调试 WebSocket 建标签：Target.createTarget(background=True)
- 用 Target.attachToTarget 附着，禁止 Target.activateTarget / switch_to / driver.get
- 导航与 JS 均走该 session，不把 Chrome 拉到前台
- 绝不「还焦」或守护前台：用户切走别处后不会被抢回来

非静默：退回 Selenium 常规打开（会切前台，仅调试用）。
"""

from __future__ import annotations

import json
import random
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from allnews_mornitor import store

_driver = None
_bg: Optional["BackgroundTarget"] = None


def get_debugger_url() -> str:
    cfg = store.load_config()
    return str((cfg.get("cdp") or {}).get("debugger_url") or "127.0.0.1:9222")


def silent_enabled() -> bool:
    return bool((store.load_config().get("cdp") or {}).get("silent", True))


def _http_json(path: str) -> Any:
    base = get_debugger_url().rstrip("/")
    if not base.startswith("http"):
        base = f"http://{base}"
    url = f"{base}{path}"
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _browser_ws_url() -> str:
    ver = _http_json("/json/version")
    ws = (ver or {}).get("webSocketDebuggerUrl") or ""
    if not ws:
        raise RuntimeError("Chrome CDP 未返回 webSocketDebuggerUrl，请确认已开 --remote-debugging-port")
    return ws


class _CdpClient:
    """浏览器级 CDP：按 sessionId 把命令发到后台页，不 activate。"""

    def __init__(self, ws_url: str):
        from websockets.sync.client import connect

        self._ws = connect(ws_url, max_size=64 * 1024 * 1024, open_timeout=10)
        self._next_id = 0
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._pending: dict[int, dict] = {}
        self._closed = False
        self._reader = threading.Thread(target=self._read_loop, name="allnews-cdp", daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        try:
            while not self._closed:
                raw = self._ws.recv()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                msg = json.loads(raw)
                mid = msg.get("id")
                if mid is None:
                    continue
                with self._cv:
                    self._pending[int(mid)] = msg
                    self._cv.notify_all()
        except Exception:
            with self._cv:
                self._closed = True
                self._cv.notify_all()

    def call(
        self,
        method: str,
        params: Optional[dict] = None,
        session_id: Optional[str] = None,
        timeout: float = 60.0,
    ) -> dict:
        with self._lock:
            if self._closed:
                raise RuntimeError("CDP 连接已关闭")
            self._next_id += 1
            msg_id = self._next_id
            payload: dict[str, Any] = {
                "id": msg_id,
                "method": method,
                "params": params or {},
            }
            if session_id:
                payload["sessionId"] = session_id
            self._ws.send(json.dumps(payload))
            deadline = time.time() + timeout
            while msg_id not in self._pending:
                if self._closed:
                    raise RuntimeError(f"CDP 断开: {method}")
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise TimeoutError(f"CDP 超时: {method}")
                self._cv.wait(timeout=remaining)
            resp = self._pending.pop(msg_id)
        if "error" in resp:
            err = resp["error"]
            raise RuntimeError(f"{method}: {err}")
        return resp.get("result") or {}

    def close(self) -> None:
        self._closed = True
        try:
            self._ws.close()
        except Exception:
            pass


class BackgroundTarget:
    """后台标签：创建与操作均不 activate。"""

    def __init__(self, client: _CdpClient, target_id: str, session_id: str):
        self.client = client
        self.target_id = target_id
        self.session_id = session_id

    @classmethod
    def create(cls, client: _CdpClient, url: str = "about:blank") -> "BackgroundTarget":
        created = client.call(
            "Target.createTarget",
            {"url": url or "about:blank", "background": True},
        )
        target_id = str(created.get("targetId") or "")
        if not target_id:
            raise RuntimeError("Target.createTarget 未返回 targetId")
        attached = client.call(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
        )
        session_id = str(attached.get("sessionId") or "")
        if not session_id:
            raise RuntimeError("Target.attachToTarget 未返回 sessionId")
        page = cls(client, target_id, session_id)
        # 不调用 Target.activateTarget
        try:
            page.call("Page.enable")
            page.call("Runtime.enable")
        except Exception:
            pass
        return page

    def call(self, method: str, params: Optional[dict] = None, timeout: float = 60.0) -> dict:
        return self.client.call(method, params, session_id=self.session_id, timeout=timeout)

    def silent_navigate(self, url: str) -> None:
        target = (url or "").strip()
        if not target:
            return
        self.call("Page.navigate", {"url": target})
        self._wait_ready()

    def _wait_ready(self, timeout: float = 25.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                state = self.eval_js("document.readyState")
                if state in ("interactive", "complete"):
                    return
            except Exception:
                pass
            time.sleep(0.12)

    def eval_js(self, script: str) -> Any:
        # 包一层 IIFE，兼容「多语句 + return」的抽取脚本
        src = (script or "").strip()
        if not src:
            return None
        expression = f"(() => {{\n{src}\n}})()"
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
                "userGesture": False,
            },
            timeout=90.0,
        )
        if result.get("exceptionDetails"):
            detail = result["exceptionDetails"]
            text = detail.get("text") or detail.get("exception", {}).get("description") or detail
            raise RuntimeError(f"JS 执行失败: {text}")
        remote = result.get("result") or {}
        return remote.get("value")

    def detach(self) -> None:
        try:
            self.client.call("Target.detachFromTarget", {"sessionId": self.session_id})
        except Exception:
            pass


def get_driver(force_new: bool = False):
    """非静默模式用的 Selenium 连接。"""
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
    global _driver, _bg
    if _bg is not None:
        try:
            _bg.client.close()
        except Exception:
            pass
        _bg = None
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


def _as_bg(driver) -> Optional[BackgroundTarget]:
    if isinstance(driver, BackgroundTarget):
        return driver
    return _bg if isinstance(_bg, BackgroundTarget) else None


def navigate(driver, url: str) -> None:
    """静默：后台 session Page.navigate；非静默：Selenium get。"""
    target = (url or "").strip()
    if not target:
        return

    bg = _as_bg(driver)
    if bg is not None:
        bg.silent_navigate(target)
        return

    if not silent_enabled():
        try:
            driver.switch_to.new_window("tab")
        except Exception:
            pass
        driver.get(target)
        return

    raise RuntimeError("静默模式未建立后台 CDP session")


def navigate_dedicated_tab(driver, url: str) -> None:
    navigate(driver, url)


def scroll_page(driver, rounds: int = 6, step: int = 900, wait_ms: int = 1200) -> None:
    bg = _as_bg(driver)
    for _ in range(max(1, rounds)):
        try:
            if bg is not None:
                bg.eval_js(f"window.scrollBy(0, {int(step)}); return true;")
            else:
                driver.execute_script(f"window.scrollBy(0, {int(step)});")
        except Exception:
            break
        jitter_sleep(wait_ms, 0.4)


def exec_js(driver, script: str) -> Any:
    bg = _as_bg(driver)
    if bg is not None:
        return bg.eval_js(script)
    return driver.execute_script(script)


@contextmanager
def cdp_session() -> Iterator[Any]:
    """
    整段抓取共用一次后台标签。
    静默：纯 CDP，不抢焦点、不还焦。
    """
    global _bg

    if not silent_enabled():
        driver = get_driver()
        try:
            yield driver
        except Exception:
            reset_driver()
            raise
        return

    client: Optional[_CdpClient] = None
    page: Optional[BackgroundTarget] = None
    try:
        try:
            _http_json("/json/version")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise RuntimeError(
                f"无法连接 Chrome CDP ({get_debugger_url()})，请先用 --remote-debugging-port 启动: {e}"
            ) from e

        client = _CdpClient(_browser_ws_url())
        page = BackgroundTarget.create(client, "about:blank")
        _bg = page
        print("[allnews] 静默 CDP：后台标签已建立（不激活、不还焦）")
        yield page
    except Exception:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        _bg = None
        raise
    finally:
        if page is not None:
            try:
                page.detach()
            except Exception:
                pass
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        if _bg is page:
            _bg = None


@contextmanager
def borrow_driver(driver=None) -> Iterator[Any]:
    """平台适配器用：有外部 session 则复用，否则自开短 session。"""
    if driver is not None:
        yield driver
        return
    with cdp_session() as d:
        yield d
