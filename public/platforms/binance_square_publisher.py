# coding=utf-8
"""币安广场 CDP 发布：文本 + 图片 + 视频（需 Chrome 已登录）。"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from typing import Dict, List, Optional, Sequence

from public.platforms.cdp_common import (
    connect_cdp,
    find_file_inputs,
    human_pause,
    normalize_media_paths,
    open_url_new_tab,
    split_media,
)

logger = logging.getLogger(__name__)

DEFAULT_SQUARE_URL = "https://www.binance.com/zh-CN/square"

_COMPOSE_LABELS = (
    "发帖",
    "发布",
    "发帖子",
    "写点什么",
    "分享你的想法",
    "Share your idea",
    "Create post",
    "Post",
    "New post",
)

_SUBMIT_LABELS = ("发布", "发文", "发帖", "Post", "Publish", "发送", "Submit")

_DISMISS_COOKIE_JS = r"""
(function() {
  const words = ['接受', '同意', 'Allow', 'Accept', 'OK', '确定', 'Got it'];
  const nodes = document.querySelectorAll('button, a, [role="button"]');
  for (const el of nodes) {
    const t = (el.innerText || el.textContent || '').trim();
    if (!t || t.length > 24) continue;
    if (words.some(w => t === w || t.includes(w))) {
      try { el.click(); return true; } catch (_) {}
    }
  }
  return false;
})();
"""

_FIND_COMPOSE_JS = r"""
const labels = arguments[0];
function visible(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 8 || r.height < 8) return false;
  const st = window.getComputedStyle(el);
  if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) < 0.05) return false;
  return true;
}
function score(el) {
  const t = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim();
  if (!t) return 0;
  for (let i = 0; i < labels.length; i++) {
    if (t.includes(labels[i])) return 100 - i;
  }
  return 0;
}
const nodes = Array.from(document.querySelectorAll('button, a, [role="button"], div[role="button"]'));
let best = null, bestSc = 0;
for (const el of nodes) {
  if (!visible(el)) continue;
  const sc = score(el);
  if (sc > bestSc) { bestSc = sc; best = el; }
}
if (!best) {
  const placeholders = ['分享', 'Share', '说点什么', '想法'];
  const inputs = Array.from(document.querySelectorAll(
    'textarea, input[type="text"], [contenteditable="true"], [role="textbox"]'
  ));
  for (const el of inputs) {
    if (!visible(el)) continue;
    const ph = (el.getAttribute('placeholder') || el.getAttribute('aria-label') || '').trim();
    if (placeholders.some(p => ph.includes(p))) { best = el; break; }
  }
}
if (!best) return null;
best.setAttribute('data-pai-compose', '1');
return true;
"""

_FIND_EDITOR_JS = r"""
function visible(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 24 || r.height < 12) return false;
  const st = window.getComputedStyle(el);
  if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) < 0.05) return false;
  return true;
}
function markEditor(ed, root) {
  ed.setAttribute('data-pai-editor', '1');
  if (root) root.setAttribute('data-pai-editor-root', '1');
  return true;
}
function pickEditable(root) {
  if (!root || !visible(root)) return null;
  if (root.isContentEditable || root.getAttribute('contenteditable') === 'true') return root;
  return root.querySelector(
    '[contenteditable="true"], [role="textbox"], textarea, .ProseMirror, .ql-editor'
  );
}
const shortRoots = [];
for (const sel of [
  '.short-editor-editor',
  '[class*="short-editor-editor"]',
  '[class*="shortEditor-editor"]',
  '[class*="short-editor"]',
]) {
  document.querySelectorAll(sel).forEach(el => shortRoots.push(el));
}
for (const root of shortRoots) {
  const ed = pickEditable(root);
  if (ed && visible(ed)) return markEditor(ed, root);
}
for (const sel of [
  'div[contenteditable="true"][role="textbox"]',
  'div[contenteditable="true"]',
  'textarea',
  '[role="textbox"]',
]) {
  for (const el of document.querySelectorAll(sel)) {
    if (!visible(el)) continue;
    if (el.closest('[contenteditable="false"]')) continue;
    const root = el.closest('[class*="short-editor"]') || el.closest('.short-editor-editor');
    return markEditor(el, root);
  }
}
return false;
"""

_ACTIVATE_SHORT_EDITOR_JS = r"""
function visible(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 24 || r.height < 12) return false;
  const st = window.getComputedStyle(el);
  if (st.visibility === 'hidden' || st.display === 'none') return false;
  return true;
}
const roots = document.querySelectorAll(
  '.short-editor-editor, [class*="short-editor-editor"], [class*="short-editor"]'
);
for (const root of roots) {
  if (!visible(root)) continue;
  try { root.click(); } catch (_) {}
  const ed = root.querySelector('[contenteditable="true"], [role="textbox"], textarea')
    || (root.isContentEditable ? root : null);
  if (ed && visible(ed)) {
    try { ed.click(); ed.focus(); return true; } catch (_) {}
  }
}
return false;
"""

_SET_EDITOR_TEXT_JS = r"""
const text = arguments[0];
const el = document.querySelector('[data-pai-editor="1"]');
if (!el) return false;
el.focus();
if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
  el.value = text;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
} else {
  try {
    document.execCommand('selectAll', false, null);
    document.execCommand('insertText', false, text);
  } catch (_) {
    el.innerText = text;
  }
  el.dispatchEvent(new InputEvent('input', { bubbles: true, data: text }));
}
return true;
"""

_CLICK_MEDIA_BUTTON_JS = r"""
const prefer = arguments[0] || 'image';
const imageWords = ['图片', '图像', '添加图片', '上传图片', 'Photo', 'Image', '相册', 'Add image'];
const videoWords = ['视频', '添加视频', '上传视频', 'Video', 'Add video', '影片'];
const words = prefer === 'video' ? videoWords.concat(imageWords) : imageWords;
const hints = prefer === 'video'
  ? ['video', 'media', 'upload', 'attach']
  : ['image', 'photo', 'picture', 'upload', 'media', 'attach', 'album'];
