# coding=utf-8
"""CDP 发布共用：连接已登录 Chrome、复用末页签导航、传媒体。"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class PublishAborted(Exception):
    """CDP 发布被用户终止或新任务抢占。"""


def publish_abort_requested() -> bool:
    try:
        from console.publish_context import abort_requested

        return abort_requested()
    except Exception:
        return False


def raise_if_publish_aborted() -> None:
    if publish_abort_requested():
        raise PublishAborted("已终止")


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
            pass
        else:
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


def _cdp_http_base(debugger_url: str) -> str:
    base = (debugger_url or "").strip()
    if not base:
        base = "127.0.0.1:9222"
    if not base.startswith("http"):
        base = f"http://{base}"
    return base.rstrip("/")


def fetch_cdp_browser_version(debugger_url: str) -> Optional[str]:
    """读 CDP 端口上正在运行的 Chrome 版本（与系统安装的 Chrome 可能不是同一只）。"""
    url = f"{_cdp_http_base(debugger_url)}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        browser = str((data or {}).get("Browser") or "")
        if "/" in browser:
            return browser.split("/", 1)[1].strip()
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError) as e:
        logger.debug("CDP %s 读取失败: %s", url, e)
    return None


def fetch_cdp_target_count(debugger_url: str) -> Optional[int]:
    """CDP /json 目标数（标签页 + 扩展/worker 等）。过多时 Selenium attach 易变慢或卡住。"""
    url = f"{_cdp_http_base(debugger_url)}/json"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        if isinstance(data, list):
            return len(data)
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError) as e:
        logger.debug("CDP %s 目标列表读取失败: %s", url, e)
    return None


def _installed_chrome_version() -> Optional[str]:
    """本机默认 Google Chrome 版本（Selenium Manager 通常按此拉 ChromeDriver）。"""
    import shutil
    import subprocess

    for cmd in (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chrome"),
    ):
        if not cmd:
            continue
        try:
            out = subprocess.run(
                [cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            line = (out.stdout or out.stderr or "").strip()
            # "Google Chrome 154.0.8037.58"
            parts = line.split()
            if parts:
                ver = parts[-1]
                if re.match(r"^\d+\.\d+\.\d+\.\d+$", ver):
                    return ver
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def _chrome_major(version: str) -> Optional[int]:
    m = re.match(r"^(\d+)", (version or "").strip())
    return int(m.group(1)) if m else None


_CDP_LOCK = threading.RLock()
_CDP_ATTACH_LOCK = threading.Lock()
_CDP_POOL: Dict[str, Any] = {}
# Selenium NEW_SESSION 读超时（秒）。/json 能打开 ≠ attach 一定快，标签/worker 多时会拖到超时。
CDP_CONNECT_TIMEOUT_SEC = float(os.environ.get("CDP_CONNECT_TIMEOUT_SEC", "90"))
_CDP_TARGET_COUNT_WARN = int(os.environ.get("CDP_TARGET_COUNT_WARN", "40"))


def cdp_driver_alive(driver: Any) -> bool:
    """探测 Selenium 与 CDP 的会话是否仍可用。"""
    try:
        _ = driver.window_handles
        return True
    except Exception:
        return False


def invalidate_cdp_driver(debugger_url: str) -> None:
    """丢弃该调试地址的缓存 WebDriver（Chrome 本身不退出）。"""
    addr = debugger_url.strip()
    with _CDP_LOCK:
        old = _CDP_POOL.pop(addr, None)
    if old is None:
        return
    try:
        old.quit()
    except Exception:
        pass


def _configure_driver_timeouts(driver: Any) -> None:
    try:
        driver.set_page_load_timeout(45)
    except Exception:
        pass
    try:
        driver.set_script_timeout(90)
    except Exception:
        pass
    try:
        driver.command_executor.set_timeout(60)
    except Exception:
        pass


def _cdp_attach_timeout_hint(addr: str, timeout_sec: float) -> str:
    n = fetch_cdp_target_count(addr)
    parts = [
        f"Selenium 通过 ChromeDriver attach 到 {addr} 超时（>{int(timeout_sec)}s）。",
        "调试端口 HTTP（如 /json）正常只说明 Chrome 在监听，"
        "与「新建 WebDriver 会话」不是同一条链路；后者卡住时 /json 仍可秒开。",
    ]
    if n is not None:
        parts.append(f"当前 CDP 目标约 {n} 个（含后台页/worker）。")
        if n >= _CDP_TARGET_COUNT_WARN:
            parts.append(
                "目标过多时 attach 常越来越慢；请关掉无用标签页、重启调试 Chrome，"
                "并避免连续失败发布（每次失败若并发 attach 会叠加拖死浏览器）。"
            )
    else:
        parts.append("请重启带 --remote-debugging-port 的 Chrome 后再试。")
    return "".join(parts)


def _attach_chrome_webdriver(addr: str, options: Any, timeout_sec: float) -> Any:
    """串行 attach，避免多个 NEW_SESSION 并发把 Chrome 拖死。Selenium 4.48 起勿用 RemoteConnection 类级 get/set_timeout。"""
    from selenium import webdriver

    with _CDP_ATTACH_LOCK:
        try:
            driver = webdriver.Chrome(options=options)
        except Exception as e:
            err = str(e)
            if "Read timed out" in err or "timed out" in err.lower():
                raise TimeoutError(_cdp_attach_timeout_hint(addr, timeout_sec)) from e
            raise
        # 会话建好后用实例级 timeout（默认 NEW_SESSION 约 120s，由 Selenium ClientConfig 决定）
        sec = max(10, int(timeout_sec))
        try:
            driver.command_executor.set_timeout(sec)
        except Exception:
            pass
        return driver


def connect_cdp(
    debugger_url: str = "127.0.0.1:9222",
    *,
    force_new: bool = False,
    timeout_sec: Optional[float] = None,
):
    """连接已启动的 Chrome（需 --remote-debugging-port）。同地址复用 WebDriver，避免重复 NEW_SESSION 拖死浏览器。"""
    from selenium.common.exceptions import SessionNotCreatedException
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

    addr = debugger_url.strip()
    tout = CDP_CONNECT_TIMEOUT_SEC if timeout_sec is None else timeout_sec

    with _CDP_LOCK:
        if not force_new:
            cached = _CDP_POOL.get(addr)
            if cached is not None and cdp_driver_alive(cached):
                return cached
            if cached is not None:
                _CDP_POOL.pop(addr, None)
                try:
                    cached.quit()
                except Exception:
                    pass

    cdp_ver = fetch_cdp_browser_version(addr)
    local_ver = _installed_chrome_version()
    if cdp_ver and local_ver:
        cdp_m = _chrome_major(cdp_ver)
        loc_m = _chrome_major(local_ver)
        if cdp_m is not None and loc_m is not None and cdp_m != loc_m:
            raise RuntimeError(
                f"CDP {addr} 上的 Chrome 为 {cdp_ver}，本机 Chrome 为 {local_ver}，"
                f"Selenium 会使用 ChromeDriver {loc_m}，无法 attach 到 {cdp_m} 的调试实例。"
                f"9223/9222 端口能 curl 通不代表版本已对齐。"
                f"请完全退出该调试 Chrome，用本机最新 Chrome 重新启动，例如："
                f' "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" '
                f'--remote-debugging-port={addr.split(":")[-1]} '
                f'--user-data-dir="$HOME/chrome-cdp-profile"'
            )

    options = Options()
    options.add_experimental_option("debuggerAddress", addr)

    target_n = fetch_cdp_target_count(addr)
    if target_n is not None and target_n >= _CDP_TARGET_COUNT_WARN:
        logger.warning(
            "CDP %s 目标数 %s，Selenium attach 可能较慢（/json 仍可正常访问）",
            addr,
            target_n,
        )

    try:
        driver = _attach_chrome_webdriver(addr, options, tout)
    except SessionNotCreatedException as e:
        msg = str(e)
        if "only supports Chrome version" in msg or "Current browser version" in msg:
            hint = (
                f"ChromeDriver 与 {addr} 上的 Chrome 主版本不一致。"
                f"端口能访问只说明调试服务在跑，不代表驱动已匹配。"
            )
            if cdp_ver:
                hint += f" 该端口当前浏览器版本约为 {cdp_ver}。"
            if local_ver:
                hint += f" 本机 Chrome 约为 {local_ver}（ChromeDriver 通常跟随本机）。"
            hint += (
                " 请关闭该调试 Chrome 后，用本机最新 Chrome 重新启动，例如："
                " chrome --remote-debugging-port=9223 --user-data-dir=…"
            )
            raise SessionNotCreatedException(hint) from e
        raise

    _configure_driver_timeouts(driver)
    try:
        driver._cdp_debugger_url = addr  # type: ignore[attr-defined]
        driver._cdp_pooled = True  # type: ignore[attr-defined]
    except Exception:
        pass
    with _CDP_LOCK:
        _CDP_POOL[addr] = driver
    logger.info("CDP 已连接: %s（不抢焦点）", addr)
    return driver


_HOST_ALIASES = {
    "x.com": ("x.com", "twitter.com"),
    "twitter.com": ("x.com", "twitter.com"),
    "binance.com": ("binance.com",),
    "okx.com": ("okx.com",),
    "gate.com": ("gate.com",),
    "bitget.com": ("bitget.com",),
    "gemini.google.com": ("gemini.google.com",),
}


def _bare_host(url: str) -> str:
    host = (urlparse(url or "").netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _host_aliases(url: str) -> Tuple[str, ...]:
    host = _bare_host(url)
    return _HOST_ALIASES.get(host, (host,) if host else ())


def _path_of(url: str) -> str:
    return (urlparse(url or "").path or "").rstrip("/").lower()


def _is_usable_page_url(url: str) -> bool:
    u = (url or "").strip()
    if not u:
        return False
    low = u.lower()
    return not low.startswith(
        ("chrome://", "chrome-extension://", "devtools://", "about:", "edge://", "data:")
    )


def _urls_match(a: str, b: str) -> bool:
    """同一页面：host 别名一致且路径相同（忽略末尾斜杠和 query）。"""
    if not a or not b:
        return False
    ha, hb = _bare_host(a), _bare_host(b)
    if not ha or not hb:
        return False
    aliases = _host_aliases(a) or (ha,)
    if hb != ha and hb not in aliases and ha not in _host_aliases(b):
        return False
    return _path_of(a) == _path_of(b)


def _same_site(tab_url: str, want_url: str) -> bool:
    host = _bare_host(tab_url)
    if not host or not _is_usable_page_url(tab_url):
        return False
    aliases = _host_aliases(want_url)
    if not aliases:
        return False
    return any(host == a or host.endswith("." + a) for a in aliases)


def _debugger_http_base(driver) -> str:
    addr = str(getattr(driver, "_cdp_debugger_url", None) or "127.0.0.1:9222").strip()
    if "://" in addr:
        addr = addr.split("://", 1)[1]
    return f"http://{addr}".rstrip("/")


def _http_list_tabs(driver) -> List[Dict[str, Any]]:
    """Chrome /json：列出所有页签 URL，无需 switch_to，避免误抢当前页签。"""
    try:
        import json
        import urllib.request

        with urllib.request.urlopen(f"{_debugger_http_base(driver)}/json", timeout=5) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for t in raw if isinstance(raw, list) else []:
        if not isinstance(t, dict):
            continue
        if str(t.get("type") or "") not in ("page", "tab"):
            continue
        url = str(t.get("url") or "")
        if not _is_usable_page_url(url):
            continue
        tid = str(t.get("id") or t.get("targetId") or "")
        out.append({"targetId": tid, "id": tid, "url": url})
    return out


def _list_page_targets(driver) -> List[Dict[str, Any]]:
    tabs = _http_list_tabs(driver)
    if tabs:
        return tabs
    try:
        raw = driver.execute_cdp_cmd("Target.getTargets", {}) or {}
    except Exception:
        raw = {}
    out: List[Dict[str, Any]] = []
    for t in raw.get("targetInfos") or []:
        if not isinstance(t, dict):
            continue
        if str(t.get("type") or "") not in ("page", "tab"):
            continue
        url = str(t.get("url") or "")
        if not _is_usable_page_url(url):
            continue
        tid = str(t.get("targetId") or t.get("id") or "")
        out.append({"targetId": tid, "id": tid, "url": url})
    return out


def _score_site_tab(tab_url: str, want_url: str) -> int:
    if not _same_site(tab_url, want_url):
        return 0
    if _urls_match(tab_url, want_url):
        return 100
    want_path = _path_of(want_url)
    tab_path = _path_of(tab_url)
    if want_path and tab_path:
        if tab_path == want_path or tab_path.startswith(want_path + "/") or want_path.startswith(tab_path + "/"):
            return 80
    return 40


def find_existing_site_tab(driver, url: str) -> Optional[Dict[str, Any]]:
    """找已打开该网站的页签：精确路径 > 同路径前缀 > 同站点。"""
    url = (url or "").strip()
    if not url:
        return None
    best = None
    best_sc = 0
    for t in _list_page_targets(driver):
        sc = _score_site_tab(str(t.get("url") or ""), url)
        if sc > best_sc:
            best, best_sc = t, sc
    return best if best_sc > 0 else None


def _handle_for_target_id(driver, target_id: str) -> Optional[str]:
    tid = str(target_id or "").strip()
    if not tid:
        return None
    for attempt in range(2):
        try:
            handles = list(driver.window_handles or [])
        except Exception:
            handles = []
        for h in handles:
            if h == tid:
                return h
            if len(tid) >= 8 and len(h) >= 8 and (h.startswith(tid[:8]) or tid.startswith(h[:8])):
                return h
        if attempt == 0:
            time.sleep(0.12)
    return None


def _switch_to_target_id(driver, target_id: str) -> bool:
    """切到指定 target 对应页签；不调用 Target.activateTarget。"""
    handle = _handle_for_target_id(driver, target_id)
    if not handle:
        return False
    try:
        with preserve_os_focus():
            driver.switch_to.window(handle)
        return True
    except Exception:
        return False


def _switch_selenium_to_target(driver, target: Dict[str, Any]) -> bool:
    tid = str(target.get("targetId") or target.get("id") or "")
    if tid and _switch_to_target_id(driver, tid):
        return True
    want_url = str(target.get("url") or "")
    if not want_url:
        return False
    for t in _http_list_tabs(driver):
        turl = str(t.get("url") or "")
        if not (_urls_match(turl, want_url) or _same_site(turl, want_url)):
            continue
        tid2 = str(t.get("targetId") or t.get("id") or "")
        if tid2 and _switch_to_target_id(driver, tid2):
            return True
    return False


def _navigate_current_tab(driver, url: str) -> None:
    """只在当前 Selenium 页签跳转，绝不 createTarget / new_window。"""
    url = (url or "").strip()
    if not url:
        return
    try:
        driver.execute_cdp_cmd("Page.navigate", {"url": url})
    except Exception:
        try:
            driver.get(url)
        except Exception as e:
            logger.warning("当前页签导航失败: %s", e)
            return
    for _ in range(40):
        try:
            cur = (current_href(driver) or "").strip()
            if cur and (url.startswith("about:") or cur != "about:blank"):
                if _same_site(cur, url) or _urls_match(cur, url):
                    break
        except Exception:
            pass
        time.sleep(0.08)


def _create_site_tab(driver, url: str) -> Optional[str]:
    """无同站点页签时新建后台页签并导航；返回 targetId / handle。"""
    url = (url or "").strip()
    if not url:
        return None
    try:
        created = driver.execute_cdp_cmd(
            "Target.createTarget",
            {"url": "about:blank", "background": True},
        )
        tid = str(created.get("targetId") or "")
        if tid and _switch_to_target_id(driver, tid):
            _navigate_current_tab(driver, url)
            return tid
    except Exception as exc:
        logger.warning("Target.createTarget 失败: %s", exc)

    try:
        before = set(driver.window_handles or [])
        with preserve_os_focus():
            driver.execute_script("window.open('about:blank','_blank');")
        time.sleep(0.35)
        after = list(driver.window_handles or [])
        new_handles = [h for h in after if h not in before]
        if new_handles:
            with preserve_os_focus():
                driver.switch_to.window(new_handles[-1])
            _navigate_current_tab(driver, url)
            return new_handles[-1]
    except Exception as exc:
        logger.warning("window.open 新建页签失败: %s", exc)
    return None


def open_url_new_tab(driver, url: str) -> None:
    """兼容旧名：优先复用同站点页签，否则新建页签。"""
    navigate_or_activate(driver, url)


def current_href(driver) -> str:
    try:
        href = driver.execute_script("return String(location.href || '')")
        if href:
            return str(href)
    except Exception:
        pass
    try:
        return str(driver.current_url or "")
    except Exception:
        return ""


def navigate_or_activate(driver, url: str, *, timeout: float = 8.0) -> bool:
    """
    发布导航：
    1. 在已打开页签中找与目标 URL 同域名的页签，切过去并在该页签内跳转（不占用无关页签）
    2. 若没有同域名页签，才新建后台页签再打开
    3. 不调用 Target.activateTarget，尽量避免抢当前前台页签

    返回 True 表示复用了已有同站点页签；False 表示新建了页签。
    """
    url = (url or "").strip()
    if not url:
        return False

    found = find_existing_site_tab(driver, url)
    if found:
        tid = str(found.get("targetId") or found.get("id") or "")
        old = str(found.get("url") or "")
        if not _switch_selenium_to_target(driver, found):
            logger.warning("已找到同站点页签 %s (target=%s) 但未能切到 Selenium 句柄", old, tid[:12])
        cur = current_href(driver)
        if not _urls_match(cur, url):
            logger.info("复用同站点页签 %s → %s", old, url)
            _navigate_current_tab(driver, url)
        else:
            logger.info("复用同站点页签（已在目标页）: %s", cur or url)
        return True

    logger.info("未找到同站点页签，新建页签打开 %s", url)
    created = _create_site_tab(driver, url)
    if not created:
        logger.warning("无法新建页签: %s", url)
        return False
    return False


def wait_landed(
    driver,
    *,
    hosts: Sequence[str],
    paths: Sequence[str] = (),
    timeout: float = 16.0,
) -> str:
    """等到 location 落到指定站点；超时仍返回最后看到的 href。"""
    deadline = time.time() + max(4.0, timeout)
    last = ""
    host_needles = tuple(h.lower() for h in hosts if h)
    path_needles = tuple(p.lower() for p in paths if p)
    while time.time() < deadline:
        last = current_href(driver)
        low = last.lower()
        host_ok = any(h in low for h in host_needles) if host_needles else True
        path_ok = (not path_needles) or any(p in low for p in path_needles)
        if host_ok and path_ok and last:
            return last
        time.sleep(0.35)
    return last


def wait_css(driver, css: str, timeout: float = 20):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, css))
    )


_INSERT_TEXT_JS = """
const root = arguments[0];
const text = String(arguments[1] || '');
const clearFirst = !!arguments[2];
function pickEditable(n) {
  if (!n) return null;
  const tag = String(n.tagName || '').toUpperCase();
  if (tag === 'TEXTAREA' || tag === 'INPUT') return n;
  if (n.isContentEditable && (n.getAttribute('role') === 'textbox' || n.className && String(n.className).includes('DraftEditor'))) return n;
  const inner = n.querySelector && n.querySelector(
    '[contenteditable="true"][role="textbox"], .public-DraftEditor-content[contenteditable="true"], [contenteditable="true"]'
  );
  if (inner) return inner;
  if (n.isContentEditable) return n;
  return n;
}
const el = pickEditable(root);
if (!el) return { ok: false, got: '' };
try { el.click(); } catch (_) {}
el.focus && el.focus();
const tag = String(el.tagName || '').toUpperCase();
if (tag === 'TEXTAREA' || tag === 'INPUT') {
  el.value = clearFirst ? text : ((el.value || '') + text);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: true, got: String(el.value || '') };
}
const sel = window.getSelection();
function selectAll() {
  const range = document.createRange();
  range.selectNodeContents(el);
  sel.removeAllRanges();
  sel.addRange(range);
}
if (clearFirst) {
  selectAll();
  try { document.execCommand('selectAll', false, null); } catch (_) {}
  try { document.execCommand('delete', false, null); } catch (_) {}
}
selectAll();
let inserted = false;
try { inserted = !!document.execCommand('insertText', false, text); } catch (_) {}
if (!inserted) {
  try {
    el.dispatchEvent(new InputEvent('beforeinput', {
      bubbles: true, cancelable: true, inputType: 'insertText', data: text
    }));
    el.dispatchEvent(new InputEvent('input', {
      bubbles: true, inputType: 'insertText', data: text
    }));
  } catch (_) {}
}
const got = String(el.innerText || el.textContent || '').replace(/\\u200b/g, '');
return { ok: true, got: got };
"""


def _norm_editor_text(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch not in "\u200b\u200c\u200d\ufeff").strip()


def typed_text_is_valid(got: str, expected: str) -> bool:
    """写入后核对：不要私用区乱码，也不要「动之动」这类 Draft/IME 垃圾。"""
    got_n = _norm_editor_text(got).replace("\n", "")
    exp_n = _norm_editor_text(expected).replace("\n", "")
    if any(0xE000 <= ord(c) <= 0xF8FF for c in got_n):
        return False
    if not exp_n:
        return True
    head = exp_n[: min(16, len(exp_n))]
    if head and head not in got_n:
        return False
    if "动之动" not in exp_n and got_n.count("动之动") >= 2:
        return False
    if "动后动" not in exp_n and got_n.count("动后动") >= 2:
        return False
    if len(got_n) > max(len(exp_n) * 2, len(exp_n) + 24) and got_n.count("动") >= 8:
        return False
    return True


def read_editor_text(driver, element) -> str:
    try:
        return str(
            driver.execute_script(
                """
