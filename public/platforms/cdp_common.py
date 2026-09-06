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


def _try_silent_cdp_goto(driver, url: str) -> bool:
    """优先走 auto-deal-eth 静默 CDP（不 activate / 不 switch_to）。"""
    try:
        eth = Path(__file__).resolve().parents[2].parent / "auto-deal-eth"
        if eth.is_dir() and str(eth) not in sys.path:
            sys.path.insert(0, str(eth))
        from binance.cdp_navigation import cdp_goto

        cdp_goto(
            driver,
            url,
            page_load_timeout=60,
            log_prefix="publish-cdp",
            last_tab=True,
        )
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