function visible(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 8 || r.height < 8) return false;
  const st = window.getComputedStyle(el);
  if (st.visibility === 'hidden' || st.display === 'none') return false;
  return true;
}
function tryClick(el) {
  try { el.click(); return true; } catch (_) { return false; }
}
function matchBtn(el) {
  const t = (el.innerText || el.textContent || '').trim();
  const label = (el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
  const cls = String(el.className || '') + ' ' + (el.getAttribute('class') || '');
  const blob = (t + ' ' + label + ' ' + cls).toLowerCase();
  if (words.some(w => t.includes(w) || label.includes(w))) return true;
  return hints.some(h => blob.includes(h));
}
const root = document.querySelector('[data-pai-editor-root="1"]')
  || document.querySelector('[class*="short-editor"]');
const scopes = root ? [root, document] : [document];
for (const scope of scopes) {
  const nodes = scope.querySelectorAll('button, [role="button"], label');
  for (const el of nodes) {
    if (!visible(el)) continue;
    if (matchBtn(el) && tryClick(el)) return true;
  }
}
return false;
"""

_CLICK_SUBMIT_JS = r"""
const labels = arguments[0];
function visible(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 8 || r.height < 8) return false;
  const st = window.getComputedStyle(el);
  if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) < 0.05) return false;
  return true;
}
function disabled(el) {
  return el.disabled || el.getAttribute('aria-disabled') === 'true';
}
function findIn(scope) {
  const nodes = Array.from(scope.querySelectorAll(
    'button, [role="button"], a, [class*="btn"], [class*="button"]'
  ));
  let best = null, bestSc = 0;
  for (const el of nodes) {
    if (!visible(el) || disabled(el)) continue;
    const t = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim();
    const cls = String(el.className || '') + ' ' + (el.getAttribute('class') || '');
    const blob = (t + ' ' + cls).toLowerCase();
    if (!t && !blob) continue;
    for (let i = 0; i < labels.length; i++) {
      if (t === labels[i] || t.includes(labels[i]) || blob.includes(labels[i].toLowerCase())) {
        const sc = 90 - i;
        if (sc > bestSc) { bestSc = sc; best = el; }
      }
    }
  }
  return best;
}
const toolbarSel = '.editor-toolbar-container, [class*="editor-toolbar-container"]';
const root = document.querySelector('[data-pai-editor-root="1"]')
  || document.querySelector('[class*="short-editor"]');
