# coding=utf-8
"""CDP 发布共用：连接已登录 Chrome、复用末页签导航、传媒体。"""

from __future__ import annotations

import logging
import os
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

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

    addr = debugger_url.strip()
    options = Options()
    options.add_experimental_option("debuggerAddress", addr)
    driver = webdriver.Chrome(options=options)
    try:
        driver._cdp_debugger_url = addr  # type: ignore[attr-defined]
    except Exception:
        pass
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

    time.sleep(max(0.1, a + random.random() * max(0.0, b - a)))


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
    return "".join(out)


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
    X 发帖正文：段间仅单换行 \\n（X 会吃掉连续空行）。
    多行原文保留行序；单行多句按句号拆行；连续空行压成单 \\n。
    """
    body = sanitize_typed_text(text or "").strip()
    if not body:
        return ""
    body = re.sub(r"\n\s*\n+", "\n", body)
    body = re.sub(r"\n{2,}", "\n", body)
    lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
    if len(lines) > 1:
        return "\n".join(lines)
    chunks = _split_x_compose_chunks(body)
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


def _norm_editor_newlines(s: str) -> str:
    return sanitize_typed_text(s or "").replace("\r\n", "\n").replace("\r", "\n")


def x_editor_line_structure_ok(got: str, expected: str) -> bool:
    """核对 innerText：多行预期时编辑区须含 \\n，且非空行顺序一致。"""
    exp = _norm_editor_newlines(expected)
    got_s = _norm_editor_newlines(got)
    if not exp:
        return True
    exp_lines = [ln.strip() for ln in exp.split("\n") if ln.strip()]
    got_lines = [ln.strip() for ln in got_s.split("\n") if ln.strip()]
    if not multiline_content_preserved(got_s, exp):
        return False
    if len(exp_lines) <= 1:
        return True
    if "\n" not in got_s:
        return False
    if got_lines != exp_lines:
        return False
    return True


def type_x_compose_via_cdp_insert_text(
    driver,
    element,
    text: str,
    *,
    clear_first: bool = True,
) -> str:
    """
    X 发帖：焦点处 CDP Input.insertText 一次写入（含真实 \\n）。
    不用 value 赋值；写后读 tweetTextarea innerText 核对。
    """
    body = prepare_x_compose_text(text)
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
    try:
        driver.execute_script(
            "const el=arguments[0]; if(el&&el.focus) el.focus();", element
        )
    except Exception:
        pass
    human_pause(0.05, 0.12)
    inserted = False
    try:
        driver.execute_cdp_cmd("Input.insertText", {"text": body})
        inserted = True
    except Exception as exc:
        logger.warning("CDP Input.insertText 失败，回退 execCommand insertText: %s", exc)
    if not inserted:
        try:
            driver.execute_script(_INSERT_TEXT_JS, element, body, False)
        except Exception as exc:
            raise RuntimeError(f"X 正文写入失败: {exc}") from exc
    human_pause(0.1, 0.22)
    got = _norm_editor_newlines(
        read_x_compose_inner_text(driver) or read_editor_text(driver, element)
    )
    if not x_editor_line_structure_ok(got, body):
        logger.warning(
            "X innerText 与预期不符。期望=%r innerText=%r",
            body[:80],
            (got or "")[:120],
        )
        try:
            driver.execute_script(_CLEAR_EDITOR_JS, element)
        except Exception:
            pass
        raise RuntimeError(
            "X 正文写入异常（innerText 未保留换行），已中止。"
            f" 期望前40={body[:40]!r} innerText前60={(got or '')[:60]!r}"
        )
    return got


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
        idx = 0
        while idx < len(segments):
            seg = segments[idx]
            if seg:
                got = append_text_at_caret(driver, element, seg)
                human_pause(*line_pause)
            nxt = idx + 1
            while nxt < len(segments) and not segments[nxt]:
                nxt += 1
            if nxt < len(segments):
                nl = max(1, nxt - idx)
                if seg and min_breaks_between_blocks > nl:
                    nl = min_breaks_between_blocks
                got = append_text_at_caret(driver, element, "\n" * nl)
                human_pause(*break_pause)
            idx = nxt if nxt > idx else idx + 1
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