const root = arguments[0];
if (!root) return '';
const el = (root.querySelector && root.querySelector('[contenteditable="true"]')) || root;
return String(el.innerText || el.value || el.textContent || '').replace(/\\u200b/g, '');
""",
                element,
            )
            or ""
        )
    except Exception:
        try:
            return str(element.text or "")
        except Exception:
            return ""

_PICK_FILE_INPUT_JS = """
const prefer = arguments[0] || 'any';
const nodes = Array.from(document.querySelectorAll('input[type="file"]'));
let best = -1, bestScore = -1;
for (let i = 0; i < nodes.length; i++) {
  const inp = nodes[i];
  if (inp.disabled) continue;
  const accept = String(inp.accept || '').toLowerCase();
  let score = 1;
  if (prefer === 'image') {
    if (accept.includes('video') && !accept.includes('image') && !accept.includes('*')) continue;
    if (accept.includes('image') || !accept) score = 10;
  } else if (prefer === 'video') {
    if (accept.includes('image') && !accept.includes('video') && !accept.includes('*')) continue;
    if (accept.includes('video') || !accept || accept.includes('*')) score = 10;
  }
  if (score > bestScore) { bestScore = score; best = i; }
}
return best;
"""


def find_file_inputs(driver, prefer: str = "any") -> list:
    """
    prefer: any | image | video
    一次 JS 选中最佳 input，避免对每个 file 节点做 CDP get_attribute。
    """
    from selenium.webdriver.common.by import By

    try:
        idx = driver.execute_script(_PICK_FILE_INPUT_JS, prefer)
        idx = int(idx if idx is not None else -1)
    except Exception:
        idx = -1
    if idx < 0:
        return []
    try:
        inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
    except Exception:
        return []
    if 0 <= idx < len(inputs):
        return [inputs[idx]]
    return list(inputs[:1])


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

    total = max(0.1, a + random.random() * max(0.0, b - a))
    end = time.time() + total
    while time.time() < end:
        raise_if_publish_aborted()
        time.sleep(min(0.2, max(0.05, end - time.time())))


# 长文粘贴进 CDP 编辑区时，若像 Markdown 则转成适合社交平台的纯文本
PASTE_MARKDOWN_MIN_LEN = 300


def is_markdown(text: str) -> bool:
    """判断一段文本是否很有可能是 Markdown。"""
    if not text or len(text) < 8:
        return False
    score = 0
    if re.search(r"^#{1,6}\s+\S+", text, flags=re.MULTILINE):
        score += 2
    if re.search(r"\*\*[^*]+\*\*|~~[^~]+~~", text):
        score += 2
    if re.search(r"\[.+?\]\(https?://\S+\)", text):
        score += 2
    if re.search(r"^\s*[-*+]\s+\S+|^\s*>\s+\S+", text, flags=re.MULTILINE):
        score += 1
    if re.search(r"^[-\*_]{3,}\s*$", text, flags=re.MULTILINE):
        score += 1
    if re.search(r"```", text):
        score += 2
    return score >= 2


def clean_markdown_for_social(text: str) -> str:
    """去掉 Markdown 语法，保留可读正文（链接保留 URL）。"""
    if not text:
        return ""
    s = text.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"```[^\n]*\n([\s\S]*?)```", r"\1", s)
    s = re.sub(r"`([^`\n]+)`", r"\1", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"__(.+?)__", r"\1", s)
    s = re.sub(r"~~(.+?)~~", r"\1", s)
    s = re.sub(r"\*(.+?)\*", r"\1", s)
    s = re.sub(r"_(.+?)_", r"\1", s)
    s = re.sub(r"!\[(.+?)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 \2", s)
    s = re.sub(r"^>\s?", "", s, flags=re.MULTILINE)
    s = re.sub(r"^#{1,6}\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"^[\-\*_]{3,}\s*$", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\s*[-*+]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\s*\d+\.\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def process_text_before_send(text: str) -> str:
    """超长粘贴：疑似 Markdown 时清洗后再写入 CDP 编辑区。"""
    if not text or len(text) <= PASTE_MARKDOWN_MIN_LEN:
        return text
    if is_markdown(text):
        cleaned = clean_markdown_for_social(text)
        if cleaned and cleaned != text:
            logger.info(
                "CDP 长文 Markdown 已清洗: %d -> %d 字",
                len(text),
                len(cleaned),
            )
        return cleaned or text
    return text


def sanitize_typed_text(text: str) -> str:
    """去掉 Selenium Keys 私用区和控制符，避免广场正文出现 a 这类乱码。"""
    if not text:
        return ""
    # Cmd/Ctrl+A、Backspace 被当成正文插入时的完整序列
    for meta in ("\ue03d", "\ue009"):  # COMMAND, CONTROL
        for letter in ("a", "A"):
            text = text.replace(meta + letter + "\ue003", "")
            text = text.replace(meta + letter + "\ue017", "")  # DELETE
            text = text.replace(meta + letter, "")
        text = text.replace(meta + "\ue010", "")  # END
    out: list[str] = []
    for ch in text:
        o = ord(ch)
        if 0xE000 <= o <= 0xF8FF:
            continue
        if o < 32 and ch not in "\n\t":
            continue
        if o in (0x7F, 0x200B, 0x200C, 0x200D, 0xFEFF, 0x00AD):
            continue
        out.append(ch)
    return process_text_before_send("".join(out))


_CLEAR_EDITOR_JS = """
const el = arguments[0];
if (!el) return false;
try { el.click(); } catch (_) {}
el.focus && el.focus();
if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
  try { el.select(); } catch (_) {}
  el.value = '';
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
}
try {
  const sel = window.getSelection();
  const range = document.createRange();
  range.selectNodeContents(el);
  sel.removeAllRanges();
  sel.addRange(range);
  document.execCommand('delete', false, null);
} catch (_) {}
const left = String(el.innerText || el.textContent || '').replace(/\\s+/g, '');
if (left) {
  try { el.textContent = ''; } catch (_) {}
}
el.dispatchEvent(new InputEvent('input', { bubbles: true, data: '' }));
return true;
"""

_CARET_END_JS = """
const el = arguments[0];
if (!el) return;
el.focus && el.focus();
if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
  const len = (el.value || '').length;
  try { el.setSelectionRange(len, len); } catch (_) {}
  return;
}
const sel = window.getSelection();
const range = document.createRange();
range.selectNodeContents(el);
range.collapse(false);
sel.removeAllRanges();
sel.addRange(range);
"""


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
    """一次写入正文，并核对结果，避免乱码/Draft 垃圾留在输入框。"""
    text = sanitize_typed_text(text)
    if not text:
        return
    try:
        element.click()
    except Exception:
        try:
            driver.execute_script("arguments[0].click(); arguments[0].focus();", element)
        except Exception:
            pass
    human_pause(0.08, 0.18)

    def _write() -> str:
        got = ""
        try:
            res = driver.execute_script(_INSERT_TEXT_JS, element, text, bool(clear_first))
            if isinstance(res, dict):
                got = str(res.get("got") or "")
            elif res:
                got = read_editor_text(driver, element)
        except Exception:
            got = ""
        if typed_text_is_valid(got, text):
            return got
        try:
            driver.execute_script(_CLEAR_EDITOR_JS, element)
        except Exception:
            pass
        try:
            res = driver.execute_script(_INSERT_TEXT_JS, element, text, True)
            if isinstance(res, dict):
                got = str(res.get("got") or "")
            else:
                got = read_editor_text(driver, element)
        except Exception:
            got = read_editor_text(driver, element)
        return got

    got = _write()
    if typed_text_is_valid(got, text):
        human_pause(0.08, 0.16)
        return
    logger.warning(
        "编辑区写入结果异常，已清空。期望前20字=%r 实际=%r",
        text[:20],
        (got or "")[:40],
    )
    try:
        driver.execute_script(_CLEAR_EDITOR_JS, element)
    except Exception:
        pass
    raise RuntimeError("编辑区写入异常（乱码或垃圾文本），已中止")


_APPEND_TEXT_AT_CARET_JS = """
const root = arguments[0];
const text = String(arguments[1] || '');
function pickEditable(n) {
  if (!n) return null;
  const tag = String(n.tagName || '').toUpperCase();
  if (tag === 'TEXTAREA' || tag === 'INPUT') return n;
  if (n.isContentEditable && (n.getAttribute('role') === 'textbox' || n.className && String(n.className).includes('DraftEditor'))) return n;
  const inner = n.querySelector && n.querySelector(
    '[contenteditable="true"][role="textbox"], .public-DraftEditor-content[contenteditable="true"], [contenteditable="true"]'
  );
  if (inner) return inner;
  if (n.isContentEditable) return n;
  return n;
}
const el = pickEditable(root);
if (!el) return { ok: false, got: '' };
try { el.click(); } catch (_) {}
el.focus && el.focus();
const tag = String(el.tagName || '').toUpperCase();
if (tag === 'TEXTAREA' || tag === 'INPUT') {
  el.value = String(el.value || '') + text;
  try {
    const len = (el.value || '').length;
    el.setSelectionRange(len, len);
  } catch (_) {}
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: true, got: String(el.value || '') };
}
const sel = window.getSelection();
if (!sel) return { ok: false, got: '' };
const range = document.createRange();
range.selectNodeContents(el);
range.collapse(false);
sel.removeAllRanges();
sel.addRange(range);
let inserted = false;
try { inserted = !!document.execCommand('insertText', false, text); } catch (_) {}
if (!inserted) {
  try {
    el.dispatchEvent(new InputEvent('beforeinput', {
      bubbles: true, cancelable: true, inputType: 'insertText', data: text
    }));
    el.dispatchEvent(new InputEvent('input', {
      bubbles: true, inputType: 'insertText', data: text
    }));
  } catch (_) {}
}
const got = String(el.innerText || el.textContent || '').replace(/\\u200b/g, '');
return { ok: true, got: got };
"""


def append_text_at_caret(driver, element, text: str) -> str:
    """在光标处追加文本（不选中全文），适合 Draft.js 逐段写入。"""
    chunk = sanitize_typed_text(text)
    if not chunk:
        return read_editor_text(driver, element)
    try:
        res = driver.execute_script(_APPEND_TEXT_AT_CARET_JS, element, chunk)
        if isinstance(res, dict):
            return str(res.get("got") or "")
    except Exception:
        pass
    return read_editor_text(driver, element)


def multiline_content_preserved(got: str, expected: str) -> bool:
    """核对非空行是否按顺序出现在编辑区（允许 X 合并尾部空行、轻微空格差异）。"""
    exp = sanitize_typed_text(expected or "")
    if not exp:
        return True
    got_s = sanitize_typed_text(got or "")
    pos = 0
    seen = 0
    for raw in exp.split("\n"):
        line = raw.strip()
        if not line:
            continue
        idx = got_s.find(line, pos)
        if idx < 0:
            return False
        pos = idx + len(line)
        seen += 1
    if seen == 0:
        return True
    compact_exp = exp.replace("\n", "").replace(" ", "")
    compact_got = got_s.replace("\n", "").replace(" ", "")
    head = compact_exp[: min(12, len(compact_exp))]
    if head and head not in compact_got:
        return False
    if any(0xE000 <= ord(c) <= 0xF8FF for c in compact_got):
        return False
    return True


def _split_x_compose_chunks(text: str) -> List[str]:
    """把一段正文拆成 X 发帖用的句/段块（不含空串）。"""
    t = (text or "").strip()
    if not t:
        return []
    lines = [ln.strip() for ln in t.split("\n") if ln.strip()]
    if len(lines) > 1:
        return lines
    parts = re.split(r"(?<=[。！？!?…])\s*", t)
    parts = [p.strip() for p in parts if p.strip()]
    return parts if len(parts) > 1 else [t]


def prepare_x_compose_text(text: str) -> str:
    """
    X 发帖正文：保留原文换行与空行；仅对「单行无换行」长文按句号拆行。
    """
    body = sanitize_typed_text(text or "")
    if not body.strip():
        return ""
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    if "\n" in body:
        lines = [ln.rstrip() for ln in body.split("\n")]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines) if lines else ""
    chunks = _split_x_compose_chunks(body.strip())
    return "\n".join(chunks)


def read_x_compose_inner_text(driver) -> str:
    """读 X 编辑器 innerText（提交前以它为准，不是肉眼 DOM）。"""
    try:
        return str(
            driver.execute_script(
                """
