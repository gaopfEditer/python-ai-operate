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
    current_href,
    find_file_inputs,
    human_pause,
    normalize_media_paths,
    open_url_new_tab,
    sanitize_typed_text,
    split_media,
    type_text_human,
    wait_landed,
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

_SUBMIT_LABELS = (
    "发布",
    "发文",
    "发帖",
    "发送",
    "发表",
    "确认发布",
    "立即发布",
    "Post",
    "Publish",
    "Submit",
    "Send",
    "Post now",
    "Share",
)

_PLATFORM_SITE = {
    "binance_square": (("binance.com",), ("/square",)),
    "okx": (("okx.com",), ("/orbit",)),
    "bitget": (("bitget.com",), ("/insights",)),
}

_PLATFORM_COMPOSE_EXTRA = {
    "okx": ("发文", "发动态", "写动态"),
    "bitget": ("洞察", "Insights", "写洞察", "分享观点", "发帖"),
}

_PLATFORM_SUBMIT_EXTRA = {
    "okx": ("确认发布", "确认", "发送动态", "Post now", "Submit"),
    "bitget": ("确认发布", "确认", "Post", "Submit", "发送", "发表"),
}

_PLATFORM_POST_MARKERS = {
    "binance_square": ("/square/post/",),
    "okx": ("/orbit/post/", "/orbit/insight/"),
    "bitget": ("/insights/", "/post/", "/article/"),
}

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
function badLink(el) {
  if (el.tagName !== 'A') return false;
  const h = (el.getAttribute('href') || el.href || '').toLowerCase();
  if (!h || h === '#' || h.startsWith('javascript:')) return false;
  const bad = ['ventures', '/trade', '/learn', '/support', '/about', '/download', '/campaign'];
  return bad.some(b => h.includes(b));
}
function score(el) {
  const t = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim();
  if (!t || t.length > 20) return 0;
  for (let i = 0; i < labels.length; i++) {
    const lab = labels[i];
    if (t === lab || t.replace(/\s+/g, '') === lab) return 150 - i;
    if (lab.length >= 2 && t.includes(lab)) return 100 - i;
  }
  return 0;
}
const nodes = Array.from(document.querySelectorAll('button, a, [role="button"], div[role="button"]'));
let best = null, bestSc = 0;
for (const el of nodes) {
  if (!visible(el) || badLink(el)) continue;
  let sc = score(el);
  if (!sc) continue;
  if (el.tagName === 'BUTTON' || el.getAttribute('role') === 'button') sc += 15;
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

_FIND_OKX_COMPOSE_JS = r"""
function visible(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 8 || r.height < 8) return false;
  const st = window.getComputedStyle(el);
  if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) < 0.05) return false;
  return true;
}
function inBadAnchor(el) {
  let n = el;
  while (n) {
    if (n.tagName === 'A') {
      const h = (n.getAttribute('href') || n.href || '').toLowerCase();
      if (!h || h === '#' || h.startsWith('javascript:')) {
        n = n.parentElement;
        continue;
      }
      if (h.includes('ventures')) return true;
      if (h.includes('/trade') || h.includes('/learn') || h.includes('/earn')) return true;
      if (h.includes('okx.com') && !h.includes('/orbit')) return true;
    }
    n = n.parentElement;
  }
  return false;
}
function norm(t) {
  return (t || '').trim().replace(/\s+/g, '');
}
const prefer = ['发文', '发动态'];
const selectors = ['button', '[role="button"]'];
let best = null, bestSc = 0;
for (const sel of selectors) {
  for (const el of document.querySelectorAll(sel)) {
    if (!visible(el) || inBadAnchor(el)) continue;
    if (el.tagName === 'A') continue;
    const t = norm(el.innerText || el.textContent || el.getAttribute('aria-label') || '');
    if (!t || t.length > 8) continue;
    for (let i = 0; i < prefer.length; i++) {
      if (t !== prefer[i]) continue;
      let sc = 300 - i * 10;
      if (el.tagName === 'BUTTON') sc += 20;
      if (sc > bestSc) { bestSc = sc; best = el; }
      break;
    }
  }
}
if (!best) return false;
best.setAttribute('data-pai-compose', '1');
return true;
"""

_OKX_ENSURE_ORBIT_JS = r"""
try {
  const p = (location.pathname || '').toLowerCase();
  if (p.includes('/orbit')) return true;
} catch (_) {}
return false;
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
  'textarea[placeholder*="分享" i]',
  'textarea[placeholder*="Share" i]',
  'textarea[placeholder*="说点什么" i]',
  'textarea[placeholder*="想法" i]',
  'textarea[placeholder*="Post" i]',
  'textarea',
  '[role="textbox"]',
]) {
  for (const el of document.querySelectorAll(sel)) {
    if (!visible(el)) continue;
    if (el.closest('[contenteditable="false"]')) continue;
    const root = el.closest('[class*="short-editor"]') || el.closest('.short-editor-editor')
      || el.closest('[class*="editor"]') || el.closest('[class*="Editor"]');
    return markEditor(el, root);
  }
}
return false;
"""

_FIND_BITGET_TITLE_JS = r"""
function visible(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 24 || r.height < 8) return false;
  const st = window.getComputedStyle(el);
  if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) < 0.05) return false;
  return true;
}
function hintText(el) {
  return (el.getAttribute('placeholder') || el.getAttribute('aria-label')
    || el.getAttribute('data-placeholder') || '').trim().toLowerCase();
}
function isTitleHint(el) {
  const h = hintText(el);
  return ['标题', 'title', 'topic', '主题', 'heading'].some(x => h.includes(x));
}
function markTitle(el) {
  el.setAttribute('data-pai-title', '1');
  return true;
}
for (const sel of [
  'input[placeholder*="标题" i]',
  'input[placeholder*="title" i]',
  'textarea[placeholder*="标题" i]',
  '[contenteditable="true"][placeholder*="标题" i]',
  '[contenteditable="true"][data-placeholder*="标题" i]',
  '[class*="title" i] input',
  '[class*="Title"] input',
  '[class*="title" i] textarea',
  '[class*="title" i] [contenteditable="true"]',
  '[class*="Title"] [contenteditable="true"]',
]) {
  for (const el of document.querySelectorAll(sel)) {
    if (visible(el)) return markTitle(el);
  }
}
const modal = document.querySelector('[role="dialog"], [class*="modal" i], [class*="Modal"]');
const scope = modal || document.body;
for (const el of scope.querySelectorAll('input[type="text"], input:not([type]), textarea, [contenteditable="true"]')) {
  if (!visible(el)) continue;
  if (isTitleHint(el)) return markTitle(el);
}
return false;
"""

_FIND_BITGET_FIELDS_JS = r"""
function visible(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 24 || r.height < 8) return false;
  const st = window.getComputedStyle(el);
  if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) < 0.05) return false;
  return true;
}
function hintText(el) {
  return (el.getAttribute('placeholder') || el.getAttribute('aria-label')
    || el.getAttribute('data-placeholder') || '').trim().toLowerCase();
}
function isTitleHint(el) {
  const h = hintText(el);
  return ['标题', 'title', 'topic', '主题', 'heading'].some(x => h.includes(x));
}
document.querySelectorAll('[data-pai-title]').forEach(el => el.removeAttribute('data-pai-title'));
document.querySelectorAll('[data-pai-editor]').forEach(el => el.removeAttribute('data-pai-editor'));
document.querySelectorAll('[data-pai-editor-root]').forEach(el => el.removeAttribute('data-pai-editor-root'));
for (const sel of [
  'input[placeholder*="标题" i]',
  'input[placeholder*="title" i]',
  'textarea[placeholder*="标题" i]',
  '[contenteditable="true"][placeholder*="标题" i]',
  '[class*="title" i] input',
  '[class*="title" i] textarea',
  '[class*="title" i] [contenteditable="true"]',
]) {
  for (const el of document.querySelectorAll(sel)) {
    if (!visible(el)) continue;
    el.setAttribute('data-pai-title', '1');
    break;
  }
}
if (!document.querySelector('[data-pai-title="1"]')) {
  const modal = document.querySelector('[role="dialog"], [class*="modal" i], [class*="Modal"]');
  const scope = modal || document.body;
  for (const el of scope.querySelectorAll('input[type="text"], input:not([type]), textarea, [contenteditable="true"]')) {
    if (!visible(el)) continue;
    if (isTitleHint(el)) {
      el.setAttribute('data-pai-title', '1');
      break;
    }
  }
}
let body = null, bodyArea = 0;
for (const el of document.querySelectorAll(
  '[contenteditable="true"], .ProseMirror, [role="textbox"], textarea'
)) {
  if (!visible(el)) continue;
  if (el.getAttribute('data-pai-title') === '1') continue;
  if (el.closest('[class*="title" i], [class*="Title"]')) continue;
  if (isTitleHint(el)) continue;
  const r = el.getBoundingClientRect();
  const area = r.width * r.height;
  if (area > bodyArea) { body = el; bodyArea = area; }
}
if (!body) return false;
body.setAttribute('data-pai-editor', '1');
const root = body.closest('[class*="editor" i], [class*="Editor"], [role="dialog"]');
if (root) root.setAttribute('data-pai-editor-root', '1');
return true;
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

_COUNT_EDITOR_MEDIA_JS = r"""
const prefer = arguments[0] || 'image';
const editor = document.querySelector('[data-pai-editor="1"]');
const root = document.querySelector('[data-pai-editor-root="1"]')
  || (editor ? editor.closest('[role="dialog"], [class*="modal" i], [class*="editor" i], [class*="Editor"]') : null)
  || editor?.parentElement
  || document.body;
function visible(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  return r.width > 24 && r.height > 24;
}
function isUiIcon(img) {
  const src = (img.getAttribute('src') || img.src || '').toLowerCase();
  const cls = String(img.className || '') + ' ' + (img.getAttribute('class') || '');
  if (src.includes('avatar') || src.includes('icon') || src.includes('logo') || src.includes('emoji')) return true;
  if (cls.includes('avatar') || cls.includes('icon') || cls.includes('logo')) return true;
  const r = img.getBoundingClientRect();
  if (r.width < 48 || r.height < 48) return true;
  return false;
}
let n = 0;
if (prefer === 'video') {
  for (const v of root.querySelectorAll('video')) {
    if (visible(v)) n++;
  }
  return n;
}
for (const img of root.querySelectorAll('img')) {
  if (!visible(img) || isUiIcon(img)) continue;
  const src = (img.getAttribute('src') || img.src || '').toLowerCase();
  if (src.startsWith('blob:') || src.startsWith('data:') || src.includes('upload')
      || src.includes('cdn') || src.includes('bitget') || src.includes('okex')) {
    n++;
  }
}
return n;
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

_CLICK_EXACT_PUBLISH_JS = r"""
const allowDisabled = !!arguments[0];
function vis(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 8 || r.height < 8) return false;
  const st = window.getComputedStyle(el);
  if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) < 0.05) return false;
  return true;
}
function disabled(el) {
  if (!el) return true;
  if (el.disabled) return true;
  if (el.getAttribute('aria-disabled') === 'true') return true;
  const st = window.getComputedStyle(el);
  if (st.pointerEvents === 'none') return true;
  if (/\bdisabled\b/i.test(String(el.className || ''))) return true;
  return false;
}
function isTab(el) {
  if (!el) return false;
  if (el.getAttribute('role') === 'tab') return true;
  if (el.closest('[role="tablist"]')) return true;
  const sel = el.getAttribute('aria-selected');
  if (sel === 'true' || sel === 'false') return true;
  return false;
}
function clickable(el) {
  return el.closest('button, [role="button"], [type="submit"], a, [class*="btn" i], [class*="button" i]') || el;
}
function ownShort(el) {
  // 优先读 aria-label/title（OKX/币安发布按钮的文本常在这里）
  const aria = (el.getAttribute('aria-label') || el.getAttribute('title') || '').replace(/\s+/g, '').trim();
  if (aria && aria.length <= 14) return aria;
  // 再读 innerText
  let t = '';
  for (const n of el.childNodes) {
    if (n.nodeType === 3) t += n.textContent || '';
  }
  t = (t || '').replace(/\s+/g, '').trim();
  if (t && t.length <= 8) return t;
  if (el.childElementCount === 1) {
    const c = el.firstElementChild;
    const ct = (c.innerText || c.textContent || '').replace(/\s+/g, '').trim();
    if (ct && ct.length <= 8) return ct;
  }
  const inner = (el.innerText || '').replace(/\s+/g, '').trim();
  if (inner && inner.length <= 8) return inner;
  return '';
}
function isPublishWord(t) {
  const n = (t || '').toLowerCase();
  return n === '发布' || n === '发送' || n === '确认发布' || n === '立即发布'
    || n === 'post' || n === 'publish' || n === 'submit' || n === 'submit'
    || t === '发布' || t === '发送';
}
const _COMPOSE_WORDS = new Set(['发文','发帖','发帖子','发动态','写动态']);
const editor = document.querySelector('[data-pai-editor="1"]');
const cluster = editor && editor.closest(
  '[role="dialog"], [class*="modal" i], [class*="drawer" i], [class*="popup" i], [class*="sheet" i], [class*="composer" i], [class*="short-editor"], [class*="editor" i], [data-pai-editor-root="1"]'
);
const roots = [];
if (cluster) roots.push(cluster);
if (editor && editor.parentElement) roots.push(editor.parentElement);
if (editor && editor.parentElement && editor.parentElement.parentElement) {
  roots.push(editor.parentElement.parentElement);
}
roots.push(document.body);
const seen = new Set();
const hits = [];
function consider(el) {
  if (!el || seen.has(el) || !vis(el) || isTab(el)) return;
  seen.add(el);
  const t = ownShort(el);
  // 排除开帖按钮（打开编辑器用的，不是提交）
  if (!t || _COMPOSE_WORDS.has(t)) return;
  if (!isPublishWord(t)) return;
  const btn = clickable(el);
  if (isTab(btn)) return;
  let sc = 80;
  if (cluster && cluster.contains(el)) sc += 80;
  if (btn.tagName === 'BUTTON' || btn.getAttribute('role') === 'button') sc += 20;
  if (/primary|solid|bn-button/i.test(String(btn.className || ''))) sc += 20;
  try {
    const r = btn.getBoundingClientRect();
    const er = editor ? editor.getBoundingClientRect() : r;
    if (r.left > (er.left + er.width * 0.3)) sc += 25;
    const dist = Math.hypot(r.left - er.right, r.top - er.top);
    if (dist < 420) sc += 15;
  } catch (_) {}
  hits.push({ el: btn, sc, label: t, disabled: disabled(btn) });
}
for (const root of roots) {
  const xp = document.evaluate(
    ".//*[self::button or self::span or self::div or @role='button'][normalize-space(.)='发布' or normalize-space(.)='Post' or normalize-space(.)='Publish' or normalize-space(.)='发送']",
    root, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null
  );
  for (let i = 0; i < xp.snapshotLength; i++) consider(xp.snapshotItem(i));
  root.querySelectorAll('button, [role="button"], [type="submit"], [class*="btn" i]').forEach(consider);
}
hits.sort((a, b) => b.sc - a.sc);
const nearby = hits.slice(0, 8).map(h => ({ label: h.label, score: h.sc, disabled: h.disabled }));
if (!hits.length) return { ok: false, label: '', waiting: false, candidates: nearby };
const best = hits[0];
if (best.disabled && !allowDisabled) {
  return { ok: false, label: best.label, waiting: true, disabled: true, candidates: nearby };
}
try {
  best.el.scrollIntoView({block:'center', inline:'center'});
  try { best.el.focus(); } catch (_) {}
  best.el.click();
  return { ok: true, label: best.label, score: best.sc, candidates: nearby };
} catch (_) {
  try {
    best.el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
    return { ok: true, label: best.label, score: best.sc, candidates: nearby };
  } catch (e) {
    return { ok: false, label: best.label, waiting: false, candidates: nearby };
  }
}
}
function labelOf(el) {
  if (!el) return '';
  const aria = (el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('data-bn-toast') || '').trim();
  const an = norm(aria);
  if (an && isSubmitWord(an)) return aria.replace(/\s+/g, ' ').trim();
  let own = '';
  for (const node of el.childNodes) {
    if (node.nodeType === 3) own += node.textContent || '';
  }
  own = own.replace(/\s+/g, ' ').trim();
  if (own && isSubmitWord(norm(own))) return own;
  for (const c of el.children || []) {
    if (c.closest && c.closest('[data-pai-editor="1"]')) continue;
    const ct = (c.innerText || c.textContent || '').replace(/\s+/g, ' ').trim();
    if (ct && ct.length <= 16 && isSubmitWord(norm(ct))) return ct;
  }
  const inner = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  if (inner.length <= 16) return inner;
  return an || own || '';
}
function clickTarget(el) {
  return el.closest('button, [role="button"], [type="submit"], a, [class*="btn" i], [class*="button" i]') || el;
}
function eachNode(root, cb) {
  if (!root) return;
  cb(root);
  const walk = (node) => {
    if (!node || !node.querySelectorAll) return;
    node.querySelectorAll('*').forEach((el) => {
      cb(el);
      if (el.shadowRoot) walk(el.shadowRoot);
    });
  };
  walk(root);
}
function subtreeHasSubmit(root, editor) {
  if (!root) return false;
  let hit = false;
  eachNode(root, (el) => {
    if (hit) return;
    if (!el.matches) return;
    if (!el.matches('button, [role="button"], [type="submit"], [class*="btn" i], [class*="button" i]')) return;
    if (editor && editor.contains(el)) return;
    if (!visible(el)) return;
    if (isSubmitWord(norm(labelOf(el)))) hit = true;
  });
  return hit;
}
function editorCluster(editor) {
  if (!editor) return null;
  const dialog = editor.closest(
    '[role="dialog"], [class*="modal" i], [class*="Modal"], [class*="drawer" i], [class*="popup" i], [class*="overlay" i], [class*="sheet" i], [class*="composer" i], [class*="compose" i]'
  );
  if (dialog) return dialog;
  const marked = document.querySelector('[data-pai-editor-root="1"]');
  if (marked && marked.contains(editor) && subtreeHasSubmit(marked.parentElement || marked, editor)) {
    return marked.parentElement && subtreeHasSubmit(marked.parentElement, editor) ? marked.parentElement : marked;
  }
  let n = editor.parentElement;
  for (let i = 0; i < 10 && n && n !== document.body && n !== document.documentElement; i++) {
    const box = n.getBoundingClientRect();
    if (box.height > window.innerHeight * 0.9 && box.width > window.innerWidth * 0.9) break;
    if (subtreeHasSubmit(n, editor)) return n;
    n = n.parentElement;
  }
  return (marked && marked.contains(editor) ? marked : null) || editor.parentElement;
}
function inSiteChrome(el, cluster) {
  const chrome = el.closest('header, nav, [class*="navbar" i], [class*="Navbar"], [class*="top-nav" i], [class*="side-nav" i], [class*="sidenav" i]');
  if (!chrome) return false;
  if (cluster && cluster.contains(el)) return false;
  return true;
}
function nearScore(el, editor, cluster) {
  if (!editor) return 0;
  if (cluster && cluster.contains(el)) return 100;
  if (editor.contains(el)) return 20;
  const er = editor.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  const dist = Math.hypot(
    (r.left + r.width/2) - (er.left + er.width/2),
    (r.top + r.height/2) - (er.top + er.height/2)
  );
  if (dist < 520) return 70;
  if (dist < 860) return 40;
  return 0;
}
function wordBoost(n, editorFilled) {
  const low = n.toLowerCase();
  if (editorFilled && (n === '发文' || n === '发帖' || n === '发帖子' || n === '发动态')) return -200;
  if (n === '发布' || n === '确认发布' || n === '立即发布' || low === 'post' || low === 'publish' || low === 'submit') return 50;
  if (n.includes('发布') || low.includes('publish') || low === 'send') return 35;
  if (n === '发文' || n === '发帖' || n === '发送') return 20;
  return 10;
}
function scoreBtn(el, editor, cluster, editorFilled) {
  if (inBadAnchor(el)) return 0;
  if (inSiteChrome(el, cluster)) return 0;
  if (el.getAttribute('role') === 'tab' || el.closest('[role="tablist"]')) return 0;
  const raw = labelOf(el);
  const n = norm(raw);
  const iconHit = /post|publish|submit|send|发布|发送/.test(
    String(el.getAttribute('aria-label') || el.getAttribute('title') || '')
  );
  if (!isSubmitWord(n) && !iconHit) return 0;
  const near = nearScore(el, editor, cluster);
  if (!near) return 0;
  let sc = 30 + near + wordBoost(n || norm(el.getAttribute('aria-label') || ''), editorFilled);
  const t = clickTarget(el);
  if (t.tagName === 'BUTTON' || t.getAttribute('role') === 'button' || t.getAttribute('type') === 'submit') sc += 16;
  const cls = String(t.className || '');
  if (/primary|submit|confirm|bn-button|solid/i.test(cls)) sc += 18;
  try {
    const r = el.getBoundingClientRect();
    const er = editor.getBoundingClientRect();
    if (r.left > er.left + er.width * 0.35) sc += 12;
    if (r.top <= er.top + 8) sc += 10;
  } catch (_) {}
  return sc;
}
const editor = document.querySelector('[data-pai-editor="1"]');
const cluster = editorCluster(editor);
const scopes = [];
const seenScope = new Set();
function pushScope(el) {
  if (!el || seenScope.has(el)) return;
  seenScope.add(el);
  scopes.push(el);
}
pushScope(cluster);
pushScope(document.querySelector('[data-pai-editor-root="1"]'));
if (editor) {
  pushScope(editor.parentElement);
  if (editor.parentElement) pushScope(editor.parentElement.parentElement);
}
const sel = 'button, [role="button"], [type="submit"], a, [class*="btn" i], [class*="button" i], span, div';
let best = null, bestSc = 0;
const ranked = [];
const nearby = [];
for (const scope of (scopes.length ? scopes : [document.body])) {
  eachNode(scope, (el) => {
    if (!el.matches || !el.matches(sel)) return;
    if (!visible(el)) return;
    if (editor && editor.contains(el) && el !== editor) {
      if (el.closest('[data-pai-editor="1"]') === editor && el !== clickTarget(el)) return;
    }
    const lab = labelOf(el);
    if (el.matches('button, [role="button"], [type="submit"]')) {
      nearby.push({
        label: (lab || el.getAttribute('aria-label') || '(icon)').slice(0, 24),
        tag: el.tagName,
        disabled: hardDisabled(el),
        inHeader: !!el.closest('header'),
        inCluster: !!(cluster && cluster.contains(el))
      });
    }
    if (!allowDisabled && hardDisabled(clickTarget(el))) return;
    const sc = scoreBtn(el, editor, cluster, editorFilled);
    if (sc <= 0) return;
    ranked.push({ el, sc, label: (lab || '').slice(0, 24) });
    if (sc > bestSc) { bestSc = sc; best = el; }
  });
}
document.querySelectorAll('button, [role="button"], [type="submit"]').forEach((el) => {
  if (!visible(el)) return;
  if (editor && editor.contains(el)) return;
  const lab = labelOf(el);
  nearby.push({
    label: (lab || el.getAttribute('aria-label') || '(icon)').slice(0, 24),
    tag: el.tagName,
    disabled: hardDisabled(el),
    inHeader: !!el.closest('header'),
    inCluster: !!(cluster && cluster.contains(el))
  });
  if (!allowDisabled && hardDisabled(el)) return;
  const sc = scoreBtn(el, editor, cluster, editorFilled);
  if (sc <= 0) return;
  ranked.push({ el, sc, label: (lab || '').slice(0, 24) });
  if (sc > bestSc) { bestSc = sc; best = el; }
});
ranked.sort((a, b) => b.sc - a.sc);
const candidates = ranked.slice(0, 8).map((x) => ({ label: x.label, score: x.sc }));
const nearbyOut = nearby.slice(0, 12);
if (!best || bestSc < 50) {
  return { ok: false, label: '', score: bestSc, candidates, nearby: nearbyOut };
}
const target = clickTarget(best);
try {
  target.scrollIntoView({block:'center', inline:'center'});
  try { target.focus(); } catch (_) {}
  target.click();
  return { ok: true, label: (labelOf(best) || textOfSafe(best)).slice(0, 24), score: bestSc, candidates, nearby: nearbyOut };
} catch (_) {
  try {
    target.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
    return { ok: true, label: (labelOf(best) || '').slice(0, 24), score: bestSc, candidates, nearby: nearbyOut };
  } catch (_) {
    return { ok: false, label: '', score: bestSc, candidates, nearby: nearbyOut };
  }
}
function textOfSafe(el) {
  return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
}
"""

_SUBMIT_STATE_JS = r"""
const editor = document.querySelector('[data-pai-editor="1"]');
function vis(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 4 || r.height < 4) return false;
  const st = window.getComputedStyle(el);
  if (st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) < 0.05) return false;
  return true;
}
let modalOpen = false;
if (editor) {
  const modal = editor.closest('[role="dialog"], [class*="modal" i], [class*="drawer" i], [class*="popup" i], [class*="overlay" i]');
  modalOpen = !!(modal && vis(modal));
}
const toasts = [];
for (const el of document.querySelectorAll('[role="alert"], [class*="toast" i], [class*="snackbar" i], [class*="notify" i]')) {
  if (!vis(el)) continue;
  const t = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
  if (t && t.length < 80) toasts.push(t);
}
const edText = editor ? String(editor.innerText || editor.value || '').replace(/\u200b/g, '').trim() : '';
return {
  href: String(location.href || ''),
  editorPresent: !!(editor && vis(editor)),
  editorLen: edText.length,
  modalOpen,
  toasts: toasts.slice(0, 6)
};
"""

_CLICK_BITGET_SUBMIT_JS = r"""
function visible(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 8 || r.height < 8) return false;
  const st = window.getComputedStyle(el);
  if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) < 0.05) return false;
  if (st.pointerEvents === 'none') return false;
  return true;
}
function norm(t) {
  return (t || '').trim().replace(/\s+/g, '');
}
function textOf(el) {
  if (!el || typeof el === 'string') return norm(el || '');
  return norm(el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '');
}
function hardDisabled(el) {
  if (!el) return true;
  if (el.disabled) return true;
  if (el.getAttribute('aria-disabled') === 'true') return true;
  const st = window.getComputedStyle(el);
  if (st.pointerEvents === 'none') return true;
  return false;
}
function inTopSiteNav(el) {
  const r = el.getBoundingClientRect();
  if (r.top > window.innerHeight * 0.22) return false;
  return !!el.closest('header, nav, [class*="navbar" i], [class*="Navbar"], [class*="top-nav" i], [class*="TopNav"]');
}
function rejectLabel(t) {
  return !t || t.includes('发布文章') || t.includes('发文章') || t.includes('文章');
}
function publishLabel(t) {
  return t === '发布' || t === 'Publish' || t === 'Post';
}
function modalScope() {
  const editor = document.querySelector('[data-pai-editor="1"]');
  const root = document.querySelector('[data-pai-editor-root="1"]');
  const scopes = [];
  const seen = new Set();
  const push = (el) => {
    if (!el || seen.has(el)) return;
    seen.add(el);
    scopes.push(el);
  };
  if (editor) {
    push(editor.closest(
      '[role="dialog"], [class*="modal" i], [class*="Modal"], [class*="drawer" i], [class*="popup" i], [class*="overlay" i], [class*="sheet" i], [class*="editor" i], [class*="Editor"]'
    ));
  }
  if (root) push(root);
  document.querySelectorAll('[role="dialog"], [class*="modal" i], [class*="Modal"]').forEach(push);
  if (!scopes.length) scopes.push(document.body);
  return scopes;
}
function eachNode(root, cb) {
  if (!root) return;
  cb(root);
  root.querySelectorAll('*').forEach(el => {
    cb(el);
    if (el.shadowRoot) eachNode(el.shadowRoot, cb);
  });
}
function scorePublish(el, allowDisabled) {
  const t = textOf(el);
  if (!publishLabel(t) || rejectLabel(t)) return -1;
  let sc = 200;
  const r = el.getBoundingClientRect();
  if (el.tagName === 'BUTTON' || el.getAttribute('role') === 'button') sc += 40;
  const cls = String(el.className || '');
  if (/btn|button|submit|primary/i.test(cls)) sc += 25;
  if (r.top > window.innerHeight * 0.45) sc += 60;
  if (inTopSiteNav(el)) sc -= 200;
  for (const scope of modalScope()) {
    if (scope.contains(el)) sc += 100;
  }
  if (hardDisabled(el)) {
    if (!allowDisabled) return -1;
    sc -= 40;
  }
  return sc;
}
function clickTarget(el) {
  return el.closest('button, [role="button"], a, [class*="btn" i], [class*="button" i]') || el;
}
function doClick(el) {
  const clickEl = clickTarget(el);
  clickEl.scrollIntoView({block:'center', inline:'center'});
  try { clickEl.focus(); } catch (_) {}
  try {
    clickEl.click();
    return true;
  } catch (_) {}
  try {
    const r = clickEl.getBoundingClientRect();
    const x = r.left + r.width / 2;
    const y = r.top + r.height / 2;
    const hit = document.elementFromPoint(x, y);
    if (hit) {
      hit.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y}));
      hit.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y}));
      hit.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y}));
      return true;
    }
  } catch (_) {}
  try {
    clickEl.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
    return true;
  } catch (_) {
    return false;
  }
}
const sel = 'button, [role="button"], a, div, span, p';
const allowDisabled = !!arguments[0];
let best = null, bestSc = 0;
for (const scope of modalScope()) {
  eachNode(scope, (el) => {
    if (!el.matches || !el.matches(sel)) return;
    if (!visible(el)) return;
    const sc = scorePublish(el, allowDisabled);
    if (sc > bestSc) { bestSc = sc; best = el; }
  });
}
if (!best || bestSc < 30) {
  const xpath = document.evaluate(
    "//*[normalize-space(.)='发布' and not(contains(normalize-space(.),'发布文章'))]",
    document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null
  );
  for (let i = 0; i < xpath.snapshotLength; i++) {
    const el = xpath.snapshotItem(i);
    if (!visible(el)) continue;
    const sc = scorePublish(el, allowDisabled);
    if (sc > bestSc) { bestSc = sc; best = el; }
  }
}
if (!best || bestSc < 30) return false;
return doClick(best);
"""

_SYNC_BITGET_FORM_JS = r"""
function fire(el) {
  if (!el) return;
  try { el.dispatchEvent(new Event('input', {bubbles:true})); } catch (_) {}
  try { el.dispatchEvent(new Event('change', {bubbles:true})); } catch (_) {}
  try { el.dispatchEvent(new Event('blur', {bubbles:true})); } catch (_) {}
}
fire(document.querySelector('[data-pai-title="1"]'));
fire(document.querySelector('[data-pai-editor="1"]'));
return true;
"""

_DEBUG_BITGET_SUBMIT_JS = r"""
function norm(t) { return (t || '').trim().replace(/\s+/g, ''); }
const out = [];
for (const el of document.querySelectorAll('button, [role="button"], a, span, div')) {
  const t = norm(el.innerText || el.textContent || '');
  if (!t || !t.includes('发')) continue;
  const r = el.getBoundingClientRect();
  if (r.width < 8 || r.height < 8) continue;
  out.push({
    tag: el.tagName,
    text: t.slice(0, 12),
    top: Math.round(r.top),
    disabled: !!(el.disabled || el.getAttribute('aria-disabled') === 'true'),
    inModal: !!el.closest('[role="dialog"], [class*="modal" i], [class*="Modal"]'),
  });
}
return out.slice(0, 20);
"""

_CLICK_SUBMIT_JS = r"""
const labels = arguments[0] || [];
const allowDisabled = !!arguments[1];
const editorForFill = document.querySelector('[data-pai-editor="1"]');
const editorFilled = !!(editorForFill && String(editorForFill.innerText || editorForFill.value || '').replace(/\u200b/g, '').trim().length >= 8);
function visible(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 6 || r.height < 6) return false;
  const st = window.getComputedStyle(el);
  if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) < 0.05) return false;
  return true;
}
function hardDisabled(el) {
  if (!el) return true;
  if (el.disabled) return true;
  if (el.getAttribute('aria-disabled') === 'true') return true;
  return false;
}
function norm(t) {
  return String(t || '').replace(/\s+/g, '').replace(/\u200b/g, '').trim();
}
function inBadAnchor(el) {
  let n = el;
  while (n) {
    if (n.tagName === 'A') {
      const h = (n.getAttribute('href') || n.href || '').toLowerCase();
      if (!h || h === '#' || h.startsWith('javascript:')) {
        n = n.parentElement;
        continue;
      }
      if (h.includes('ventures') || h.includes('/trade') || h.includes('/learn')) return true;
    }
    n = n.parentElement;
  }
  return false;
}
function isOpenerText(n) {
  const openers = ['写点什么','分享你的想法','说点什么','有什么新鲜事','shareyouridea','whatshappening','startapost','createpost','newpost'];
  const low = n.toLowerCase();
  return openers.some(x => low === x || low.includes(x));
}
function isSubmitWord(n) {
  if (!n || n.length > 16) return false;
  if (n.includes('文章')) return false;
  if (isOpenerText(n)) return false;
  if (editorFilled && ['发文','发帖','发帖子','发动态','写动态'].includes(n)) return false;
  const zh = ['发布','发送','发表','确认发布','立即发布','发送动态'];
  if (!editorFilled) zh.push('发文','发帖','发帖子','发动态');
  if (zh.some(z => n === z || (z.length >= 2 && n.includes(z)))) return true;
  const en = n.toLowerCase();
  if (['post','publish','submit','send','postnow','share'].includes(en)) return true;
  if (/^(post|publish|submit|send)([!.]?)$/i.test(n)) return true;
  for (const lab of labels) {
    const ln = norm(lab);
    if (!ln) continue;
    if (editorFilled && ['发文','发帖','发帖子','发动态','写动态'].includes(ln)) continue;
    if (n === ln || n.toLowerCase() === ln.toLowerCase()) return true;
  }
  return false;
}
function labelOf(el) {
  if (!el) return '';
  const aria = (el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('data-bn-toast') || '').trim();
  const an = norm(aria);
  if (an && isSubmitWord(an)) return aria.replace(/\s+/g, ' ').trim();
  let own = '';
  for (const node of el.childNodes) {
    if (node.nodeType === 3) own += node.textContent || '';
  }
  own = own.replace(/\s+/g, ' ').trim();
  if (own && isSubmitWord(norm(own))) return own;
  for (const c of el.children || []) {
    if (c.closest && c.closest('[data-pai-editor="1"]')) continue;
    const ct = (c.innerText || c.textContent || '').replace(/\s+/g, ' ').trim();
    if (ct && ct.length <= 16 && isSubmitWord(norm(ct))) return ct;
  }
  const inner = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  if (inner.length <= 16) return inner;
  return an || own || '';
}
function clickTarget(el) {
  return el.closest('button, [role="button"], [type="submit"], a, [class*="btn" i], [class*="button" i]') || el;
}
function eachNode(root, cb) {
  if (!root) return;
  cb(root);
  const walk = (node) => {
    if (!node || !node.querySelectorAll) return;
    node.querySelectorAll('*').forEach((el) => {
      cb(el);
      if (el.shadowRoot) walk(el.shadowRoot);
    });
  };
  walk(root);
}
function subtreeHasSubmit(root, editor) {
  if (!root) return false;
  let hit = false;
  eachNode(root, (el) => {
    if (hit) return;
    if (!el.matches) return;
    if (!el.matches('button, [role="button"], [type="submit"], [class*="btn" i], [class*="button" i]')) return;
    if (editor && editor.contains(el)) return;
    if (!visible(el)) return;
    if (isSubmitWord(norm(labelOf(el)))) hit = true;
  });
  return hit;
}
function editorCluster(editor) {
  if (!editor) return null;
  const dialog = editor.closest(
    '[role="dialog"], [class*="modal" i], [class*="Modal"], [class*="drawer" i], [class*="popup" i], [class*="overlay" i], [class*="sheet" i], [class*="composer" i], [class*="compose" i]'
  );
  if (dialog) return dialog;
  const marked = document.querySelector('[data-pai-editor-root="1"]');
  if (marked && marked.contains(editor) && subtreeHasSubmit(marked.parentElement || marked, editor)) {
    return marked.parentElement && subtreeHasSubmit(marked.parentElement, editor) ? marked.parentElement : marked;
  }
  let n = editor.parentElement;
  for (let i = 0; i < 10 && n && n !== document.body && n !== document.documentElement; i++) {
    const box = n.getBoundingClientRect();
    if (box.height > window.innerHeight * 0.9 && box.width > window.innerWidth * 0.9) break;
    if (subtreeHasSubmit(n, editor)) return n;
    n = n.parentElement;
  }
  return (marked && marked.contains(editor) ? marked : null) || editor.parentElement;
}
function inSiteChrome(el, cluster) {
  const chrome = el.closest('header, nav, [class*="navbar" i], [class*="Navbar"], [class*="top-nav" i], [class*="side-nav" i], [class*="sidenav" i]');
  if (!chrome) return false;
  if (cluster && cluster.contains(el)) return false;
  return true;
}
function nearScore(el, editor, cluster) {
  if (!editor) return 0;
  if (cluster && cluster.contains(el)) return 100;
  if (editor.contains(el)) return 20;
  const er = editor.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  const dist = Math.hypot(
    (r.left + r.width/2) - (er.left + er.width/2),
    (r.top + r.height/2) - (er.top + er.height/2)
  );
  if (dist < 520) return 70;
  if (dist < 860) return 40;
  return 0;
}
function wordBoost(n, editorFilled) {
  const low = n.toLowerCase();
  if (editorFilled && (n === '发文' || n === '发帖' || n === '发帖子' || n === '发动态')) return -200;
  if (n === '发布' || n === '确认发布' || n === '立即发布' || low === 'post' || low === 'publish' || low === 'submit') return 50;
  if (n.includes('发布') || low.includes('publish') || low === 'send') return 35;
  if (n === '发文' || n === '发帖' || n === '发送') return 20;
  return 10;
}
function scoreBtn(el, editor, cluster, editorFilled) {
  if (inBadAnchor(el)) return 0;
  if (inSiteChrome(el, cluster)) return 0;
  if (el.getAttribute('role') === 'tab' || el.closest('[role="tablist"]')) return 0;
  const raw = labelOf(el);
  const n = norm(raw);
  const iconHit = /post|publish|submit|send|发布|发送/.test(
    String(el.getAttribute('aria-label') || el.getAttribute('title') || '')
  );
  if (!isSubmitWord(n) && !iconHit) return 0;
  const near = nearScore(el, editor, cluster);
  if (!near) return 0;
  let sc = 30 + near + wordBoost(n || norm(el.getAttribute('aria-label') || ''), editorFilled);
  const t = clickTarget(el);
  if (t.tagName === 'BUTTON' || t.getAttribute('role') === 'button' || t.getAttribute('type') === 'submit') sc += 16;
  const cls = String(t.className || '');
  if (/primary|submit|confirm|bn-button|solid/i.test(cls)) sc += 18;
  try {
    const r = el.getBoundingClientRect();
    const er = editor.getBoundingClientRect();
    if (r.left > er.left + er.width * 0.35) sc += 12;
    if (r.top <= er.top + 8) sc += 10;
  } catch (_) {}
  return sc;
}
const editor = document.querySelector('[data-pai-editor="1"]');
const cluster = editorCluster(editor);
const scopes = [];
const seenScope = new Set();
function pushScope(el) {
  if (!el || seenScope.has(el)) return;
  seenScope.add(el);
  scopes.push(el);
}
pushScope(cluster);
pushScope(document.querySelector('[data-pai-editor-root="1"]'));
if (editor) {
  pushScope(editor.parentElement);
  if (editor.parentElement) pushScope(editor.parentElement.parentElement);
}
const sel = 'button, [role="button"], [type="submit"], a, [class*="btn" i], [class*="button" i], span, div';
let best = null, bestSc = 0;
const ranked = [];
const nearby = [];
for (const scope of (scopes.length ? scopes : [document.body])) {
  eachNode(scope, (el) => {
    if (!el.matches || !el.matches(sel)) return;
    if (!visible(el)) return;
    if (editor && editor.contains(el) && el !== editor) {
      if (el.closest('[data-pai-editor="1"]') === editor && el !== clickTarget(el)) return;
    }
    const lab = labelOf(el);
    if (el.matches('button, [role="button"], [type="submit"]')) {
      nearby.push({
        label: (lab || el.getAttribute('aria-label') || '(icon)').slice(0, 24),
        tag: el.tagName,
        disabled: hardDisabled(el),
        inHeader: !!el.closest('header'),
        inCluster: !!(cluster && cluster.contains(el))
      });
    }
    if (!allowDisabled && hardDisabled(clickTarget(el))) return;
    const sc = scoreBtn(el, editor, cluster, editorFilled);
    if (sc <= 0) return;
    ranked.push({ el, sc, label: (lab || '').slice(0, 24) });
    if (sc > bestSc) { bestSc = sc; best = el; }
  });
}
document.querySelectorAll('button, [role="button"], [type="submit"]').forEach((el) => {
  if (!visible(el)) return;
  if (editor && editor.contains(el)) return;
  const lab = labelOf(el);
  nearby.push({
    label: (lab || el.getAttribute('aria-label') || '(icon)').slice(0, 24),
    tag: el.tagName,
    disabled: hardDisabled(el),
    inHeader: !!el.closest('header'),
    inCluster: !!(cluster && cluster.contains(el))
  });
  if (!allowDisabled && hardDisabled(el)) return;
  const sc = scoreBtn(el, editor, cluster, editorFilled);
  if (sc <= 0) return;
  ranked.push({ el, sc, label: (lab || '').slice(0, 24) });
  if (sc > bestSc) { bestSc = sc; best = el; }
});
ranked.sort((a, b) => b.sc - a.sc);
const candidates = ranked.slice(0, 8).map((x) => ({ label: x.label, score: x.sc }));
const nearbyOut = nearby.slice(0, 12);
if (!best || bestSc < 50) {
  return { ok: false, label: '', score: bestSc, candidates, nearby: nearbyOut };
}
const target = clickTarget(best);
try {
  target.scrollIntoView({block:'center', inline:'center'});
  try { target.focus(); } catch (_) {}
  target.click();
  return { ok: true, label: (labelOf(best) || textOfSafe(best)).slice(0, 24), score: bestSc, candidates, nearby: nearbyOut };
} catch (_) {
  try {
    target.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
    return { ok: true, label: (labelOf(best) || '').slice(0, 24), score: bestSc, candidates, nearby: nearbyOut };
  } catch (_) {
    return { ok: false, label: '', score: bestSc, candidates, nearby: nearbyOut };
  }
}
function textOfSafe(el) {
  return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
}
"""

_SUBMIT_STATE_JS = r"""
const editor = document.querySelector('[data-pai-editor="1"]');
function vis(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 4 || r.height < 4) return false;
  const st = window.getComputedStyle(el);
  if (st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) < 0.05) return false;
  return true;
}
let modalOpen = false;
if (editor) {
  const modal = editor.closest('[role="dialog"], [class*="modal" i], [class*="drawer" i], [class*="popup" i], [class*="overlay" i]');
  modalOpen = !!(modal && vis(modal));
}
const toasts = [];
for (const el of document.querySelectorAll('[role="alert"], [class*="toast" i], [class*="snackbar" i], [class*="notify" i]')) {
  if (!vis(el)) continue;
  const t = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
  if (t && t.length < 80) toasts.push(t);
}
const edText = editor ? String(editor.innerText || editor.value || '').replace(/\u200b/g, '').trim() : '';
return {
  href: String(location.href || ''),
  editorPresent: !!(editor && vis(editor)),
  editorLen: edText.length,
  modalOpen,
  toasts: toasts.slice(0, 6)
};
"""

_CLICK_BITGET_SUBMIT_JS = r"""
function visible(el) {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 8 || r.height < 8) return false;
  const st = window.getComputedStyle(el);
  if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) < 0.05) return false;
  if (st.pointerEvents === 'none') return false;
  return true;
}
function norm(t) {
  return (t || '').trim().replace(/\s+/g, '');
}
function textOf(el) {
  if (!el || typeof el === 'string') return norm(el || '');
  return norm(el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '');
}
function hardDisabled(el) {
  if (!el) return true;
  if (el.disabled) return true;
  if (el.getAttribute('aria-disabled') === 'true') return true;
  const st = window.getComputedStyle(el);
  if (st.pointerEvents === 'none') return true;
  return false;
}
function inTopSiteNav(el) {
  const r = el.getBoundingClientRect();
  if (r.top > window.innerHeight * 0.22) return false;
  return !!el.closest('header, nav, [class*="navbar" i], [class*="Navbar"], [class*="top-nav" i], [class*="TopNav"]');
}
function rejectLabel(t) {
  return !t || t.includes('发布文章') || t.includes('发文章') || t.includes('文章');
}
function publishLabel(t) {
  return t === '发布' || t === 'Publish' || t === 'Post';
}
function modalScope() {
  const editor = document.querySelector('[data-pai-editor="1"]');
  const root = document.querySelector('[data-pai-editor-root="1"]');
  const scopes = [];
  const seen = new Set();
  const push = (el) => {
    if (!el || seen.has(el)) return;
    seen.add(el);
    scopes.push(el);
  };
  if (editor) {
    push(editor.closest(
      '[role="dialog"], [class*="modal" i], [class*="Modal"], [class*="drawer" i], [class*="popup" i], [class*="overlay" i], [class*="sheet" i], [class*="editor" i], [class*="Editor"]'
    ));
  }
  if (root) push(root);
  document.querySelectorAll('[role="dialog"], [class*="modal" i], [class*="Modal"]').forEach(push);
  if (!scopes.length) scopes.push(document.body);
  return scopes;
}
function eachNode(root, cb) {
  if (!root) return;
  cb(root);
  root.querySelectorAll('*').forEach(el => {
    cb(el);
    if (el.shadowRoot) eachNode(el.shadowRoot, cb);
  });
}
function scorePublish(el, allowDisabled) {
  const t = textOf(el);
  if (!publishLabel(t) || rejectLabel(t)) return -1;
  let sc = 200;
  const r = el.getBoundingClientRect();
  if (el.tagName === 'BUTTON' || el.getAttribute('role') === 'button') sc += 40;
  const cls = String(el.className || '');
  if (/btn|button|submit|primary/i.test(cls)) sc += 25;
  if (r.top > window.innerHeight * 0.45) sc += 60;
  if (inTopSiteNav(el)) sc -= 200;
  for (const scope of modalScope()) {
    if (scope.contains(el)) sc += 100;
  }
  if (hardDisabled(el)) {
    if (!allowDisabled) return -1;
    sc -= 40;
  }
  return sc;
}
function clickTarget(el) {
  return el.closest('button, [role="button"], a, [class*="btn" i], [class*="button" i]') || el;
}
function doClick(el) {
  const clickEl = clickTarget(el);
  clickEl.scrollIntoView({block:'center', inline:'center'});
  try { clickEl.focus(); } catch (_) {}
  try {
    clickEl.click();
    return true;
  } catch (_) {}
  try {
    const r = clickEl.getBoundingClientRect();
    const x = r.left + r.width / 2;
    const y = r.top + r.height / 2;
    const hit = document.elementFromPoint(x, y);
    if (hit) {
      hit.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y}));
      hit.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y}));
      hit.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y}));
      return true;
    }
  } catch (_) {}
  try {
    clickEl.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
    return true;
  } catch (_) {
    return false;
  }
}
const sel = 'button, [role="button"], a, div, span, p';
const allowDisabled = !!arguments[0];
let best = null, bestSc = 0;
for (const scope of modalScope()) {
  eachNode(scope, (el) => {
    if (!el.matches || !el.matches(sel)) return;
    if (!visible(el)) return;
    const sc = scorePublish(el, allowDisabled);
    if (sc > bestSc) { bestSc = sc; best = el; }
  });
}
if (!best || bestSc < 30) {
  const xpath = document.evaluate(
    "//*[normalize-space(.)='发布' and not(contains(normalize-space(.),'发布文章'))]",
    document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null
  );
  for (let i = 0; i < xpath.snapshotLength; i++) {
    const el = xpath.snapshotItem(i);
    if (!visible(el)) continue;
    const sc = scorePublish(el, allowDisabled);
    if (sc > bestSc) { bestSc = sc; best = el; }
  }
}
if (!best || bestSc < 30) return false;
return doClick(best);
"""

_SYNC_BITGET_FORM_JS = r"""
function fire(el) {
  if (!el) return;
  try { el.dispatchEvent(new Event('input', {bubbles:true})); } catch (_) {}
  try { el.dispatchEvent(new Event('change', {bubbles:true})); } catch (_) {}
  try { el.dispatchEvent(new Event('blur', {bubbles:true})); } catch (_) {}
}
fire(document.querySelector('[data-pai-title="1"]'));
fire(document.querySelector('[data-pai-editor="1"]'));
return true;
"""

_DEBUG_BITGET_SUBMIT_JS = r"""
function norm(t) { return (t || '').trim().replace(/\s+/g, ''); }
const out = [];
for (const el of document.querySelectorAll('button, [role="button"], a, span, div')) {
  const t = norm(el.innerText || el.textContent || '');
  if (!t || !t.includes('发')) continue;
  const r = el.getBoundingClientRect();
  if (r.width < 8 || r.height < 8) continue;
  out.push({
    tag: el.tagName,
    text: t.slice(0, 12),
    top: Math.round(r.top),
    disabled: !!(el.disabled || el.getAttribute('aria-disabled') === 'true'),
    inModal: !!el.closest('[role="dialog"], [class*="modal" i], [class*="Modal"]'),
  });
}
return out.slice(0, 20);
"""



class BinanceSquarePublisher:
    def __init__(
        self,
        debugger_url: str = "127.0.0.1:9222",
        square_url: str = DEFAULT_SQUARE_URL,
        close_driver: bool = False,
        wait_sec: float = 8.0,
        media_upload_wait: float = 25.0,
        platform_id: str = "binance_square",
        platform_name: str = "币安广场",
    ):
        self.debugger_url = debugger_url
        self.square_url = square_url
        self.close_driver = close_driver
        self.wait_sec = wait_sec
        self.media_upload_wait = media_upload_wait
        self.platform_id = platform_id
        self.platform_name = platform_name
        extra = _PLATFORM_COMPOSE_EXTRA.get(platform_id, ())
        self.compose_labels = _COMPOSE_LABELS + extra
        extra_submit = _PLATFORM_SUBMIT_EXTRA.get(platform_id, ())
        if platform_id == "binance_square":
            # 「发文」是广场页签，发送按钮叫「发布」
            self.submit_labels = ("发布", "Post", "Publish", "发送")
        elif platform_id == "bitget":
            self.submit_labels = ("发布", "Post", "Publish") + extra_submit
        else:
            self.submit_labels = tuple(
                x for x in (_SUBMIT_LABELS + extra_submit) if x not in ("发文", "发帖")
            )
        self.post_url_markers = _PLATFORM_POST_MARKERS.get(
            platform_id, ("/square/post/",)
        )
        self.driver = None

    def _site_needles(self) -> tuple:
        return _PLATFORM_SITE.get(self.platform_id, (("example.invalid",), ()))

    def _href_on_site(self, href: str) -> bool:
        low = (href or "").lower()
        hosts, paths = self._site_needles()
        if not any(h in low for h in hosts):
            return False
        if paths and not any(p in low for p in paths):
            return False
        return True

    def _wait_on_site(self, driver, timeout: float = 16.0) -> str:
        hosts, paths = self._site_needles()
        return wait_landed(driver, hosts=hosts, paths=paths, timeout=timeout)

    def publish(
        self,
        text: str = "",
        media_paths: Optional[Sequence[str]] = None,
        *,
        submit: bool = True,
        title: str = "",
    ) -> Dict:
        body = sanitize_typed_text((text or "").strip())
        title_text = sanitize_typed_text((title or "").strip())
        if self.platform_id == "bitget":
            if not title_text and body:
                first, _, rest = body.partition("\n")
                if first.strip() and len(first.strip()) <= 120:
                    title_text = first.strip()
                    body = rest.strip()
        elif title_text and title_text not in body:
            body = f"{title_text}\n\n{body}".strip() if body else title_text

        media = normalize_media_paths(media_paths)
        images, videos = split_media(media)
        if not body and not media and not (self.platform_id == "bitget" and title_text):
            return {
                "success": False,
                "error": "正文与媒体不能同时为空",
                "platform": self.platform_id,
            }

        steps: List[str] = []
        own = self.driver is None
        try:
            if own:
                self.driver = connect_cdp(self.debugger_url)
            driver = self.driver
            logger.info("%s 打开广场 %s", self.platform_name, self.square_url)
            open_url_new_tab(driver, self.square_url)
            href = self._wait_on_site(driver, timeout=18.0)
            logger.info("%s 当前页 %s", self.platform_name, href or "(空)")
            if not self._href_on_site(href):
                return {
                    "success": False,
                    "error": f"{self.platform_name}没有打开，当前是 {href or '未知页面'}",
                    "steps": steps,
                    "platform": self.platform_id,
                }
            steps.append("square")
            human_pause(0.4, 0.8)
            try:
                driver.execute_script(_DISMISS_COOKIE_JS)
            except Exception:
                pass

            if self.platform_id == "okx":
                self._ensure_okx_orbit(driver, steps)
            elif self.platform_id == "bitget":
                self._click_compose(driver, steps)

            if not self._wait_for_editor(driver, self.wait_sec):
                if self.platform_id == "okx":
                    self._click_okx_compose(driver, steps)
                else:
                    self._click_compose(driver, steps)
                for alt in self._alt_square_urls():
                    open_url_new_tab(driver, alt)
                    human_pause(1.0, 1.6)
                    if self._wait_for_editor(driver, self.wait_sec):
                        break
                if not self._find_body_editor(driver):
                    if self.platform_id == "okx":
                        self._click_okx_compose(driver, steps)
                    else:
                        self._click_compose(driver, steps)
                    human_pause(0.8, 1.4)
                    self._wait_for_editor(driver, self.wait_sec)

            href = current_href(driver) or href
            if not self._href_on_site(href):
                return {
                    "success": False,
                    "error": f"打开过程中离开了{self.platform_name}，当前是 {href or '未知页面'}",
                    "steps": steps,
                    "platform": self.platform_id,
                }
            if not self._find_body_editor(driver):
                logger.warning("%s 未找到编辑区 @ %s", self.platform_name, href)
                return {
                    "success": False,
                    "error": f"未找到{self.platform_name}编辑区，请确认已登录（当前 {href}）",
                    "steps": steps,
                    "platform": self.platform_id,
                }
            steps.append("editor")
            logger.info("%s 已找到编辑区 @ %s", self.platform_name, href)

            if self.platform_id == "bitget":
                if title_text:
                    if self._fill_bitget_title(driver, title_text):
                        steps.append("title")
                        human_pause(0.3, 0.6)
                    elif body and title_text not in body:
                        body = f"{title_text}\n\n{body}".strip()
                        steps.append("title_in_body")
                    elif not body:
                        body = title_text
                        steps.append("title_as_body")
                if body:
                    self._type_text(driver, body, clear_first=False)
                    steps.append("text")
                    human_pause(0.4, 0.9)
                    self._sync_editor_state(driver)
                if images:
                    n = self._upload_media(driver, images, prefer="image")
                    steps.append(f"images:{n}")
                    human_pause(1.0, 2.0)
                if videos:
                    n = self._upload_media(driver, videos, prefer="video")
                    steps.append(f"videos:{n}")
                    human_pause(2.0, 4.0)
                    self._wait_media_settle(driver, timeout=max(30.0, self.media_upload_wait))
            else:
                if images:
                    logger.info("%s 上传图片 %s 张", self.platform_name, len(images))
                    n = self._upload_media(driver, images, prefer="image")
                    steps.append(f"images:{n}")
                    human_pause(0.6, 1.0)
                    self._wait_media_settle(driver, timeout=18.0)

                if videos:
                    logger.info("%s 上传视频 %s 个", self.platform_name, len(videos))
                    n = self._upload_media(driver, videos, prefer="video")
                    steps.append(f"videos:{n}")
                    human_pause(0.8, 1.4)
                    self._wait_media_settle(driver, timeout=min(20.0, max(8.0, self.media_upload_wait)))

                if body:
                    logger.info("%s 写入正文 %s 字", self.platform_name, len(body))
                    self._type_text(driver, body)
                    steps.append("text")
                    human_pause(0.2, 0.4)
                    self._sync_editor_state(driver)

            if not submit:
                return {
                    "success": True,
                    "submitted": False,
                    "steps": steps + ["dry_run"],
                    "platform": self.platform_id,
                    "platform_name": self.platform_name,
                }

            human_pause(0.3, 0.6)
            self._sync_editor_state(driver)
            if self.platform_id == "bitget":
                self._find_body_editor(driver)
                self._sync_bitget_form(driver)
                self._wait_bitget_submit_ready(driver, timeout=14.0)
            else:
                self._wait_before_submit(driver, has_media=bool(images or videos))
            urls_before = self._collect_post_urls(driver)
            logger.info("%s 准备点击发布（点击≠发出）", self.platform_name)
            clicked, click_label, cands = self._click_submit(driver)
            if not clicked:
                hint = ""
                if cands:
                    bits = [
                        f"{c.get('label') or '?'}@{c.get('score')}"
                        for c in cands[:4]
                        if isinstance(c, dict)
                    ]
                    if bits:
                        hint = f"（候选: {', '.join(bits)}）"
                err = f"能输入正文，但没点到提交按钮{hint}"
                if self.platform_id == "bitget" and not hint:
                    try:
                        dbg = driver.execute_script(_DEBUG_BITGET_SUBMIT_JS)
                        if dbg:
                            err = f"{err}（候选: {dbg[:3]}）"
                    except Exception:
                        pass
                return {
                    "success": False,
                    "error": err,
                    "steps": steps,
                    "platform": self.platform_id,
                }
            steps.append("submit")
            logger.info(
                "%s 已点击「%s」，正在确认帖子是否发出…",
                self.platform_name,
                click_label or "发布",
            )
            ok, post_url, reason = self._wait_submit_confirmed(
                driver, body=body, urls_before=urls_before
            )
            if not ok:
                err = f"已点击「{click_label or '发布'}」但帖子未发出：{reason}"
                logger.warning("%s %s", self.platform_name, err)
                return {
                    "success": False,
                    "submitted": False,
                    "error": err,
                    "steps": steps + ["submit_unconfirmed"],
                    "platform": self.platform_id,
                    "platform_name": self.platform_name,
                }
            logger.info(
                "%s 已确认发出（%s）%s",
                self.platform_name,
                reason,
                f" {post_url}" if post_url else "",
            )
            return {
                "success": True,
                "submitted": True,
                "url": post_url,
                "steps": steps + ["confirmed"],
                "platform": self.platform_id,
                "platform_name": self.platform_name,
                "media_count": len(media),
            }
        except Exception as e:
            logger.exception("%s 发布失败", self.platform_name)
            return {
                "success": False,
                "error": str(e),
                "steps": steps,
                "platform": self.platform_id,
            }
        finally:
            if own and self.close_driver and self.driver is not None:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None

    def _alt_square_urls(self) -> List[str]:
        base = self.square_url.rstrip("/").split("?")[0]
        if self.platform_id == "binance_square":
            return [f"{base}?tab=Home"]
        return []

    def _wait_for_editor(self, driver, timeout: float) -> bool:
        deadline = time.time() + max(6.0, timeout)
        while time.time() < deadline:
            if self._find_body_editor(driver):
                return True
            try:
                driver.execute_script(_ACTIVATE_SHORT_EDITOR_JS)
            except Exception:
                pass
            human_pause(0.35, 0.65)
        return False

    def _find_body_editor(self, driver) -> bool:
        try:
            if self.platform_id == "bitget":
                return bool(driver.execute_script(_FIND_BITGET_FIELDS_JS))
            return bool(driver.execute_script(_FIND_EDITOR_JS))
        except Exception:
            return False

    def _ensure_okx_orbit(self, driver, steps: List[str]) -> None:
        """确保在 orbit 页，再点「发文」。"""
        try:
            cur = (driver.current_url or "").lower()
        except Exception:
            cur = ""
        if "ventures" in cur or (cur and "/orbit" not in cur):
            driver.get(self.square_url)
            steps.append("orbit_reset")
            human_pause(1.2, 2.0)
        self._click_okx_compose(driver, steps)

    def _clear_compose_marks(self, driver) -> None:
        try:
            driver.execute_script(
                'document.querySelectorAll("[data-pai-compose]").forEach('
                "el => el.removeAttribute('data-pai-compose'));"
            )
        except Exception:
            pass

    def _click_okx_compose(self, driver, steps: List[str]) -> bool:
        """OKX 星球：只点 button 型「发文」，禁止点任何外链。"""
        from selenium.webdriver.common.by import By

        self._clear_compose_marks(driver)
        try:
            cur = (driver.current_url or "").lower()
            if "ventures" in cur or "/orbit" not in cur:
                driver.get(self.square_url)
                human_pause(1.0, 1.6)
        except Exception:
            pass

        xpaths = (
            "//button[normalize-space(.)='发文']",
            "//button[contains(normalize-space(.),'发文')]",
            "//*[@role='button' and normalize-space(.)='发文']",
        )
        for xp in xpaths:
            try:
                nodes = driver.find_elements(By.XPATH, xp)
            except Exception:
                continue
            for el in nodes:
                try:
                    if not el.is_displayed():
                        continue
                    if (el.tag_name or "").lower() == "a":
                        continue
                    bad = driver.execute_script(
                        """
                        let n = arguments[0];
                        while (n) {
                          if (n.tagName === 'A') {
                            const h = (n.getAttribute('href')||n.href||'').toLowerCase();
                            if (h && h !== '#' && !h.startsWith('javascript:')) return h;
                          }
                          n = n.parentElement;
                        }
                        return '';
                        """,
                        el,
                    )
                    if bad and (
                        "ventures" in str(bad).lower()
                        or ("okx.com" in str(bad).lower() and "/orbit" not in str(bad).lower())
                    ):
                        continue
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center',inline:'center'});"
                        "arguments[0].click();",
                        el,
                    )
                    human_pause(0.9, 1.5)
                    cur2 = (driver.current_url or "").lower()
                    if "ventures" in cur2:
                        logger.warning("OKX Selenium 点击仍跳转 ventures，跳过该元素")
                        try:
                            driver.get(self.square_url)
                            human_pause(0.8, 1.2)
                        except Exception:
                            pass
                        continue
                    if "compose" not in steps:
                        steps.append("compose")
                    return True
                except Exception:
                    continue

        if self._find_compose(driver) and self._click_marked(driver, "compose"):
            human_pause(0.9, 1.5)
            cur3 = (driver.current_url or "").lower()
            if "ventures" not in cur3:
                if "compose" not in steps:
                    steps.append("compose")
                return True
            try:
                driver.get(self.square_url)
                human_pause(0.8, 1.2)
            except Exception:
                pass
        return False

    def _find_compose(self, driver) -> bool:
        try:
            if self.platform_id == "okx":
                return bool(driver.execute_script(_FIND_OKX_COMPOSE_JS))
            return bool(
                driver.execute_script(_FIND_COMPOSE_JS, list(self.compose_labels))
            )
        except Exception:
            return False

    def _click_compose(self, driver, steps: List[str]) -> bool:
        """点击打开发布框（非 OKX）。"""
        if self.platform_id == "okx":
            return self._click_okx_compose(driver, steps)
        if not self._find_compose(driver):
            return False
        if not self._click_marked(driver, "compose"):
            return False
        human_pause(0.9, 1.5)
        if "compose" not in steps:
            steps.append("compose")
        return True

    def _open_compose_if_needed(self, driver, steps: List[str]) -> None:
        self._click_compose(driver, steps)

    def _sync_editor_state(self, driver) -> None:
        try:
            driver.execute_script(
                """
                const el = document.querySelector('[data-pai-editor="1"]');
                if (!el) return false;
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
                el.dispatchEvent(new Event('blur', {bubbles:true}));
                try { el.focus(); } catch (_) {}
                return true;
                """
            )
        except Exception:
            pass
        human_pause(0.25, 0.5)

    def _media_still_busy(self, driver) -> bool:
        try:
            return bool(
                driver.execute_script(
                    """
                    const editor = document.querySelector('[data-pai-editor="1"]');
                    const root = document.querySelector('[data-pai-editor-root="1"]')
                      || (editor && editor.closest('[role="dialog"], [class*="modal" i], [class*="editor" i], [class*="composer" i]'))
                      || (editor && editor.parentElement) || document.body;
                    function vis(el) {
                      if (!el || !el.getBoundingClientRect) return false;
                      const r = el.getBoundingClientRect();
                      if (r.width < 6 || r.height < 6) return false;
                      const st = window.getComputedStyle(el);
                      return !(st.display === 'none' || st.visibility === 'hidden');
                    }
                    const busySel = [
                      '[role="progressbar"]',
                      '[class*="uploading" i]',
                      '[class*="upload-progress" i]',
                      '[class*="loading" i]',
                      '[class*="spinner" i]',
                      '[class*="skeleton" i]'
                    ].join(',');
                    for (const el of root.querySelectorAll(busySel)) {
                      if (vis(el) && el.getBoundingClientRect().width > 8) return true;
                    }
                    for (const img of root.querySelectorAll('img')) {
                      const r = img.getBoundingClientRect();
                      if (r.width < 40 || r.height < 40) continue;
                      const src = (img.getAttribute('src') || img.src || '').toLowerCase();
                      const cls = String(img.className || '');
                      if (src.includes('avatar') || src.includes('icon') || cls.includes('avatar')) continue;
                      if (!img.complete || !img.naturalWidth) return true;
                    }
                    return false;
                    """
                )
            )
        except Exception:
            return False

    def _submit_button_state(self, driver) -> dict:
        try:
            st = driver.execute_script(
                """
                const words = ['发布','Post','Publish','Submit','发送','确认发布','立即发布'];
                function vis(el) {
                  if (!el || !el.getBoundingClientRect) return false;
                  const r = el.getBoundingClientRect();
                  if (r.width < 8 || r.height < 8) return false;
                  const st = window.getComputedStyle(el);
                  return !(st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) < 0.05);
                }
                function lab(el) {
                  return (el.getAttribute('aria-label') || el.innerText || el.textContent || '').replace(/\\s+/g, '').trim();
                }
                const editor = document.querySelector('[data-pai-editor="1"]');
                const cluster = editor && editor.closest(
                  '[role="dialog"], [class*="modal" i], [class*="drawer" i], [class*="popup" i], [class*="sheet" i], [class*="composer" i], [class*="editor" i]'
                );
                const nodes = (cluster || document).querySelectorAll('button, [role="button"], [type="submit"]');
                let found = null;
                for (const el of nodes) {
                  if (!vis(el)) continue;
                  const t = lab(el);
                  if (!t || t.length > 16) continue;
                  if (t.includes('文章') || t === '发文' || t === '发帖') continue;
                  if (!words.some(w => t === w || t.includes(w) || t.toLowerCase() === w.toLowerCase())) continue;
                  found = el;
                  if (t === '发布' || t.toLowerCase() === 'post' || t.toLowerCase() === 'publish') break;
                }
                if (!found) return { found: false, enabled: false, label: '', disabled: false };
                const disabled = !!(found.disabled || found.getAttribute('aria-disabled') === 'true');
                return { found: true, enabled: !disabled, label: lab(found).slice(0, 16), disabled };
                """
            )
            return st if isinstance(st, dict) else {}
        except Exception:
            return {}

    def _wait_before_submit(self, driver, *, has_media: bool) -> None:
        if has_media:
            logger.info("%s 等待图片加载完成（加载中发布按钮会是灰色）…", self.platform_name)
            self._wait_media_settle(driver, timeout=22.0)
            human_pause(2.4, 4.0)
        deadline = time.time() + (18.0 if has_media else 8.0)
        last = {}
        while time.time() < deadline:
            if has_media and self._media_still_busy(driver):
                time.sleep(0.45)
                continue
            last = self._submit_button_state(driver)
            if last.get("enabled"):
                logger.info("%s 提交按钮已可点「%s」", self.platform_name, last.get("label") or "发布")
                human_pause(0.5, 1.0)
                return
            time.sleep(0.45)
        logger.warning(
            "%s 等待后提交按钮仍未就绪 found=%s enabled=%s label=%s",
            self.platform_name,
            last.get("found"),
            last.get("enabled"),
            last.get("label"),
        )
        if has_media:
            human_pause(2.0, 3.0)

    def _click_result_ok(self, res) -> tuple:
        """点击脚本可能返回 bool 或 {ok, label, score, candidates}。非空 dict 在 Python 里恒为真。"""
        if isinstance(res, dict):
            ok = bool(res.get("ok"))
            label = str(res.get("label") or "").strip()
            compact = label.replace(" ", "")
            cands = res.get("candidates") if isinstance(res.get("candidates"), list) else []
            if ok and compact in {"发文", "发帖", "发帖子", "发动态"}:
                logger.warning(
                    "%s 点到的是开编辑器「%s」，不算提交",
                    self.platform_name,
                    label,
                )
                ok = False
            logger.info(
                "%s 点击结果 ok=%s label=%r score=%s candidates=%s nearby=%s",
                self.platform_name,
                ok,
                label,
                res.get("score"),
                cands[:6] if cands else [],
                (res.get("nearby") or [])[:8],
            )
            return ok, label, cands
        return bool(res), "", []

    def _click_submit(self, driver) -> tuple:
        if self.platform_id == "bitget":
            ok = self._click_bitget_submit(driver)
            return ok, "发布" if ok else "", []
        labels = list(self.submit_labels)
        last_cands: list = []
        allow_disabled = False

        for attempt in range(12):
            # 尝试 4 次仍失败 → 允许点 disabled 按钮
            if attempt >= 4 and not allow_disabled:
                logger.info("%s 切换到 allowDisabled=True（强制点击）", self.platform_name)
                allow_disabled = True

            # 策略 1：精确查找
            for strategy in (1, 2):
                try:
                    if strategy == 1:
                        res = driver.execute_script(_CLICK_EXACT_PUBLISH_JS, allow_disabled)
                    else:
                        res = driver.execute_script(_CLICK_SUBMIT_JS, labels, allow_disabled)
                    ok, label, cands = self._click_result_ok(res)
                    if cands:
                        last_cands = cands
                    if isinstance(res, dict) and res.get("waiting"):
                        logger.info(
                            "%s 「%s」还是灰色（%s/12）",
                            self.platform_name,
                            res.get("label") or "发布",
                            attempt + 1,
                        )
                        human_pause(0.9, 1.4)
                        break  # break strategy, retry from top
                    if ok:
                        return True, label or "发布", last_cands
                except Exception as e:
                    logger.debug("点击策略 %s 失败 attempt=%s: %s", strategy, attempt, e)
                    break  # try next strategy

            # 策略 2：Selenium 原生点击
            ok, lbl = self._click_submit_selenium(driver, allow_disabled=allow_disabled), "发布"
            if ok:
                return True, lbl, last_cands

            # 策略 3：坐标点击（备用）
            if self._click_submit_by_coords(driver):
                return True, "发布", last_cands

            human_pause(0.8, 1.3)

        return False, "", last_cands

    def _submit_state(self, driver) -> dict:
        try:
            st = driver.execute_script(_SUBMIT_STATE_JS)
            return st if isinstance(st, dict) else {}
        except Exception:
            return {}

    def _pick_new_post_url(self, driver, urls_before: set) -> str:
        """只认当前页变成了帖子链接，不把信息流里新冒出来的别人的帖当成功。"""
        try:
            cur = (driver.current_url or "").strip().split("#")[0]
            cur_l = cur.lower()
            if any(m.lower() in cur_l for m in self.post_url_markers) and cur not in urls_before:
                return cur
        except Exception:
            pass
        return ""

    def _wait_submit_confirmed(
        self,
        driver,
        *,
        body: str,
        urls_before: set,
        timeout: float = 14.0,
    ) -> tuple:
        """点完发布后必须看到新帖链接 / 成功提示 / 编辑区关掉，否则算失败。"""
        had_body = len((body or "").strip()) >= 16
        deadline = time.time() + max(6.0, timeout)
        last: dict = {}
        closed_since = None
        last_log = 0.0
        while time.time() < deadline:
            post_url = self._pick_new_post_url(driver, urls_before)
            if post_url:
                return True, post_url, "出现新帖链接"
            last = self._submit_state(driver)
            now = time.time()
            if now - last_log >= 2.5:
                last_log = now
                logger.info(
                    "%s 确认中 editor=%s len=%s modal=%s href=%s",
                    self.platform_name,
                    last.get("editorPresent"),
                    last.get("editorLen"),
                    last.get("modalOpen"),
                    str(last.get("href") or "")[:80],
                )
            toasts = " ".join(str(t) for t in (last.get("toasts") or []))
            toast_l = toasts.lower()
            if any(
                w in toasts
                for w in ("发布成功", "已发布", "发送成功", "发帖成功", "动态已发布")
            ) or any(
                w in toast_l
                for w in ("published successfully", "post successful", "posted successfully")
            ):
                return True, last.get("href") or "", f"成功提示「{toasts[:40]}」"
            if any(
                w in toasts
                for w in ("发布失败", "发送失败", "未登录", "请先登录", "请登录")
            ):
                return False, "", toasts[:80] or "页面提示失败"

            href = str(last.get("href") or "").lower()
            if any(w in href for w in ("/login", "/signin", "/account/login")):
                return False, "", "跳到了登录页，帖子未发出"

            editor_on = bool(last.get("editorPresent"))
            modal_on = bool(last.get("modalOpen"))
            editor_len = int(last.get("editorLen") or 0)
            composing = editor_on or modal_on
            if composing:
                closed_since = None
            else:
                if closed_since is None:
                    closed_since = time.time()
                elif time.time() - closed_since >= 1.5:
                    post_url = self._pick_new_post_url(driver, urls_before)
                    if post_url:
                        return True, post_url, "出现新帖链接"
                    return True, last.get("href") or "", "编辑区已关闭"

            if had_body and editor_on and editor_len < 8 and not modal_on:
                post_url = self._pick_new_post_url(driver, urls_before)
                if post_url:
                    return True, post_url, "出现新帖链接"
            time.sleep(0.4)

        post_url = self._pick_new_post_url(driver, urls_before)
        if post_url:
            return True, post_url, "出现新帖链接"

        editor_on = bool(last.get("editorPresent"))
        modal_on = bool(last.get("modalOpen"))
        editor_len = int(last.get("editorLen") or 0)
        if had_body and editor_on and editor_len >= 16:
            return False, "", f"编辑区还在（{editor_len} 字），点击没有发出去"
        if editor_on or modal_on:
            return False, "", "编辑弹窗还开着，帖子未发出"
        if closed_since is not None:
            return True, last.get("href") or "", "编辑区已关闭"
        return False, "", "点击后未出现新帖链接或成功提示"

    def _sync_bitget_form(self, driver) -> None:
        try:
            driver.execute_script(_SYNC_BITGET_FORM_JS)
        except Exception:
            pass
        human_pause(0.3, 0.6)

    def _wait_bitget_submit_ready(self, driver, timeout: float = 12.0) -> bool:
        deadline = time.time() + max(4.0, timeout)
        while time.time() < deadline:
            try:
                ready = driver.execute_script(
                    """
                    const scopes = [];
                    const editor = document.querySelector('[data-pai-editor="1"]');
                    if (editor) {
                      const m = editor.closest('[role="dialog"], [class*="modal" i], [class*="Modal"]');
                      if (m) scopes.push(m);
                    }
                    if (!scopes.length) scopes.push(document.body);
                    function norm(t){return (t||'').trim().replace(/\\s+/g,'');}
                    for (const scope of scopes) {
                      for (const el of scope.querySelectorAll('button, [role="button"], a, span, div')) {
                        const t = norm(el.innerText || el.textContent || '');
                        if (t !== '发布' || t.includes('文章')) continue;
                        const r = el.getBoundingClientRect();
                        if (r.width < 8 || r.height < 8) continue;
                        if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                        if (r.top < window.innerHeight * 0.35) continue;
                        return true;
                      }
                    }
                    return false;
                    """
                )
                if ready:
                    return True
            except Exception:
                pass
            self._sync_bitget_form(driver)
            human_pause(0.45, 0.75)
        return False

    def _click_bitget_submit(self, driver) -> bool:
        from selenium.webdriver.common.by import By

        for attempt in range(14):
            allow_disabled = attempt >= 8
            try:
                if driver.execute_script(_CLICK_BITGET_SUBMIT_JS, allow_disabled):
                    return True
            except Exception as e:
                logger.debug("Bitget JS 发布 attempt=%s: %s", attempt, e)
            xpaths = (
                "//*[contains(@class,'modal') or contains(@class,'Modal') or @role='dialog']"
                "//*[self::button or @role='button' or contains(@class,'btn')]"
                "[normalize-space(.)='发布']",
                "//button[normalize-space(.)='发布']",
                "//*[@role='button' and normalize-space(.)='发布']",
                "//*[contains(@class,'btn') and normalize-space(.)='发布']",
                "//span[normalize-space(.)='发布']/ancestor::button[1]",
                "//span[normalize-space(.)='发布']/ancestor::*[@role='button'][1]",
                "//span[normalize-space(.)='发布']/ancestor::*[contains(@class,'btn')][1]",
            )
            candidates: List[tuple] = []
            for xp in xpaths:
                try:
                    nodes = driver.find_elements(By.XPATH, xp)
                except Exception:
                    continue
                for el in nodes:
                    try:
                        if not el.is_displayed():
                            continue
                        if not allow_disabled:
                            if (el.get_attribute("disabled") or "").lower() in ("true", "disabled"):
                                continue
                            if (el.get_attribute("aria-disabled") or "").lower() == "true":
                                continue
                        txt = driver.execute_script(
                            "return (arguments[0].innerText||arguments[0].textContent||'').replace(/\\s+/g,'').trim()",
                            el,
                        )
                        if txt != "发布" or "文章" in txt:
                            continue
                        top = driver.execute_script(
                            "return arguments[0].getBoundingClientRect().top",
                            el,
                        )
                        score = 100 + (top or 0) / 10
                        if top and top < driver.execute_script("return window.innerHeight * 0.22"):
                            score -= 200
                        candidates.append((score, el))
                    except Exception:
                        continue

            candidates.sort(key=lambda x: -x[0])
            for _, el in candidates[:8]:
                try:
                    click_el = driver.execute_script(
                        """
                        const el = arguments[0];
                        return el.closest('button,[role="button"],a,[class*="btn"]') || el;
                        """,
                        el,
                    )
                    if click_el:
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center',inline:'center'});"
                            "arguments[0].click();",
                            click_el,
                        )
                        return True
                except Exception:
                    try:
                        el.click()
                        return True
                    except Exception:
                        continue

            human_pause(0.6, 1.0)
        try:
            dbg = driver.execute_script(_DEBUG_BITGET_SUBMIT_JS)
            logger.warning("Bitget 未点到发布按钮，候选: %s", dbg)
        except Exception:
            pass
        return False

    def _click_submit_selenium(self, driver, *, allow_disabled: bool = False) -> bool:
        from selenium.webdriver.common.by import By

        labels = list(self.submit_labels)
        editor = None
        try:
            editors = driver.find_elements(By.CSS_SELECTOR, '[data-pai-editor="1"]')
            editor = editors[0] if editors else None
        except Exception:
            editor = None

        candidates: List[tuple] = []
        selectors = (
            'button, [role="button"], a, [class*="btn"], [class*="button"], '
            'span[class*="btn"], div[class*="submit"]'
        )
        try:
            nodes = driver.find_elements(By.CSS_SELECTOR, selectors)
        except Exception:
            return False

        for el in nodes:
            try:
                if not el.is_displayed():
                    continue
                if not allow_disabled:
                    if (el.get_attribute("disabled") or "").lower() in ("true", "disabled"):
                        continue
                    if (el.get_attribute("aria-disabled") or "").lower() == "true":
                        continue
                t = (el.text or el.get_attribute("aria-label") or el.get_attribute("title") or "").strip()
                compact = "".join(t.split())
                if not compact or len(compact) > 18:
                    continue
                if "文章" in compact:
                    continue
                if compact in {"发文", "发帖", "发帖子", "发动态"}:
                    continue
                if not any(lab.replace(" ", "") in compact or lab.lower() in t.lower() for lab in labels):
                    continue
                in_nav = driver.execute_script(
                    """
                    const el = arguments[0];
                    const ed = arguments[1];
                    const chrome = el.closest(
                      'header, nav, [class*="navbar" i], [class*="side-nav" i], [class*="sidenav" i]'
                    );
                    if (!chrome) return false;
                    const cluster = ed && ed.closest(
                      '[role="dialog"], [class*="modal"], [class*="drawer"], [class*="popup"], [class*="sheet"], [class*="composer"]'
                    );
                    if (cluster && cluster.contains(el)) return false;
                    return true;
                    """,
                    el,
                    editor,
                )
                if in_nav:
                    continue
                score = 40
                for i, lab in enumerate(labels):
                    if lab.replace(" ", "") in compact or lab.lower() == t.lower():
                        score = max(score, 100 - i)
                tag = (el.tag_name or "").lower()
                if tag == "button" or el.get_attribute("role") == "button":
                    score += 8
                if editor is not None:
                    near = driver.execute_script(
                        """
                        const ed = arguments[0], btn = arguments[1];
                        if (!ed) return 0;
                        const cluster = ed.closest(
                          '[role="dialog"], [class*="modal"], [class*="drawer"], [class*="popup"], [class*="editor"], [data-pai-editor-root="1"]'
                        );
                        if (cluster && cluster.contains(btn)) return 100;
                        const er = ed.getBoundingClientRect();
                        const r = btn.getBoundingClientRect();
                        const dist = Math.hypot(
                          (r.left + r.width/2) - (er.left + er.width/2),
                          (r.top + r.height/2) - (er.top + er.height/2)
                        );
                        return dist < 380 ? 55 : 0;
                        """,
                        editor,
                        el,
                    )
                    if not near:
                        continue
                    score += int(near or 0)
                candidates.append((score, el))
            except Exception:
                continue

        candidates.sort(key=lambda x: -x[0])
        for score, el in candidates[:6]:
            if score < 20:
                break
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center', inline:'center'});"
                    "arguments[0].click();",
                    el,
                )
                return True
            except Exception:
                try:
                    el.click()
                    return True
                except Exception:
                    continue
        return False

    def _click_submit_by_coords(self, driver) -> bool:
        """备用：找到「发布」类按钮位置，用坐标点击（绕过遮挡/JS 问题）。"""
        try:
            hit = driver.execute_script("""
                const words = ['发布','发送','Post','Publish','Submit','立即发布','确认发布'];
                function vis(el) {
                  if (!el || !el.getBoundingClientRect) return null;
                  const r = el.getBoundingClientRect();
                  if (r.width < 8 || r.height < 8) return null;
                  const st = window.getComputedStyle(el);
                  if (st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) < 0.05) return null;
                  return r;
                }
                function ownText(el) {
                  return ((el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText || el.textContent || '').replace(/\\s+/g,'').trim()).slice(0,12);
                }
                function clickable(el) {
                  return el.closest('button,[role="button"],[type="submit"],[class*="btn"],[class*="button"]') || el;
                }
                const editor = document.querySelector('[data-pai-editor="1"]');
                const cluster = editor && editor.closest('[role="dialog"],[class*="modal"],[class*="drawer"],[class*="popup"],[class*="sheet"],[class*="composer"]');
                const roots = cluster ? [cluster, document.body] : [document.body];
                let best = null, bestSc = 0;
                for (const root of roots) {
                  for (const el of root.querySelectorAll('button,[role="button"],[class*="btn"]')) {
                    const r = vis(el);
                    if (!r) continue;
                    if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                    const t = ownText(el);
                    const cls = String(el.className || '');
                    let sc = 0;
                    if (words.some(w => t.includes(w) && !['发文','发帖','发动态'].includes(t))) sc = 100;
                    else if (words.some(w => t.includes(w))) sc = 40;
                    else continue;
                    if (/primary|solid|bn-button|submit/i.test(cls)) sc += 20;
                    if (r.top < window.innerHeight * 0.45 && r.top > window.innerHeight * 0.05) sc += 30;
                    if (sc > bestSc) { bestSc = sc; best = el; }
                  }
                }
                if (!best || bestSc < 80) return null;
                const r = best.getBoundingClientRect();
                return { x: r.left + r.width/2, y: r.top + r.height/2 };
                """)
            if not hit:
                return False
            x, y = float(hit["x"]), float(hit["y"])
            from selenium.webdriver.common.action_chains import ActionChains

            ActionChains(driver).move_to_element_with_offset(
                driver.find_element("tag name", "body"), x, y
            ).click().perform()
            return True
        except Exception as e:
            logger.debug("坐标点击失败: %s", e)
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

    def _fill_bitget_title(self, driver, title: str) -> bool:
        from selenium.webdriver.common.by import By

        if not title.strip():
            return False
        try:
            driver.execute_script(_FIND_BITGET_FIELDS_JS)
            found_title = driver.execute_script(_FIND_BITGET_TITLE_JS)
        except Exception:
            found_title = False
        if not found_title:
            return False
        try:
            field = driver.find_element(By.CSS_SELECTOR, '[data-pai-title="1"]')
        except Exception:
            return False
        try:
            field.click()
            type_text_human(driver, field, title, min_delay=0.03, max_delay=0.1, clear_first=True)
            return True
        except Exception:
            return False

    def _type_text(self, driver, text: str, *, clear_first: bool = True) -> None:
        from selenium.webdriver.common.by import By

        text = sanitize_typed_text(text)
        if not text:
            return

        for _ in range(3):
            if not self._find_body_editor(driver):
                human_pause(0.2, 0.4)
                continue
            try:
                if clear_first and driver.execute_script(_SET_EDITOR_TEXT_JS, text):
                    return
            except Exception:
                pass
            try:
                editor = driver.find_element(By.CSS_SELECTOR, '[data-pai-editor="1"]')
                editor.click()
                type_text_human(
                    driver,
                    editor,
                    text,
                    clear_first=clear_first,
                )
                return
            except Exception:
                human_pause(0.2, 0.4)
        raise RuntimeError("无法写入正文编辑区")

    def _count_editor_media(self, driver, prefer: str = "image") -> int:
        try:
            n = driver.execute_script(_COUNT_EDITOR_MEDIA_JS, prefer)
            return int(n or 0)
        except Exception:
            return 0

    def _upload_media(self, driver, paths: List[str], prefer: str = "image") -> int:
        if not paths:
            return 0

        existing = self._count_editor_media(driver, prefer=prefer)
        if existing >= len(paths):
            logger.info("编辑器已有 %s 个媒体，跳过重复上传", existing)
            return len(paths)

        to_upload = paths[existing:]
        uploaded = 0
        inputs = find_file_inputs(driver, prefer=prefer)

        for ap in to_upload:
            try:
                if not inputs:
                    inputs = find_file_inputs(driver, prefer=prefer)
                # 仅在没有隐藏 file input 时才点「添加图片」，避免多余弹窗
                if not inputs:
                    try:
                        driver.execute_script(_CLICK_MEDIA_BUTTON_JS, prefer)
                        human_pause(0.4, 0.9)
                    except Exception:
                        pass
                    inputs = find_file_inputs(driver, prefer=prefer)
                if inputs:
                    inputs[0].send_keys(ap)
                    uploaded += 1
                    want = existing + uploaded
                    deadline = time.time() + (
                        min(12.0, self.media_upload_wait)
                        if prefer == "video"
                        else 3.5
                    )
                    while time.time() < deadline:
                        if self._count_editor_media(driver, prefer=prefer) >= want:
                            break
                        time.sleep(0.35)
                    continue
            except Exception as e:
                logger.warning("file input 上传失败 %s: %s", ap, e)

            if prefer == "image" and self._paste_image_clipboard(driver, ap):
                uploaded += 1
        return existing + uploaded

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
        if not self._find_body_editor(driver):
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

    def _wait_media_settle(self, driver, timeout: float = 12.0) -> None:
        deadline = time.time() + min(28.0, max(6.0, timeout))
        idle_since = None
        while time.time() < deadline:
            busy = self._media_still_busy(driver)
            if not busy:
                if idle_since is None:
                    idle_since = time.time()
                elif time.time() - idle_since >= 1.6:
                    return
            else:
                idle_since = None
            time.sleep(0.4)
        logger.warning("%s 媒体仍可能在加载，继续尝试发布", self.platform_name)

    def _collect_post_urls(self, driver) -> set:
        markers_js = [m.lower() for m in self.post_url_markers]
        try:
            hrefs = driver.execute_script(
                """
                const markers = arguments[0];
                const out = new Set();
                for (const a of document.querySelectorAll('a[href]')) {
                  const h = (a.href || '').split('#')[0];
                  if (!h) continue;
                  const hl = h.toLowerCase();
                  if (markers.some(m => hl.includes(m))) out.add(h);
                }
                try {
                  const cur = (location.href || '').split('#')[0];
                  const cl = cur.toLowerCase();
                  if (markers.some(m => cl.includes(m))) out.add(cur);
                } catch (_) {}
                return Array.from(out);
                """,
                markers_js,
            )
            if isinstance(hrefs, list):
                return {str(h) for h in hrefs if h}
        except Exception:
            pass
        return set()
