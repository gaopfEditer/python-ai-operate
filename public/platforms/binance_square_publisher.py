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
    type_text_human,
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
  if (!el) return true;
  if (el.disabled) return true;
  if (el.getAttribute('aria-disabled') === 'true') return true;
  return false;
}
function textOf(el) {
  return (el.innerText || el.textContent || el.getAttribute('aria-label')
    || el.getAttribute('title') || '').trim();
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
function scoreBtn(el) {
  if (inBadAnchor(el)) return 0;
  const t = textOf(el);
  const cls = String(el.className || '') + ' ' + (el.getAttribute('class') || '');
  const blob = (t + ' ' + cls).toLowerCase();
  if (!t && !blob) return 0;
  let sc = 0;
  for (let i = 0; i < labels.length; i++) {
    const lab = labels[i];
    if (t === lab || t.includes(lab) || blob.includes(lab.toLowerCase())) {
      sc = Math.max(sc, 120 - i);
    }
  }
  if (!sc) return 0;
  if (el.tagName === 'BUTTON' || el.getAttribute('role') === 'button') sc += 8;
  const editor = document.querySelector('[data-pai-editor="1"]');
  if (editor) {
    const modal = el.closest('[role="dialog"], [class*="modal" i], [class*="drawer" i], [class*="popup" i], [class*="overlay" i]');
    if (modal && modal.contains(editor)) sc += 60;
    if (el.closest('[class*="footer" i], [class*="action" i], [class*="toolbar" i]')) sc += 25;
    if (el.closest('header, nav, [class*="header" i], [class*="navbar" i], [class*="nav-" i]')) sc -= 55;
  }
  try {
    const r = el.getBoundingClientRect();
    if (r.top > window.innerHeight * 0.45) sc += 12;
  } catch (_) {}
  return sc;
}
function collectScopes() {
  const scopes = [];
  const seen = new Set();
  const push = (el) => {
    if (!el || seen.has(el)) return;
    seen.add(el);
    scopes.push(el);
  };
  const editor = document.querySelector('[data-pai-editor="1"]');
  if (editor) {
    const modal = editor.closest(
      '[role="dialog"], [class*="modal" i], [class*="Modal"], [class*="drawer" i], [class*="Drawer"], [class*="popup" i], [class*="Popup"], [class*="overlay" i], [class*="sheet" i]'
    );
    if (modal) {
      push(modal);
      modal.querySelectorAll('[class*="footer" i], [class*="Footer"], [class*="action" i], [class*="Action"], [class*="bottom" i]').forEach(push);
    }
    push(editor.closest('[class*="editor" i], [class*="Editor"]') || editor.parentElement);
  }
  const root = document.querySelector('[data-pai-editor-root="1"]')
    || document.querySelector('[class*="short-editor"]');
  if (root) push(root);
  document.querySelectorAll('.editor-toolbar-container, [class*="editor-toolbar"]').forEach((tb) => {
    push(tb);
    if (tb.parentElement) push(tb.parentElement);
    if (tb.nextElementSibling) push(tb.nextElementSibling);
  });
  push(document.body);
  return scopes;
}
const sel = 'button, [role="button"], a, [class*="btn" i], [class*="button" i], span[class*="btn" i], div[class*="submit" i]';
let best = null, bestSc = 0;
for (const scope of collectScopes()) {
  for (const el of scope.querySelectorAll(sel)) {
    if (!visible(el) || disabled(el)) continue;
    const sc = scoreBtn(el);
    if (sc > bestSc) { bestSc = sc; best = el; }
  }
}
if (!best || bestSc < 20) return false;
try {
  best.scrollIntoView({block:'center', inline:'center'});
  best.click();
  return true;
} catch (_) {
  try {
    best.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
    return true;
  } catch (_) {
    return false;
  }
}
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
        if platform_id == "bitget":
            self.submit_labels = ("发布",)
        else:
            self.submit_labels = _SUBMIT_LABELS + _PLATFORM_SUBMIT_EXTRA.get(platform_id, ())
        self.post_url_markers = _PLATFORM_POST_MARKERS.get(
            platform_id, ("/square/post/",)
        )
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
        title_text = (title or "").strip()
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
            open_url_new_tab(driver, self.square_url)
            steps.append("square")
            human_pause(1.0, 1.8)
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

            if not self._find_body_editor(driver):
                return {
                    "success": False,
                    "error": f"未找到{self.platform_name}编辑区，请确认已登录",
                    "steps": steps,
                    "platform": self.platform_id,
                }
            steps.append("editor")

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
                    n = self._upload_media(driver, images, prefer="image")
                    steps.append(f"images:{n}")
                    human_pause(1.0, 2.0)

                if videos:
                    n = self._upload_media(driver, videos, prefer="video")
                    steps.append(f"videos:{n}")
                    human_pause(2.0, 4.0)
                    self._wait_media_settle(driver, timeout=max(30.0, self.media_upload_wait))

                if body:
                    self._type_text(driver, body)
                    steps.append("text")
                    human_pause(0.4, 0.9)
                    self._sync_editor_state(driver)

            if not submit:
                return {
                    "success": True,
                    "submitted": False,
                    "steps": steps + ["dry_run"],
                    "platform": self.platform_id,
                    "platform_name": self.platform_name,
                }

            human_pause(0.5, 1.0)
            self._sync_editor_state(driver)
            if self.platform_id == "bitget":
                self._find_body_editor(driver)
                self._sync_bitget_form(driver)
                self._wait_bitget_submit_ready(driver, timeout=14.0)
            urls_before = self._collect_post_urls(driver)
            clicked = self._click_submit(driver)
            if not clicked:
                err = "未找到或无法点击「发布」按钮"
                if self.platform_id == "bitget":
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
            human_pause(2.0, 3.5)

            post_url = ""
            try:
                cur = (driver.current_url or "").strip()
                cur_l = cur.lower()
                if any(m.lower() in cur_l for m in self.post_url_markers):
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

    def _click_submit(self, driver) -> bool:
        if self.platform_id == "bitget":
            return self._click_bitget_submit(driver)
        labels = list(self.submit_labels)
        for attempt in range(8):
            try:
                if driver.execute_script(_CLICK_SUBMIT_JS, labels):
                    return True
            except Exception as e:
                logger.debug("JS 点击发布失败 attempt=%s: %s", attempt, e)
            if self._click_submit_selenium(driver):
                return True
            human_pause(0.55, 1.0)
        return False

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

    def _click_submit_selenium(self, driver) -> bool:
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
                if (el.get_attribute("disabled") or "").lower() in ("true", "disabled"):
                    continue
                if (el.get_attribute("aria-disabled") or "").lower() == "true":
                    continue
                t = (el.text or el.get_attribute("aria-label") or el.get_attribute("title") or "").strip()
                if not t or not any(lab in t for lab in labels):
                    continue
                score = 0
                for i, lab in enumerate(labels):
                    if lab in t:
                        score = max(score, 100 - i)
                if score <= 0:
                    continue
                tag = (el.tag_name or "").lower()
                if tag == "button" or el.get_attribute("role") == "button":
                    score += 8
                if editor is not None:
                    in_modal = driver.execute_script(
                        """
                        const ed = arguments[0], btn = arguments[1];
                        const modal = ed.closest('[role="dialog"], [class*="modal"], [class*="drawer"], [class*="popup"]');
                        return !!(modal && modal.contains(btn));
                        """,
                        editor,
                        el,
                    )
                    if in_modal:
                        score += 60
                    in_nav = driver.execute_script(
                        """
                        return !!arguments[0].closest('header, nav, [class*="header"], [class*="navbar"], [class*="nav-"]');
                        """,
                        el,
                    )
                    if in_nav:
                        score -= 55
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

        for _ in range(4):
            if not self._find_body_editor(driver):
                human_pause(0.3, 0.6)
                continue
            try:
                editor = driver.find_element(By.CSS_SELECTOR, '[data-pai-editor="1"]')
                editor.click()
                type_text_human(
                    driver,
                    editor,
                    text,
                    min_delay=0.04,
                    max_delay=0.13,
                    clear_first=clear_first,
                )
                return
            except Exception:
                human_pause(0.3, 0.6)
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
                    time.sleep(
                        self.media_upload_wait
                        if prefer == "video"
                        else min(8.0, self.media_upload_wait)
                    )
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