const el = document.querySelector('[data-testid="tweetTextarea_0"] [contenteditable="true"]')
  || document.querySelector('div[role="textbox"][data-testid^="tweetTextarea"] [contenteditable="true"]')
  || document.querySelector('[data-testid="tweetTextarea_0"]');
return el ? String(el.innerText || el.textContent || '').replace(/\\u200b/g, '') : '';
"""
            )
            or ""
        )
    except Exception:
        return ""


_FOCUS_X_EDITOR_JS = """
const el = (function(root) {
  if (!root) return null;
  const tag = String(root.tagName || '').toUpperCase();
  if (tag === 'TEXTAREA' || tag === 'INPUT') return root;
  if (root.isContentEditable) return root;
  const inner = root.querySelector && root.querySelector(
    '[data-testid="tweetTextarea_0"] [contenteditable="true"], '
    + 'div[role="textbox"] [contenteditable="true"], '
    + '.public-DraftEditor-content[contenteditable="true"], '
    + '[contenteditable="true"][role="textbox"], [contenteditable="true"]'
  );
  return inner || root;
})(arguments[0]);
if (!el) return { ok: false, reason: 'no_editable' };
try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (_) {}
try { el.click(); } catch (_) {}
try { el.focus(); } catch (_) {}
const sel = window.getSelection();
if (sel) {
  try {
    const range = document.createRange();
    range.selectNodeContents(el);
    range.collapse(false);
    sel.removeAllRanges();
    sel.addRange(range);
  } catch (_) {}
}
const ae = document.activeElement;
const focused = ae === el || (ae && el.contains(ae));
return { ok: !!focused, activeTag: String(ae && ae.tagName || '') };
"""


def _activate_driver_tab_for_input(driver) -> None:
    """写入前短暂激活当前 Selenium 页签（Draft.js 在后台 tab 常吞 Input.insertText）。"""
    try:
        handle = str(driver.current_window_handle or "")
    except Exception:
        handle = ""
    if not handle:
        return
    for t in _list_page_targets(driver):
        tid = str(t.get("targetId") or t.get("id") or "")
        if not tid:
            continue
        if tid == handle or (len(tid) >= 8 and len(handle) >= 8 and (handle.startswith(tid[:8]) or tid.startswith(handle[:8]))):
            try:
                driver.execute_cdp_cmd("Target.activateTarget", {"targetId": tid})
                time.sleep(0.1)
            except Exception:
                pass
            return


def _ensure_x_editor_focus(driver, element) -> bool:
    try:
        with preserve_os_focus():
            _activate_driver_tab_for_input(driver)
            res = driver.execute_script(_FOCUS_X_EDITOR_JS, element)
        return bool(isinstance(res, dict) and res.get("ok"))
    except Exception:
        return False


def _read_x_text_from_element(driver, element) -> str:
    try:
        return str(
            driver.execute_script(
                """