const scopes = [];
const toolbars = [];
if (root) root.querySelectorAll(toolbarSel).forEach(el => toolbars.push(el));
document.querySelectorAll(toolbarSel).forEach(el => {
  if (!toolbars.includes(el)) toolbars.push(el);
});
for (const tb of toolbars) {
  if (tb.nextElementSibling) scopes.push(tb.nextElementSibling);
  if (tb.parentElement) scopes.push(tb.parentElement);
  scopes.push(tb);
}
if (root) scopes.push(root);
let best = null, bestSc = 0;
for (const scope of scopes) {
  const hit = findIn(scope);
  if (!hit) continue;
  const t = (hit.innerText || hit.textContent || '').trim();
  let sc = 0;
  for (let i = 0; i < labels.length; i++) {
    if (t === labels[i] || t.includes(labels[i])) { sc = 90 - i; break; }
  }
  if (sc > bestSc) { bestSc = sc; best = hit; }
}
if (!best) return false;
try {
  best.scrollIntoView({block:'center', inline:'center'});
  best.click();
  return true;
} catch (_) {
  return false;
}
"""


class BinanceSquarePublisher:
    def __init__(
        self,
        debugger_url: str = "127.0.0.1:9222",
        square_url: str = DEFAULT_SQUARE_URL,
        close_driver: bool = False,
        wait_sec: float = 8.0,
        media_upload_wait: float = 25.0,
    ):
        self.debugger_url = debugger_url
        self.square_url = square_url
        self.close_driver = close_driver
        self.wait_sec = wait_sec
        self.media_upload_wait = media_upload_wait
        self.driver = None

    def publish(
        self,
        text: str = "",
        media_paths: Optional[Sequence[str]] = None,
        *,
        submit: bool = True,
        title: str = "",
    ) -> Dict:
        body = (text or "").strip()
        if title and title.strip():
            t = title.strip()
            if t not in body:
                body = f"{t}\n\n{body}".strip() if body else t

        media = normalize_media_paths(media_paths)
        images, videos = split_media(media)
        if not body and not media:
            return {
                "success": False,
                "error": "正文与媒体不能同时为空",
                "platform": "binance_square",
            }

        steps: List[str] = []
        own = self.driver is None
        try:
            if own:
                self.driver = connect_cdp(self.debugger_url)
            driver = self.driver
            open_url_new_tab(driver, self.square_url)
            steps.append("square")
            human_pause(1.0, 1.8)
            try:
                driver.execute_script(_DISMISS_COOKIE_JS)
            except Exception:
                pass

            if not self._wait_for_editor(driver, self.wait_sec):
                alt = self.square_url.rstrip("/").split("?")[0] + "?tab=Home"
                open_url_new_tab(driver, alt)
                human_pause(1.0, 1.6)
                if not self._wait_for_editor(driver, self.wait_sec):
                    found = driver.execute_script(_FIND_COMPOSE_JS, list(_COMPOSE_LABELS))
                    if found and self._click_marked(driver, "compose"):
                        steps.append("compose")
                        human_pause(0.8, 1.4)
                        self._wait_for_editor(driver, self.wait_sec)

            if not driver.execute_script(_FIND_EDITOR_JS):
                return {
                    "success": False,
                    "error": "未找到广场编辑区，请确认已登录币安广场",
                    "steps": steps,
                    "platform": "binance_square",
                }
            steps.append("editor")

            if body:
                self._type_text(driver, body)
                steps.append("text")
                human_pause(0.4, 0.9)

            if images:
                n = self._upload_media(driver, images, prefer="image")
                steps.append(f"images:{n}")
                human_pause(1.0, 2.0)

            if videos:
                n = self._upload_media(driver, videos, prefer="video")
                steps.append(f"videos:{n}")
                human_pause(2.0, 4.0)
                self._wait_media_settle(driver, timeout=max(30.0, self.media_upload_wait))

            if not submit:
                return {
                    "success": True,
                    "submitted": False,
                    "steps": steps + ["dry_run"],
                    "platform": "binance_square",
                    "platform_name": "币安广场",
                }

            human_pause(0.5, 1.0)
            urls_before = self._collect_post_urls(driver)
            clicked = False
            for _ in range(4):
                if driver.execute_script(_CLICK_SUBMIT_JS, list(_SUBMIT_LABELS)):
                    clicked = True
                    break
                human_pause(0.4, 0.8)
            if not clicked:
                return {
                    "success": False,
                    "error": "未找到或无法点击「发布」按钮",
                    "steps": steps,
                    "platform": "binance_square",
                }
            steps.append("submit")
            human_pause(2.0, 3.5)

            post_url = ""
            try:
                cur = (driver.current_url or "").strip()
                if "/square/post/" in cur.lower():
                    post_url = cur.split("#")[0]
            except Exception:
                pass
            if not post_url:
                new_urls = sorted(self._collect_post_urls(driver) - urls_before)
                if new_urls:
                    post_url = new_urls[-1]

            return {
                "success": True,
                "submitted": True,
                "url": post_url,
                "steps": steps,
                "platform": "binance_square",
                "platform_name": "币安广场",
                "media_count": len(media),
            }
        except Exception as e:
            logger.exception("币安广场发布失败")
            return {
                "success": False,
                "error": str(e),
                "steps": steps,
                "platform": "binance_square",
            }
        finally:
            if own and self.close_driver and self.driver is not None:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None

    def _wait_for_editor(self, driver, timeout: float) -> bool:
        deadline = time.time() + max(6.0, timeout)
        while time.time() < deadline:
            if driver.execute_script(_FIND_EDITOR_JS):
                return True
            try:
                driver.execute_script(_ACTIVATE_SHORT_EDITOR_JS)
            except Exception:
                pass
            human_pause(0.35, 0.65)
        return False

    def _click_marked(self, driver, attr: str) -> bool:
        sel = f'[data-pai-{attr}="1"]'
        try:
            return bool(
                driver.execute_script(
                    """
                    const el = document.querySelector(arguments[0]);
                    if (!el) return false;
                    el.scrollIntoView({block:'center'});
                    el.click();
                    return true;
                    """,
                    sel,
                )
            )
        except Exception:
            return False

    def _type_text(self, driver, text: str) -> None:
        from selenium.webdriver.common.by import By

        for _ in range(4):
            if not driver.execute_script(_FIND_EDITOR_JS):
                human_pause(0.3, 0.6)
                continue
            if driver.execute_script(_SET_EDITOR_TEXT_JS, text):
                return
            try:
                editor = driver.find_element(By.CSS_SELECTOR, '[data-pai-editor="1"]')
                editor.click()
                editor.send_keys(text)
                return
            except Exception:
                human_pause(0.3, 0.6)
        raise RuntimeError("无法写入广场正文编辑区")

    def _upload_media(self, driver, paths: List[str], prefer: str = "image") -> int:
        if not paths:
            return 0
        # 先尝试唤出对应媒体按钮
        try:
            driver.execute_script(_CLICK_MEDIA_BUTTON_JS, prefer)
            human_pause(0.4, 0.9)
        except Exception:
            pass

        uploaded = 0
        for ap in paths:
            try:
                inputs = find_file_inputs(driver, prefer=prefer)
                if not inputs:
                    driver.execute_script(_CLICK_MEDIA_BUTTON_JS, prefer)
                    human_pause(0.5, 1.0)
                    inputs = find_file_inputs(driver, prefer=prefer)
                if inputs:
                    inputs[0].send_keys(ap)
                    uploaded += 1
                    time.sleep(self.media_upload_wait if prefer == "video" else min(8.0, self.media_upload_wait))
                    continue
            except Exception as e:
                logger.warning("file input 上传失败 %s: %s", ap, e)

            # macOS 图片可回退剪贴板
            if prefer == "image" and self._paste_image_clipboard(driver, ap):
                uploaded += 1
        return uploaded

    def _paste_image_clipboard(self, driver, path: str) -> bool:
        if sys.platform != "darwin":
            return False
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.common.keys import Keys

        ext = os.path.splitext(path)[1].lower()
        if ext == ".png":
            fmt = "«class PNGf»"
        elif ext in (".jpg", ".jpeg"):
            fmt = "JPEG picture"
        elif ext == ".gif":
            fmt = "GIF picture"
        else:
            return False
        script = f'set the clipboard to (read (POSIX file "{path}") as {fmt})'
        try:
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
        except Exception:
            return False
        if not driver.execute_script(_FIND_EDITOR_JS):
            return False
        from selenium.webdriver.common.by import By

        try:
            editor = driver.find_element(By.CSS_SELECTOR, '[data-pai-editor="1"]')
            driver.execute_script("arguments[0].click(); arguments[0].focus();", editor)
            ActionChains(driver).key_down(Keys.COMMAND).send_keys("v").key_up(Keys.COMMAND).perform()
            human_pause(1.0, 1.8)
            return True
        except Exception:
            return False

    def _wait_media_settle(self, driver, timeout: float = 40.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                busy = driver.execute_script(
                    """
                    const nodes = document.querySelectorAll(
                      '[role="progressbar"], [class*="progress"], [class*="uploading"], [class*="loading"]'
                    );
                    for (const el of nodes) {
                      const r = el.getBoundingClientRect();
                      if (r.width > 4 && r.height > 4) return true;
                    }
                    return false;
                    """
                )
                if not busy:
                    return
            except Exception:
                return
            time.sleep(0.6)

    def _collect_post_urls(self, driver) -> set:
        try:
            hrefs = driver.execute_script(
                """
                const out = new Set();
                for (const a of document.querySelectorAll('a[href*="/square/post/"]')) {
                  const h = (a.href || '').split('#')[0];
                  if (h) out.add(h);
                }
                try {
                  const cur = location.href || '';
                  if (cur.toLowerCase().includes('/square/post/')) out.add(cur.split('#')[0]);
                } catch (_) {}
                return Array.from(out);
                """
            )
            if isinstance(hrefs, list):
                return {str(h) for h in hrefs if h}
        except Exception:
            pass
        return set()