const el = (function(root) {
  if (!root) return null;
  if (root.isContentEditable) return root;
  const inner = root.querySelector && root.querySelector(
    '[contenteditable="true"][role="textbox"], .public-DraftEditor-content[contenteditable="true"], [contenteditable="true"]'
  );
  return inner || root;
})(arguments[0]);
return el ? String(el.innerText || el.textContent || '').replace(/\\u200b/g, '') : '';
""",
                element,
            )
            or ""
        )
    except Exception:
        return ""


def _read_x_compose_got(driver, element) -> str:
    got = _norm_editor_newlines(_read_x_text_from_element(driver, element))
    if got.strip():
        return got
    return _norm_editor_newlines(
        read_x_compose_inner_text(driver) or read_editor_text(driver, element)
    )


def _norm_editor_newlines(s: str) -> str:
    return sanitize_typed_text(s or "").replace("\r\n", "\n").replace("\r", "\n")


def _compose_lines_for_match(text: str) -> List[str]:
    """行级比对：保留段落间空行，忽略首尾空行与行尾空格。"""
    lines = [ln.rstrip() for ln in _norm_editor_newlines(text).split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def editor_lines_match(got: str, expected: str) -> bool:
    return _compose_lines_for_match(got) == _compose_lines_for_match(expected)


def read_gate_editor_text(driver, element) -> str:
    """Gate ProseMirror：以 data-pai-editor 的 innerText 为准。"""
    try:
        raw = driver.execute_script(
            """
const el = document.querySelector('[data-pai-editor="1"]') || arguments[0];
if (!el) return '';
return String(el.innerText || el.textContent || '').replace(/\\u200b/g, '');
""",
            element,
        )
        return _norm_editor_newlines(str(raw or ""))
    except Exception:
        return _norm_editor_newlines(read_editor_text(driver, element))


def gate_body_acceptable(got: str, expected: str) -> bool:
    """Gate 验收：行结构一致，或非空行顺序一致且字数接近（空行数 ProseMirror 可能略有差异）。"""
    body = _norm_editor_newlines(expected)
    got_s = _norm_editor_newlines(got)
    if not got_s.strip():
        return False
    if editor_lines_match(got_s, body):
        return True
    if not multiline_content_preserved(got_s, body):
        return False
    exp_len = len(body.strip())
    got_len = len(got_s.strip())
    if exp_len <= 0:
        return True
    return got_len >= max(int(exp_len * 0.88), exp_len - 40)


def _insert_exact_newlines_at_caret(driver, element, body: str) -> None:
    """按 split('\\n') 边界逐段 insertText，每个边界恰好一个 \\n（与原文一致）。"""
    segments = body.split("\n")
    for i, seg in enumerate(segments):
        if seg:
            append_text_at_caret(driver, element, seg)
            human_pause(0.02, 0.05)
        if i < len(segments) - 1:
            append_text_at_caret(driver, element, "\n")
            human_pause(0.03, 0.07)


def _gate_body_needs_segmented_newlines(body: str) -> bool:
    """原文含空行或段落间距时，整段 insertText 常会丢空行。"""
    norm = _norm_editor_newlines(body)
    if "\n\n" in norm:
        return True
    return any(not ln.strip() for ln in norm.split("\n"))


def type_text_gate(driver, element, text: str) -> str:
    """
    Gate 广场：无空行时整段 insertText 优先；含空行时先逐段 insertText+\\n，失败时不清空已输入内容。
    """
    body = _norm_editor_newlines(text)
    if not body.strip() and "\n" not in body:
        return ""

    def _focus() -> None:
        try:
            element.click()
        except Exception:
            driver.execute_script("arguments[0].click(); arguments[0].focus();", element)
        _ensure_x_editor_focus(driver, element)
        human_pause(0.06, 0.14)

    def _clear() -> None:
        try:
            driver.execute_script(_CLEAR_EDITOR_JS, element)
        except Exception:
            pass
        human_pause(0.08, 0.16)

    last_got = ""
    notes: List[str] = []

    def _try(label: str, write) -> bool:
        nonlocal last_got
        try:
            write()
            human_pause(0.12, 0.24)
            last_got = read_gate_editor_text(driver, element)
            if gate_body_acceptable(last_got, body):
                logger.info(
                    "Gate 正文写入 OK（%s）· 期望 %s 行 / 读到 %s 行",
                    label,
                    len(_compose_lines_for_match(body)),
                    len(_compose_lines_for_match(last_got)),
                )
                return True
            notes.append(
                f"{label}: exp={len(_compose_lines_for_match(body))} "
                f"got={len(_compose_lines_for_match(last_got))} "
                f"len={len(last_got.strip())}/{len(body.strip())}"
            )
        except Exception as exc:
            notes.append(f"{label}={exc}")
        return False

    seg_fn = lambda: (_clear(), _focus(), _insert_exact_newlines_at_caret(driver, element, body))
    js_fn = lambda: (_clear(), _focus(), driver.execute_script(_INSERT_TEXT_JS, element, body, True))
    cdp_fn = lambda: (_clear(), _focus(), driver.execute_cdp_cmd("Input.insertText", {"text": body}))
    if _gate_body_needs_segmented_newlines(body):
        order = (("seg", seg_fn), ("js", js_fn), ("cdp", cdp_fn))
    else:
        order = (("cdp", cdp_fn), ("js", js_fn), ("seg", seg_fn))
    for label, fn in order:
        if _try(label, fn):
            return last_got

    if last_got.strip() and multiline_content_preserved(last_got, body):
        logger.warning(
            "Gate 行空行与原文略有差异，正文顺序已对齐，继续发布（%s）",
            notes[-1] if notes else "",
        )
        return last_got

    raise RuntimeError(
        "Gate 正文写入失败（编辑区内容已保留便于核对）。"
        f" {' · '.join(notes[:4])}"
    )


def type_text_exact_multiline(
    driver,
    element,
    text: str,
    *,
    clear_first: bool = True,
) -> str:
    """Bitget 等：同 Gate 策略，可在外层选择 gate 专用入口。"""
    _ = clear_first
    return type_text_gate(driver, element, text)


def _paragraph_gap_signature(text: str) -> List[int]:
    """相邻两段非空正文之间的空行数（与原文 \\n 结构对应）。"""
    lines = _norm_editor_newlines(text).split("\n")
    sig: List[int] = []
    i = 0
    n = len(lines)
    while i < n:
        while i < n and not lines[i].strip():
            i += 1
        if i >= n:
            break
        j = i + 1
        blanks = 0
        while j < n and not lines[j].strip():
            blanks += 1
            j += 1
        if j < n:
            sig.append(blanks)
        i = j if j > i + 1 else i + 1
    return sig


def x_editor_line_structure_ok(got: str, expected: str) -> bool:
    """核对 innerText：非空行顺序一致；段落空行尽量一致，X Draft 合并空行时仍允许发帖。"""
    exp = _norm_editor_newlines(expected)
    got_s = _norm_editor_newlines(got)
    if not exp.strip():
        return True
    exp_lines = [ln.strip() for ln in exp.split("\n") if ln.strip()]
    got_lines = [ln.strip() for ln in got_s.split("\n") if ln.strip()]
    if not multiline_content_preserved(got_s, exp):
        return False
    if got_lines != exp_lines:
        return False
    if len(exp_lines) <= 1:
        return True
    if _paragraph_gap_signature(got_s) == _paragraph_gap_signature(exp) and "\n" in got_s:
        return True
    # 非空行已全部对齐：X 常把段落间多个空行压成单个换行，不再因此中止
    return "\n" in got_s or len(got_lines) > 1


def _type_x_draft_paragraphs(
    driver,
    element,
    body: str,
    *,
    clear_first: bool = True,
) -> str:
    """
    X Draft.js：空行用 Enter（新段落/空块），相邻行用 Shift+Enter。
    insertText 的 \\n 在 X 上常被压成一行，故不用整段粘贴。
    """
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.keys import Keys

    lines = _norm_editor_newlines(body).split("\n")
    if clear_first:
        try:
            driver.execute_script(_CLEAR_EDITOR_JS, element)
        except Exception:
            pass
        human_pause(0.12, 0.25)
    if not _ensure_x_editor_focus(driver, element):
        human_pause(0.1, 0.2)
        _ensure_x_editor_focus(driver, element)
    human_pause(0.08, 0.16)

    i = 0
    n = len(lines)
    while i < n:
        if not lines[i]:
            ActionChains(driver).click(element).send_keys(Keys.ENTER).perform()
            human_pause(0.06, 0.12)
            i += 1
            continue
        append_text_at_caret(driver, element, lines[i])
        human_pause(0.03, 0.08)
        i += 1
        if i >= n:
            break
        blanks = 0
        while i < n and not lines[i]:
            ActionChains(driver).click(element).send_keys(Keys.ENTER).perform()
            human_pause(0.06, 0.12)
            blanks += 1
            i += 1
        if i < n and blanks == 0:
            ActionChains(driver).click(element).key_down(Keys.SHIFT).send_keys(
                Keys.ENTER
            ).key_up(Keys.SHIFT).perform()
            human_pause(0.04, 0.09)
    human_pause(0.12, 0.22)
    return _read_x_compose_got(driver, element)


def _type_x_multiline_into_element(
    driver,
    element,
    body: str,
    *,
    clear_first: bool = True,
) -> str:
    """优先 Draft Enter/Shift+Enter；失败再退回 insertText 分段。"""
    got = _type_x_draft_paragraphs(
        driver, element, body, clear_first=clear_first
    )
    if x_editor_line_structure_ok(got, body):
        return got
    if clear_first:
        try:
            driver.execute_script(_CLEAR_EDITOR_JS, element)
        except Exception:
            pass
        human_pause(0.1, 0.2)
    _ensure_x_editor_focus(driver, element)
    segments = body.split("\n")
    for i, seg in enumerate(segments):
        if seg:
            append_text_at_caret(driver, element, seg)
            human_pause(0.02, 0.06)
        if i < len(segments) - 1:
            append_text_at_caret(driver, element, "\n")
            human_pause(0.04, 0.08)
    human_pause(0.1, 0.2)
    return _read_x_compose_got(driver, element)


def type_x_compose_via_cdp_insert_text(
    driver,
    element,
    text: str,
    *,
    clear_first: bool = True,
) -> str:
    """
    X 发帖：多策略写入 Draft.js（含真实 \\n），写后读 innerText 核对。
    CDP Input.insertText 在 X 上常因焦点不在编辑区而空写，故优先逐行 execCommand。
    """
    body = prepare_x_compose_text(text)
    if not body:
        return ""

    attempts: List[str] = []

    def _try_draft_keys() -> str:
        got = _type_x_draft_paragraphs(
            driver, element, body, clear_first=clear_first
        )
        if x_editor_line_structure_ok(got, body):
            return got
        attempts.append(
            f"draft gaps={_paragraph_gap_signature(got)} "
            f"exp={_paragraph_gap_signature(body)} "
            f"text={(got or '')[:40]!r}"
        )
        return ""

    def _try_multiline() -> str:
        got = _type_x_multiline_into_element(
            driver, element, body, clear_first=clear_first
        )
        if x_editor_line_structure_ok(got, body):
            return got
        attempts.append(f"multiline={(got or '')[:48]!r}")
        return ""

    def _try_insert_js() -> str:
        if clear_first:
            try:
                driver.execute_script(_CLEAR_EDITOR_JS, element)
            except Exception:
                pass
            human_pause(0.12, 0.25)
        _ensure_x_editor_focus(driver, element)
        human_pause(0.08, 0.16)
        try:
            res = driver.execute_script(_INSERT_TEXT_JS, element, body, True)
            if isinstance(res, dict) and not res.get("ok", True):
                attempts.append("insert_js=not_ok")
                return ""
        except Exception as exc:
            attempts.append(f"insert_js={exc}")
            return ""
        human_pause(0.12, 0.24)
        got = _read_x_compose_got(driver, element)
        if x_editor_line_structure_ok(got, body):
            return got
        attempts.append(f"insert_js={(got or '')[:48]!r}")
        return ""

    for fn in (_try_draft_keys, _try_multiline, _try_insert_js):
        got = fn()
        if got:
            logger.info(
                "X 正文写入成功 · %s 行 · 段落空行 %s",
                got.count("\n") + 1,
                _paragraph_gap_signature(got),
            )
            return got

    final_got = _read_x_compose_got(driver, element)
    try:
        driver.execute_script(_CLEAR_EDITOR_JS, element)
    except Exception:
        pass
    detail = "; ".join(attempts[:4]) if attempts else "无有效写入"
    raise RuntimeError(
        "X 正文写入异常（innerText 未保留换行），已中止。"
        f" 期望前40={body[:40]!r} innerText前60={(final_got or '')[:60]!r}"
        f" [{detail}]"
    )


def type_text_multiline_soft_breaks(
    driver,
    element,
    text: str,
    *,
    clear_first: bool = True,
    line_pause: Tuple[float, float] = (0.03, 0.09),
    break_pause: Tuple[float, float] = (0.05, 0.12),
    newline_via_insert: bool = False,
    min_breaks_between_blocks: int = 1,
) -> str:
    """
    逐块 insertText 写入；换行用 insertText 插入 \\n（X Draft 比 Shift+Enter 更稳）。
    newline_via_insert=True 时按 min_breaks_between_blocks 在块之间插入至少 N 个换行（2=空一行）。
    """
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.keys import Keys

    body = sanitize_typed_text(text or "")
    if not body:
        return ""
    if clear_first:
        try:
            driver.execute_script(_CLEAR_EDITOR_JS, element)
        except Exception:
            pass
        human_pause(0.12, 0.25)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click(); arguments[0].focus();", element)
    human_pause(0.08, 0.18)

    got = ""
    if newline_via_insert:
        segments = body.split("\n")
        for i, seg in enumerate(segments):
            if seg:
                got = append_text_at_caret(driver, element, seg)
                human_pause(*line_pause)
            if i < len(segments) - 1:
                gap = 1
                if seg and min_breaks_between_blocks > gap:
                    gap = min_breaks_between_blocks
                got = append_text_at_caret(driver, element, "\n" * gap)
                human_pause(*break_pause)
    else:
        lines = body.split("\n")
        for i, line in enumerate(lines):
            if line:
                got = append_text_at_caret(driver, element, line)
                human_pause(*line_pause)
            if i < len(lines) - 1:
                ActionChains(driver).click(element).key_down(Keys.SHIFT).send_keys(
                    Keys.ENTER
                ).key_up(Keys.SHIFT).perform()
                human_pause(*break_pause)
                got = read_editor_text(driver, element)

    got = read_editor_text(driver, element)
    if multiline_content_preserved(got, body):
        return got
    logger.warning(
        "多行写入结果异常。期望前20字=%r 实际=%r",
        body[:20],
        (got or "")[:60],
    )
    try:
        driver.execute_script(_CLEAR_EDITOR_JS, element)
    except Exception:
        pass
    raise RuntimeError(
        f"X 正文写入异常（空行/格式丢失），已中止: 期望前20={body[:20]!r} 实际={(got or '')[:40]!r}"
    )
