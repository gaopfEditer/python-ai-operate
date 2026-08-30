# coding=utf-8
"""CDP 抓取 X List 时间线推文（含时间、正文、图片）。"""

from __future__ import annotations

import re
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from signals.store import media_root, parse_dt, parse_list_id
from signals.tweet_log import fmt_tweet_line

ProgressCb = Optional[Callable[[str], None]]

# 专用静默标签标记（用于复用 / 清理，避免每次 createTarget 堆 tab）
_SIGNALS_TAB_MARKER = "trendradar-signals"
_SIGNALS_TAB_BLANK = f"about:blank#{_SIGNALS_TAB_MARKER}"

_SESSION_LOCK = threading.RLock()
_SESSION: Optional[Dict[str, Any]] = None  # client, page, target_id

LIST_FEED_JS = r"""
function absUrl(u){
  try {
    if (!u) return '';
    if (/^https?:\/\//i.test(u)) return new URL(u).href.split('?')[0];
    const base = (location && location.origin) ? location.origin : 'https://x.com';
    return new URL(u, base).href.split('?')[0];
  } catch(e) {
    return String(u || '').split('?')[0];
  }
}
/** 推特媒体 URL 必须保留 ?format=&name=，否则会 404 */
function mediaUrl(u){
  try {
    if (!u) return '';
    let href = String(u);
    if (!/^https?:\/\//i.test(href)) {
      const base = (location && location.origin) ? location.origin : 'https://x.com';
      href = new URL(href, base).href;
    }
    const url = new URL(href);
    if (/pbs\.twimg\.com|twimg\.com/i.test(url.hostname)) {
      if (!url.searchParams.get('format')) {
        const path = url.pathname.toLowerCase();
        let fmt = 'jpg';
        if (path.endsWith('.png')) fmt = 'png';
        else if (path.endsWith('.webp')) fmt = 'webp';
        else if (path.endsWith('.gif')) fmt = 'gif';
        url.searchParams.set('format', fmt);
      }
      url.searchParams.set('name', 'large');
      return url.href;
    }
    return url.href;
  } catch(e) {
    return String(u || '');
  }
}
function pickStatus(article){
  const links = [...article.querySelectorAll("a[href*='status']")];
  for (const l of links) {
    const h = (l.getAttribute('href') || '').trim();
    if (!h || /\/(analytics|photo|video|media)\//.test(h)) continue;
    const m = h.match(/status\/(\d+)/i);
    if (m) {
      const path = h.startsWith('http') ? h : (h.startsWith('/') ? h : '/' + h);
      return { tweet_id: m[1], url: absUrl(path) };
    }
  }
  const timeLink = article.querySelector('time')?.closest('a[href*="status"]');
  if (timeLink) {
    const h = (timeLink.getAttribute('href') || '').trim();
    const m = h.match(/status\/(\d+)/i);
    if (m) return { tweet_id: m[1], url: absUrl(h) };
  }
  return null;
}
function pickAuthor(article){
  for (const s of article.querySelectorAll('a[role="link"] span, [data-testid="User-Name"] span')) {
    const t = (s.textContent || '').trim();
    if (t.startsWith('@')) return t;
  }
  const nameLink = article.querySelector('[data-testid="User-Name"] a[href^="/"]')
    || article.querySelector('div[data-testid="User-Name"] a[href^="/"]');
  if (nameLink) {
    const href = (nameLink.getAttribute('href') || '').split('?')[0].split('#')[0];
    const seg = href.replace(/^\//, '').split('/')[0];
    const bad = ['home','search','i','intent','hashtag','explore','settings','notifications'];
    if (seg && bad.indexOf(seg.toLowerCase()) < 0) return '@' + seg;
  }
  return '';
}
const out = [];
const arts = [...document.querySelectorAll("article[data-testid='tweet']")];
for (const a of arts) {
  try {
    const bodyTxt = (a.innerText || '').trim();
    if (!bodyTxt || bodyTxt.length < 2) continue;
    const head = (bodyTxt.split('\n')[0] || '').trim();
    if (/^(Relevant|People|Top|Latest|Post|Posts)$/i.test(head)) continue;
    const st = pickStatus(a);
    if (!st || !st.tweet_id) continue;
    const timeEl = a.querySelector('time');
    const created_at = timeEl ? (timeEl.getAttribute('datetime') || '') : '';
    const time_label = timeEl ? (timeEl.textContent || '').trim() : '';
    const textParts = [...a.querySelectorAll('[data-testid="tweetText"]')]
      .map(el => (el.innerText || '').trim())
      .filter(Boolean);
    const text = (textParts.length ? textParts.join('\n\n') : bodyTxt).slice(0, 8000);
    const author = pickAuthor(a);
    const images = [];
    const seenImg = new Set();
    function pushImg(raw, alt) {
      if (!raw) return;
      const s = String(raw);
      if (s.indexOf('profile_images') >= 0 || s.indexOf('emoji') >= 0 || s.indexOf('hashflag') >= 0) return;
      const ok = s.indexOf('pbs.twimg.com/media') >= 0
        || s.indexOf('pbs.twimg.com/ext_tw_video_thumb') >= 0
        || s.indexOf('pbs.twimg.com/tweet_video_thumb') >= 0
        || s.indexOf('pbs.twimg.com/amplify_video_thumb') >= 0
        || (s.indexOf('twimg.com') >= 0 && s.indexOf('/media/') >= 0);
      if (!ok) return;
      const url = mediaUrl(s);
      if (!url) return;
      const key = url.replace(/([?&]name=)[^&]+/i, '$1large');
      if (seenImg.has(key)) return;
      seenImg.add(key);
      images.push({ url: key, alt: String(alt || '').slice(0, 300) });
    }
    function fromSrcset(ss) {
      if (!ss) return '';
      let best = '', bestW = -1;
      const parts = String(ss).split(',');
      for (let i = 0; i < parts.length; i++) {
        const bits = parts[i].trim().split(/\s+/);
        const u = bits[0] || '';
        const w = parseInt((bits[1] || '').replace(/w$/i, ''), 10) || 0;
        if (u && w >= bestW) { best = u; bestW = w; }
      }
      return best || String(ss).trim().split(/\s+/)[0] || '';
    }
    // 1) DOM img / video / background
    const imgs = a.querySelectorAll('img');
    for (let i = 0; i < imgs.length; i++) {
      const img = imgs[i];
      try {
        if (img.loading === 'lazy') img.loading = 'eager';
        if (!img.getAttribute('src') && img.currentSrc) img.setAttribute('src', img.currentSrc);
        const ss = img.srcset || img.getAttribute('srcset') || '';
        if (!img.getAttribute('src') && ss) {
          const u = fromSrcset(ss);
          if (u) img.setAttribute('src', u);
        }
      } catch (e) {}
      const src = img.currentSrc || img.getAttribute('src') || fromSrcset(img.getAttribute('srcset') || img.srcset || '') || '';
      pushImg(src, img.getAttribute('alt') || '');
    }
    const videos = a.querySelectorAll('video');
    for (let i = 0; i < videos.length; i++) {
      const v = videos[i];
      pushImg(v.getAttribute('poster') || v.poster || '', 'video');
    }
    const bgEls = a.querySelectorAll('[data-testid="tweetPhoto"] *, [style*="background-image"]');
    for (let i = 0; i < bgEls.length; i++) {
      try {
        const bg = (bgEls[i].style && bgEls[i].style.backgroundImage) || '';
        const m = String(bg).match(/url\(["']?([^"')]+)["']?\)/i);
        if (m) pushImg(m[1], '');
      } catch (e) {}
    }
    // 2) HTML 字符串兜底（避免正则字面量转义踩坑）
    try {
      const html = a.outerHTML || '';
      const markers = [
        'https://pbs.twimg.com/media/',
        'https://pbs.twimg.com/ext_tw_video_thumb/',
        'https://pbs.twimg.com/tweet_video_thumb/',
        'https://pbs.twimg.com/amplify_video_thumb/',
      ];
      for (let mi = 0; mi < markers.length; mi++) {
        let from = 0;
        const mk = markers[mi];
        while (true) {
          const idx = html.indexOf(mk, from);
          if (idx < 0) break;
          let end = idx;
          while (end < html.length) {
            const ch = html.charAt(end);
            if (ch === '"' || ch === "'" || ch === ' ' || ch === '<' || ch === '>' || ch === ')' || ch === '\\') break;
            end++;
          }
          pushImg(html.slice(idx, end).replace(/&amp;/g, '&'), '');
          from = idx + mk.length;
        }
      }
    } catch (e) {}
    // 3) React Fiber：不依赖图片是否可见
    try {
      const keys = Object.keys(a);
      let fiberKey = '';
      for (let i = 0; i < keys.length; i++) {
        if (keys[i].indexOf('__reactFiber$') === 0 || keys[i].indexOf('__reactInternalInstance$') === 0) {
          fiberKey = keys[i];
          break;
        }
      }
      if (fiberKey) {
        const seenNode = new Set();
        function walkFiber(node, depth) {
          if (!node || depth > 40 || seenNode.has(node)) return;
          seenNode.add(node);
          let props = null;
          try { props = node.memoizedProps || node.pendingProps || null; } catch (e) { props = null; }
          if (props && typeof props === 'object') {
            const bags = [];
            try {
              if (Array.isArray(props.media)) bags.push(props.media);
              if (props.entities && Array.isArray(props.entities.media)) bags.push(props.entities.media);
              if (props.extended_entities && Array.isArray(props.extended_entities.media)) bags.push(props.extended_entities.media);
              const legacy = props.legacy || null;
              if (legacy) {
                if (legacy.entities && Array.isArray(legacy.entities.media)) bags.push(legacy.entities.media);
                if (legacy.extended_entities && Array.isArray(legacy.extended_entities.media)) bags.push(legacy.extended_entities.media);
              }
            } catch (e) {}
            for (let bi = 0; bi < bags.length; bi++) {
              const bag = bags[bi];
              for (let mi = 0; mi < bag.length; mi++) {
                const mm = bag[mi];
                if (!mm || typeof mm !== 'object') continue;
                pushImg(mm.media_url_https || mm.media_url || mm.preview_image_url || '', mm.ext_alt_text || mm.alt || '');
              }
            }
          }
          try { walkFiber(node.child, depth + 1); } catch (e) {}
          try { walkFiber(node.sibling, depth + 1); } catch (e) {}
        }
        walkFiber(a[fiberKey], 0);
      }
    } catch (e) {}
    const hasPhotoLink = !!a.querySelector("a[href*='/photo/'], a[href*='/video/'], [data-testid='tweetPhoto']");
    out.push({
      tweet_id: st.tweet_id,
      url: st.url,
      author,
      text,
      created_at,
      time_label,
      images,
      has_media: images.length > 0 || hasPhotoLink,
    });
  } catch (e) {}
}
return out;
"""


_STATUS_IMAGES_JS = r"""
function mediaUrl(u){
  try {
    if (!u) return '';
    let href = String(u);
    if (!/^https?:\/\//i.test(href)) href = new URL(href, location.origin).href;
    const url = new URL(href);
    if (/pbs\.twimg\.com|twimg\.com/i.test(url.hostname)) {
      if (!url.searchParams.get('format')) {
        const path = (url.pathname || '').toLowerCase();
        let fmt = 'jpg';
        if (path.endsWith('.png')) fmt = 'png';
        else if (path.endsWith('.webp')) fmt = 'webp';
        else if (path.endsWith('.gif')) fmt = 'gif';
        url.searchParams.set('format', fmt);
      }
      url.searchParams.set('name', 'large');
      return url.href;
    }
    return url.href;
  } catch (e) { return String(u || ''); }
}
const images = [];
const seen = new Set();
function push(raw, alt) {
  if (!raw) return;
  if (/profile_images|emoji|hashflag/i.test(raw)) return;
  if (!/pbs\.twimg\.com\/(media|ext_tw_video_thumb|tweet_video_thumb|amplify_video_thumb)/i.test(raw)) return;
  const url = mediaUrl(raw).replace(/([?&]name=)[^&]+/i, '$1large');
  if (!url || seen.has(url)) return;
  seen.add(url);
  images.push({ url, alt: String(alt || '').slice(0, 300) });
}
const arts = [...document.querySelectorAll("article[data-testid='tweet']")];
const a = arts[0] || document.body;
for (const img of a.querySelectorAll('img')) {
  push(img.currentSrc || img.getAttribute('src') || '', img.getAttribute('alt') || '');
}
for (const v of a.querySelectorAll('video')) {
  push(v.getAttribute('poster') || v.poster || '', 'video');
}
try {
  const html = a.outerHTML || '';
  const re = /https?:\/\/pbs\.twimg\.com\/(?:media|ext_tw_video_thumb|tweet_video_thumb|amplify_video_thumb)\/[A-Za-z0-9_-]+(?:\?[^"'\s<>]*)?/g;
  for (const u of (html.match(re) || [])) push(u.replace(/&amp;/g, '&'), '');
} catch (e) {}
return images;
"""


_WAKE_MEDIA_JS = r"""
(() => {
  const arts = [...document.querySelectorAll("article[data-testid='tweet']")].slice(0, 30);
  for (const a of arts) {
    try { a.scrollIntoView({ block: 'nearest', inline: 'nearest' }); } catch (e) {}
    for (const img of a.querySelectorAll('img')) {
      try {
        if (img.loading === 'lazy') img.loading = 'eager';
        if (!img.getAttribute('src') && img.srcset) {
          const u = String(img.srcset).split(',')[0].trim().split(/\s+/)[0];
          if (u) img.setAttribute('src', u);
        }
        if (!img.getAttribute('src') && img.currentSrc) img.setAttribute('src', img.currentSrc);
      } catch (e) {}
    }
  }
  return arts.length;
})()
"""


def _feed_js(handle: str = "", *, filter_author: bool = True) -> str:
    """按博主 handle 过滤（排除时间线上的转推/他人帖）。搜索页应 filter_author=False。"""
    h = re.sub(r"[^A-Za-z0-9_]", "", (handle or "").lstrip("@")).lower()
    if not h or not filter_author:
        return LIST_FEED_JS
    filter_tail = f"""
const __want = "{h}";
for (let i = out.length - 1; i >= 0; i--) {{
  const a = (out[i].author || "").toLowerCase().replace(/^@/, "");
  if (a && a !== __want) out.splice(i, 1);
}}
return out;
"""
    base = LIST_FEED_JS.rstrip()
    if base.endswith("return out;"):
        return base[: -len("return out;")] + filter_tail
    return base + filter_tail


def _merge_tweet_item(store: Dict[str, Dict[str, Any]], it: Dict[str, Any]) -> bool:
    """
    写入/补全推文。首次无图、后续懒加载出图时合并 images，避免永远丢图。
    返回是否为新 tweet_id。
    """
    tid = str(it.get("tweet_id") or "").strip()
    if not tid:
        return False
    old = store.get(tid)
    if old is None:
        store[tid] = dict(it)
        return True
    # 补全文案
    new_text = str(it.get("text") or "").strip()
    old_text = str(old.get("text") or "").strip()
    if len(new_text) > len(old_text):
        old["text"] = it.get("text")
    if not old.get("created_at") and it.get("created_at"):
        old["created_at"] = it.get("created_at")
    if not old.get("time_label") and it.get("time_label"):
        old["time_label"] = it.get("time_label")
    if not old.get("author") and it.get("author"):
        old["author"] = it.get("author")
    if not old.get("url") and it.get("url"):
        old["url"] = it.get("url")
    if it.get("has_media"):
        old["has_media"] = True
    # 合并图片（按 url 去重）
    old_imgs = list(old.get("images") or []) if isinstance(old.get("images"), list) else []
    new_imgs = list(it.get("images") or []) if isinstance(it.get("images"), list) else []
    if new_imgs:
        seen = set()
        merged = []
        for im in old_imgs + new_imgs:
            if not isinstance(im, dict):
                continue
            u = str(im.get("url") or "").strip()
            if not u or u in seen:
                continue
            seen.add(u)
            merged.append(im)
        old["images"] = merged
        if merged:
            old["has_media"] = True
    store[tid] = old
    return False


def _wake_timeline_media(page) -> None:
    """静默唤醒懒加载：不 activate、不抢焦点，只滚 DOM + eager。"""
    try:
        page.eval_js(_WAKE_MEDIA_JS)
    except Exception:
        pass
    time.sleep(0.25)


def _enrich_missing_images(page, items: List[Dict[str, Any]], *, progress: ProgressCb = None, limit: int = 20) -> int:
    """
    时间线抽不到图、但标记 has_media 的条目：静默打开原帖补图（不抢焦点）。
    """
    need = [
        it
        for it in items
        if isinstance(it, dict)
        and it.get("has_media")
        and not (isinstance(it.get("images"), list) and it.get("images"))
        and "/status/" in str(it.get("url") or "")
    ][: max(1, int(limit))]
    if not need:
        any_img = any(isinstance(it.get("images"), list) and it.get("images") for it in items if isinstance(it, dict))
        if not any_img:
            need = [
                it
                for it in items
                if isinstance(it, dict) and "/status/" in str(it.get("url") or "")
            ][: min(8, max(1, int(limit)))]
    if not need:
        return 0
    filled = 0
    _log(progress, f"补图：静默打开原帖抽取（{len(need)} 条，不抢焦点）…")
    for it in need:
        url = str(it.get("url") or "").strip()
        if not url:
            continue
        try:
            page.silent_navigate(url)
            time.sleep(2.0)
            _wake_timeline_media(page)
            raw = page.eval_js(_STATUS_IMAGES_JS) or []
            if not isinstance(raw, list):
                raw = []
            imgs = [x for x in raw if isinstance(x, dict) and x.get("url")]
            if imgs:
                it["images"] = imgs
                filled += 1
                _log(progress, f"  补图成功 · {it.get('tweet_id')} · {len(imgs)} 张")
            else:
                _log(progress, f"  补图空 · {it.get('tweet_id')}")
        except Exception as e:
            _log(progress, f"  补图失败 · {it.get('tweet_id')}: {e}")
    return filled


def _scroll_feed_page(page, *, rounds: int = 4, aggressive: bool = False) -> None:
    """滚动时间线；卡顿时用更猛的策略把最后一条推文滚进视口并触底。"""
    n = max(1, int(rounds))
    page.eval_js(
        f"""
(() => {{
  const aggressive = {str(aggressive).lower()};
  const delta = Math.max(window.innerHeight * (aggressive ? 1.35 : 0.95), aggressive ? 1800 : 1400);
  const tweets = [...document.querySelectorAll("article[data-testid='tweet']")];
  const last = tweets.length ? tweets[tweets.length - 1] : null;
  if (last) {{
    try {{ last.scrollIntoView({{ block: 'end', inline: 'nearest' }}); }} catch (e) {{}}
  }}
  const findScrollable = (start) => {{
    let el = start;
    while (el && el !== document.documentElement) {{
      const st = window.getComputedStyle(el);
      const oy = st.overflowY || '';
      if ((oy === 'auto' || oy === 'scroll' || oy === 'overlay') && el.scrollHeight > el.clientHeight + 40) {{
        return el;
      }}
      el = el.parentElement;
    }}
    return null;
  }};
  const candidates = [
    last && findScrollable(last),
    document.querySelector('[data-testid="primaryColumn"]'),
    document.querySelector('main[role="main"]'),
    document.scrollingElement,
    document.documentElement,
    document.body,
  ].filter(Boolean);
  for (let r = 0; r < {n}; r++) {{
    for (const el of candidates) {{
      try {{
        el.scrollTop = el.scrollTop + delta;
        if (aggressive) el.scrollTop = el.scrollHeight;
      }} catch (e) {{}}
    }}
    window.scrollBy(0, delta);
  }}
  window.scrollTo(0, Math.max(
    document.body.scrollHeight,
    document.documentElement.scrollHeight,
    (document.scrollingElement && document.scrollingElement.scrollHeight) || 0
  ));
  if (aggressive && last) {{
    try {{ last.scrollIntoView({{ block: 'start', inline: 'nearest' }}); }} catch (e) {{}}
    window.scrollBy(0, delta);
  }}
  return document.querySelectorAll("article[data-testid='tweet']").length;
}})()
"""
    )
    # 键盘翻页兜底（X 虚拟列表有时只认按键滚动）
    try:
        page.eval_js(
            """
(() => {
  const tgt = document.querySelector('[data-testid="primaryColumn"]')
    || document.querySelector('main')
    || document.body;
  if (tgt && tgt.focus) try { tgt.focus(); } catch (e) {}
  for (const key of ['PageDown', 'PageDown', 'End']) {
    for (const type of ['keydown', 'keyup']) {
      window.dispatchEvent(new KeyboardEvent(type, { key, code: key, bubbles: true, cancelable: true }));
      document.dispatchEvent(new KeyboardEvent(type, { key, code: key, bubbles: true, cancelable: true }));
    }
  }
  return true;
})()
"""
        )
    except Exception:
        pass


def _prepare_timeline_page(page, *, kind: str, prefer_live: bool = True) -> None:
    """搜索/主页：点对应 Tab，尽量等首屏推文渲染。"""
    kind_l = (kind or "").lower()
    if kind_l == "search":
        prefer = "live" if prefer_live else "top"
        page.eval_js(
            f"""
(() => {{
  const prefer = "{prefer}";
  const tabs = [...document.querySelectorAll('a[role="tab"]')];
  const isLive = t => /Latest|最新|Recent|实时|Live/i.test((t.textContent||'').trim());
  const isTop = t => /Top|热门|Relevant/i.test((t.textContent||'').trim());
  const pick = prefer === "live"
    ? (tabs.find(isLive) || tabs.find(isTop))
    : (tabs.find(isTop) || tabs.find(isLive));
  if (pick) pick.click();
  return true;
}})()
"""
        )
        time.sleep(2.0)
    elif kind_l == "profile":
        page.eval_js(
            """
(() => {
  const tabs = [...document.querySelectorAll('a[role="tab"]')];
  const posts = tabs.find(t => /^(Posts|帖子|Post)$/i.test((t.textContent||'').trim()));
  if (posts) posts.click();
  return true;
})()
"""
        )
        time.sleep(1.5)


def _dom_tweet_count(page) -> int:
    try:
        n = page.eval_js(
            "return document.querySelectorAll(\"article[data-testid='tweet']\").length"
        )
        return int(n or 0)
    except Exception:
        return 0


_DIAG_FEED_JS = r"""
(() => {
  const lim = __LIMIT__;
  const arts = [...document.querySelectorAll("article[data-testid='tweet']")].slice(0, lim);
  return arts.map((a, i) => {
    const links = [...a.querySelectorAll("a[href*='status']")]
      .map(l => (l.getAttribute('href') || '').trim())
      .filter(Boolean)
      .slice(0, 4);
    const hasTime = !!a.querySelector('time');
    const hasText = !!a.querySelector('[data-testid="tweetText"]');
    let tweet_id = '';
    for (const h of links) {
      const m = (h || '').match(/status\/(\d+)/i);
      if (m) { tweet_id = m[1]; break; }
    }
    return {
      i: i + 1,
      links: links,
      hasTime: hasTime,
      hasText: hasText,
      tweet_id: tweet_id,
      preview: (a.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 100)
    };
  });
})()
"""


def _diagnose_feed_dom(page, *, limit: int = 4) -> List[Dict[str, Any]]:
    """抽取为空时诊断：每条 article 的链接/时间/正文情况。"""
    lim = max(1, min(int(limit), 8))
    script = _DIAG_FEED_JS.replace("__LIMIT__", str(lim))
    try:
        raw = page.eval_js(script)
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
    except Exception:
        pass
    return []


def _user_search_url(
    handle: str,
    since: datetime,
    *,
    live: bool = False,
    until: Optional[datetime] = None,
) -> str:
    from urllib.parse import quote

    h = re.sub(r"[^A-Za-z0-9_]", "", (handle or "").lstrip("@"))
    since_local = since
    if since_local.tzinfo is None:
        since_local = since_local.replace(tzinfo=timezone.utc)
    since_date = since_local.astimezone().strftime("%Y-%m-%d")
    q = f"from:{h} since:{since_date}"
    if until is not None:
        until_local = until
        if until_local.tzinfo is None:
            until_local = until_local.replace(tzinfo=timezone.utc)
        # X until: 为开区间，用次日日期更稳
        until_date = (until_local.astimezone() + timedelta(days=1)).strftime("%Y-%m-%d")
        q = f"{q} until:{until_date}"
    base = f"https://x.com/search?q={quote(q)}&src=typed_query"
    return f"{base}&f=live" if live else base


def _user_search_urls(handle: str, since: datetime) -> List[str]:
    """兼容旧调用：整段 since → Latest 优先，再 Top。"""
    return [
        _user_search_url(handle, since, live=True),
        _user_search_url(handle, since, live=False),
    ]


def _iter_backfill_chunks(
    since: datetime,
    *,
    until: Optional[datetime] = None,
    chunk_days: int = 5,
) -> List[Tuple[datetime, datetime]]:
    """
    将 [since, until] 切成若干短窗口（新→旧），避免 X 搜索深滚失效。
    返回 [(chunk_since, chunk_until_inclusive), ...]
    """
    end = until or datetime.now(timezone.utc).astimezone()
    start = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if end < start:
        start, end = end, start
    days = max(1, int(chunk_days or 5))
    chunks: List[Tuple[datetime, datetime]] = []
    cursor = end
    while cursor > start:
        chunk_start = max(start, cursor - timedelta(days=days - 1))
        # 归一到本地日界，便于 since/until 日期串
        cs = chunk_start.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        ce = cursor.astimezone()
        if cs < start.astimezone():
            cs = start.astimezone()
        chunks.append((cs, ce))
        cursor = cs - timedelta(seconds=1)
        if len(chunks) >= 40:
            break
    return chunks


def _crawl_timeline_at_url(
    *,
    url: str,
    label: str,
    handle: str,
    since: datetime,
    max_tweets: int,
    max_scroll: int,
    progress: ProgressCb,
    should_abort: Optional[Callable[[], bool]],
    page,
    filter_author: bool = True,
    page_kind: str = "profile",
    prefer_live: bool = True,
    stall_limit: int = 18,
) -> Dict[str, Any]:
    since_cmp = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
    feed_js = _feed_js(handle, filter_author=filter_author)
    by_id: Dict[str, Dict[str, Any]] = {}
    seen_log: set = set()
    page_seen = 0
    page_old = 0
    window_exhausted = False
    lazy_stall = 0
    stall_stop = max(8, min(int(stall_limit or 18), 40))

    _log(progress, f"打开 {label}：{url}")
    page.silent_navigate(url)
    wait_s = 5.0 if page_kind == "search" else 3.5
    time.sleep(wait_s)
    _prepare_timeline_page(page, kind=page_kind, prefer_live=prefer_live)

    for round_i in range(max_scroll):
        if should_abort and should_abort():
            _log(progress, "抓取已终止（滚动中）")
            break
        _wake_timeline_media(page)
        try:
            raw = page.eval_js(feed_js) or []
        except Exception as e:
            _log(progress, f"抽取失败 round={round_i + 1}: {e}")
            raw = []
        if not isinstance(raw, list):
            raw = []
        if not raw:
            dom_n = _dom_tweet_count(page)
            if dom_n:
                _log(
                    progress,
                    f"{label} DOM 可见 {dom_n} 条 article，但抽取为空"
                    + ("（已关作者过滤）" if not filter_author else "（检查登录或页面结构）"),
                )
                if round_i == 0 or round_i % 5 == 0:
                    for diag in _diagnose_feed_dom(page):
                        _log(
                            progress,
                            f"  诊断 #{diag.get('i')} id={diag.get('tweet_id') or '-'}"
                            f" time={bool(diag.get('hasTime'))} text={bool(diag.get('hasText'))}"
                            f" links={diag.get('links') or []}"
                            f" | {(diag.get('preview') or '')[:80]}",
                        )
            elif round_i == 0:
                _log(progress, f"{label} 首屏无推文 DOM，继续滚动…")

        oldest_in_batch = None
        new_in_round = 0
        new_in_window = 0
        new_all_old = True
        for it in raw:
            if not isinstance(it, dict):
                continue
            tid = str(it.get("tweet_id") or "").strip()
            if not tid:
                continue
            created = parse_dt(str(it.get("created_at") or ""))
            if created is not None and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            too_old = bool(created and created < since_cmp)
            if created:
                if oldest_in_batch is None or created < oldest_in_batch:
                    oldest_in_batch = created

            if tid not in seen_log:
                seen_log.add(tid)
                page_seen += 1
                new_in_round += 1
                if too_old:
                    page_old += 1
                    _log(progress, f"[页面] #{page_seen} 过旧 · {fmt_tweet_line(it)}")
                else:
                    nimg = len(it.get("images") or []) if isinstance(it.get("images"), list) else 0
                    _log(
                        progress,
                        f"[页面] #{page_seen} 纳入 · {fmt_tweet_line(it)}"
                        + (f" · 图{nimg}" if nimg else ""),
                    )
                if not too_old:
                    new_all_old = False

            if too_old:
                continue
            is_new = _merge_tweet_item(by_id, it)
            if is_new:
                new_in_window += 1

        _log(
            progress,
            f"{label} 滚动 {round_i + 1}/{max_scroll} · 窗口内 {len(by_id)} · 页面 {page_seen}"
            f"（本轮新 {new_in_round} / 入窗 {new_in_window}）"
            + (f" · 本批最旧 {oldest_in_batch.isoformat()}" if oldest_in_batch else ""),
        )

        if len(by_id) >= max_tweets:
            break

        if new_in_round > 0:
            lazy_stall = 0
            if new_all_old:
                window_exhausted = True
        else:
            lazy_stall += 1

        # 仅当「新加载的全是过旧帖」且连续多轮滚不动，才认为滚出时间窗（置顶老帖不会误触发）
        if window_exhausted and lazy_stall >= 4:
            _log(
                progress,
                f"{label}：已滚出时间窗且连续 {lazy_stall} 轮无新帖，停止",
            )
            break
        if lazy_stall >= stall_stop:
            _log(
                progress,
                f"{label}：连续 {lazy_stall} 轮 DOM 无新帖，停止（可检查 CDP 是否已登录 X）",
            )
            break

        try:
            _scroll_feed_page(
                page,
                rounds=4 if lazy_stall >= 3 else 2,
                aggressive=lazy_stall >= 2,
            )
        except Exception:
            break
        time.sleep(2.2 if lazy_stall >= 3 else (1.8 if lazy_stall else 1.35))

    items = list(by_id.values())

    def _key(x: Dict[str, Any]):
        dt = parse_dt(str(x.get("created_at") or ""))
        return dt or datetime(1970, 1, 1, tzinfo=timezone.utc)

    items.sort(key=_key, reverse=True)
    return {
        "items": items[:max_tweets],
        "page_seen": page_seen,
        "page_old": page_old,
        "count": min(len(items), max_tweets),
    }


def _log(cb: ProgressCb, msg: str) -> None:
    """有 progress 时交给控制台统一打印，避免重复。"""
    if cb:
        try:
            cb(msg)
            return
        except Exception:
            pass
    print(f"[signals] {msg}", flush=True)


def _debugger_host() -> str:
    try:
        from signals.store import resolve_signals_debugger_url

        return resolve_signals_debugger_url()
    except Exception:
        try:
            from utils.crawl_cdp import resolve_crawl_debugger_url

            return resolve_crawl_debugger_url()
        except Exception:
            return "127.0.0.1:9223"


def _patch_debugger_host(host: str):
    """临时覆盖 allnews debugger 地址。"""
    try:
        import allnews_mornitor.cdp_browser as cdp_mod

        orig = cdp_mod.get_debugger_url

        def _patched() -> str:
            return host

        cdp_mod.get_debugger_url = _patched  # type: ignore
        return orig
    except Exception:
        return None


def _list_page_targets() -> List[Dict[str, Any]]:
    """Chrome /json/list 中所有 page 类型标签（顺序与窗口一致，末项即最后一个页签）。"""
    from allnews_mornitor.cdp_browser import _http_json

    try:
        pages = _http_json("/json/list")
    except Exception:
        return []
    if not isinstance(pages, list):
        return []
    out: List[Dict[str, Any]] = []
    for p in pages:
        if isinstance(p, dict) and p.get("type") == "page":
            out.append(p)
    return out


def _close_session(*, log: ProgressCb = None) -> None:
    global _SESSION
    with _SESSION_LOCK:
        sess = _SESSION
        _SESSION = None
    if not sess:
        return
    page = sess.get("page")
    client = sess.get("client")
    if page is not None:
        try:
            page.close()
        except Exception:
            pass
    if client is not None:
        try:
            client.close()
        except Exception:
            pass
    if log:
        _log(log, "CDP 列表抓取标签已关闭")


def _session_alive(sess: Dict[str, Any]) -> bool:
    client = sess.get("client")
    page = sess.get("page")
    if client is None or page is None:
        return False
    if getattr(client, "_closed", False):
        return False
    try:
        page.eval_js("1+1")
        return True
    except Exception:
        return False


def _acquire_list_page(list_url: str, *, progress: ProgressCb = None) -> Tuple[Any, Any]:
    """
    复用 Chrome 最后一个页签抓取列表，避免周期任务每次 Target.createTarget 新开 tab。
    """
    from allnews_mornitor.cdp_browser import BackgroundTarget, _CdpClient, _browser_ws_url, _http_json

    global _SESSION

    with _SESSION_LOCK:
        if _SESSION and _session_alive(_SESSION):
            page = _SESSION["page"]
            _log(progress, f"CDP 复用会话页签 → {list_url}")
            page.silent_navigate(list_url)
            return _SESSION["client"], page

        _close_session()

        try:
            _http_json("/json/version")
        except Exception as e:
            raise RuntimeError(
                f"无法连接 Chrome CDP，请先 --remote-debugging-port=9223: {e}"
            ) from e

        client = _CdpClient(_browser_ws_url())
        page = None
        pages = _list_page_targets()

        if pages:
            tid = str(pages[-1].get("id") or "")
            try:
                page = BackgroundTarget.attach(client, tid)
                _log(
                    progress,
                    f"CDP 附着最后一个页签（未新建 tab，当前共 {len(pages)} 个）",
                )
            except Exception:
                page = None

        if page is None:
            page = BackgroundTarget.create(client, _SIGNALS_TAB_BLANK)
            _log(progress, "CDP 无可用页签，建立后台专用标签（仅此一次）")

        _SESSION = {
            "client": client,
            "page": page,
            "target_id": page.target_id,
        }
        page.silent_navigate(list_url)
        return client, page


def close_list_crawl_tab(*, log: ProgressCb = None) -> None:
    """手动关闭列表抓取专用标签（一般不必调用，周期任务会自动复用）。"""
    _close_session(log=log)


def normalize_twimg_url(url: str) -> str:
    """补全 pbs.twimg.com 缺失的 format/name，避免 404。"""
    raw = str(url or "").strip()
    if not raw:
        return ""
    if "twimg.com" not in raw and "pbs." not in raw:
        return raw
    try:
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

        parsed = urlparse(raw)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        if "format" not in qs or not qs.get("format"):
            path_l = (parsed.path or "").lower()
            fmt = "jpg"
            if path_l.endswith(".png"):
                fmt = "png"
            elif path_l.endswith(".webp"):
                fmt = "webp"
            elif path_l.endswith(".gif"):
                fmt = "gif"
            qs["format"] = [fmt]
        qs["name"] = ["large"]
        flat = [(k, v[0] if isinstance(v, list) and v else v) for k, v in qs.items()]
        return urlunparse(parsed._replace(query=urlencode(flat)))
    except Exception:
        if "?" not in raw:
            return f"{raw}?format=jpg&name=large"
        return raw


def download_image(url: str, tweet_id: str, index: int) -> Dict[str, Any]:
    """下载配图到 output/signals/media/，失败则仅保留远端 URL。"""
    fixed = normalize_twimg_url(url)
    info: Dict[str, Any] = {"url": fixed or url, "local": "", "rel": "", "alt": ""}
    if not fixed and not url:
        return info
    root = media_root()
    ext = ".jpg"
    m = re.search(r"format=(\w+)", fixed or url, re.I)
    if m:
        fmt = m.group(1).lower()
        ext = ".png" if fmt == "png" else ".webp" if fmt == "webp" else ".gif" if fmt == "gif" else ".jpg"
    elif ".png" in (fixed or url):
        ext = ".png"
    name = f"{tweet_id}_{index}{ext}"
    dest = root / name
    last_err = ""
    for candidate in (fixed, url):
        if not candidate:
            continue
        try:
            req = urllib.request.Request(
                candidate,
                headers={
                    "User-Agent": "Mozilla/5.0 TrendRadarSignals/1.0",
                    "Referer": "https://x.com/",
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
            if data:
                dest.write_bytes(data)
                info["local"] = str(dest)
                info["rel"] = name
                info["url"] = candidate
                info.pop("error", None)
                return info
        except Exception as e:
            last_err = str(e)[:120]
    if last_err:
        info["error"] = last_err
    return info


def crawl_list_timeline(
    list_id: str,
    *,
    since: datetime,
    max_tweets: int = 40,
    max_scroll: int = 18,
    progress: ProgressCb = None,
    should_abort: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """
    静默 CDP 打开列表页，滚动直到推文时间早于 since 或达到上限。
    should_abort: 返回 True 时提前结束滚动。
    """
    from allnews_mornitor.cdp_browser import _http_json

    lid = parse_list_id(list_id) or str(list_id or "").strip()
    if not lid:
        return {"success": False, "error": "缺少 list_id", "items": []}
    url = f"https://x.com/i/lists/{lid}"
    max_tweets = max(1, min(int(max_tweets or 40), 120))
    max_scroll = max(3, min(int(max_scroll or 18), 40))

    def _aborted() -> bool:
        try:
            return bool(should_abort and should_abort())
        except Exception:
            return False

    host = _debugger_host()
    _orig = _patch_debugger_host(host)

    page = None
    try:
        try:
            _http_json("/json/version")
        except Exception as e:
            return {
                "success": False,
                "error": f"无法连接 Chrome CDP（{host}），请先 --remote-debugging-port=9223: {e}",
                "items": [],
            }

        _, page = _acquire_list_page(url, progress=progress)
        time.sleep(2.5)

        by_id: Dict[str, Dict[str, Any]] = {}
        seen_log: set = set()
        page_seen = 0
        page_kept = 0
        page_old = 0
        reached_old = False
        for round_i in range(max_scroll):
            if _aborted():
                _log(progress, "抓取已终止（滚动中）")
                break
            _wake_timeline_media(page)
            try:
                raw = page.eval_js(LIST_FEED_JS) or []
            except Exception as e:
                _log(progress, f"抽取失败 round={round_i}: {e}")
                raw = []
            if not isinstance(raw, list):
                raw = []
            oldest_in_batch = None
            new_in_round = 0
            for it in raw:
                if not isinstance(it, dict):
                    continue
                tid = str(it.get("tweet_id") or "").strip()
                if not tid:
                    continue
                created = parse_dt(str(it.get("created_at") or ""))
                if created is not None and created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                since_cmp = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
                too_old = bool(created and created < since_cmp)
                if created:
                    if oldest_in_batch is None or created < oldest_in_batch:
                        oldest_in_batch = created
                    if too_old:
                        reached_old = True

                if tid not in seen_log:
                    seen_log.add(tid)
                    page_seen += 1
                    new_in_round += 1
                    if too_old:
                        page_old += 1
                        _log(
                            progress,
                            f"[页面] #{page_seen} 过旧跳过 · {fmt_tweet_line(it)}",
                        )
                    else:
                        page_kept += 1
                        nimg = len(it.get("images") or []) if isinstance(it.get("images"), list) else 0
                        _log(
                            progress,
                            f"[页面] #{page_seen} 纳入候选 · {fmt_tweet_line(it)}"
                            + (f" · 图{nimg}" if nimg else ""),
                        )

                if too_old:
                    continue
                _merge_tweet_item(by_id, it)
            _log(
                progress,
                f"滚动 {round_i + 1}/{max_scroll} · 窗口内累计 {len(by_id)} · 页面见过 {page_seen}"
                f"（新 {new_in_round}）"
                + (f" · 本批最旧 {oldest_in_batch.isoformat()}" if oldest_in_batch else ""),
            )
            if len(by_id) >= max_tweets:
                break
            if reached_old and len(by_id) >= 3:
                break
            # 全是过旧且已滚几屏：停止
            if reached_old and len(by_id) == 0 and round_i >= 2:
                _log(progress, "页面可见帖均早于时间窗，停止继续滚动")
                break
            try:
                page.eval_js("window.scrollBy(0, 1400); return true;")
            except Exception:
                break
            time.sleep(1.15)
            if _aborted():
                _log(progress, "抓取已终止（滚动中）")
                break

        items = list(by_id.values())

        def _key(x: Dict[str, Any]):
            dt = parse_dt(str(x.get("created_at") or ""))
            return dt or datetime(1970, 1, 1, tzinfo=timezone.utc)

        items.sort(key=_key, reverse=True)
        items = items[:max_tweets]
        try:
            n_fill = _enrich_missing_images(page, items, progress=progress, limit=20)
            if n_fill:
                _log(progress, f"原帖补图完成 {n_fill} 条")
        except Exception as e:
            _log(progress, f"原帖补图跳过: {e}")
        img_n = sum(1 for it in items if isinstance(it.get("images"), list) and it.get("images"))
        _log(
            progress,
            f"抓取结束：窗口内 {len(items)} 条 · 含图 {img_n} · 页面见过 {page_seen}（过旧 {page_old}）",
        )
        return {
            "success": True,
            "list_id": lid,
            "url": url,
            "items": items,
            "count": len(items),
            "page_seen": page_seen,
            "page_old": page_old,
        }
    except Exception as e:
        _close_session()
        return {"success": False, "error": str(e), "items": []}
    finally:
        if _orig is not None:
            try:
                import allnews_mornitor.cdp_browser as cdp_mod

                cdp_mod.get_debugger_url = _orig  # type: ignore
            except Exception:
                pass
        # 保留 _SESSION 供下次周期抓取复用，不 detach / 不 close tab


def crawl_user_timeline(
    handle: str,
    *,
    since: datetime,
    max_tweets: int = 80,
    max_scroll: int = 24,
    progress: ProgressCb = None,
    should_abort: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """CDP 抓取博主时间窗推文：按日期切片搜索(Latest)，不足再补主页/回复。"""
    from allnews_mornitor.cdp_browser import _http_json
    from signals.store import parse_user_handle, user_profile_url

    h = parse_user_handle(handle) or str(handle or "").strip().lstrip("@")
    if not h:
        return {"success": False, "error": "缺少博主链接或 @handle", "items": []}
    profile_url = user_profile_url(h)
    max_tweets = max(1, min(int(max_tweets or 80), 300))
    # 单段深滚上限；整月靠切片叠加，不必单次滚上百轮
    max_scroll = max(18, min(int(max_scroll or 24), 60))
    now = datetime.now(timezone.utc).astimezone()
    span_days = max(1, (now - (since if since.tzinfo else since.replace(tzinfo=timezone.utc))).days + 1)
    # >7 天按 4~5 天切片，避免 X 搜索深滚失效只拿到最近几条
    chunk_days = 4 if span_days > 14 else (5 if span_days > 7 else span_days)
    chunks = _iter_backfill_chunks(since, until=now, chunk_days=chunk_days)
    search_urls: List[str] = []

    def _merge_items(into: Dict[str, Dict[str, Any]], res: Dict[str, Any]) -> Tuple[int, int]:
        seen = int(res.get("page_seen") or 0)
        old = int(res.get("page_old") or 0)
        for it in res.get("items") or []:
            tid = str(it.get("tweet_id") or "")
            if tid:
                into[tid] = it
        return seen, old

    def _aborted() -> bool:
        try:
            return bool(should_abort and should_abort())
        except Exception:
            return False

    host = _debugger_host()
    _orig = _patch_debugger_host(host)

    page = None
    try:
        try:
            _http_json("/json/version")
        except Exception as e:
            return {
                "success": False,
                "error": f"无法连接 Chrome CDP（{host}），请先 --remote-debugging-port=9223: {e}",
                "items": [],
            }

        first_url = _user_search_url(h, since, live=True, until=now)
        _, page = _acquire_list_page(first_url, progress=progress)

        merged: Dict[str, Dict[str, Any]] = {}
        total_seen = 0
        total_old = 0

        _log(
            progress,
            f"搜索切片 {len(chunks)} 段（每段约 {chunk_days} 天）· 目标最多 {max_tweets} 条",
        )
        for ci, (chunk_since, chunk_until) in enumerate(chunks, 1):
            if _aborted():
                break
            if len(merged) >= max_tweets:
                break
            live_url = _user_search_url(h, chunk_since, live=True, until=chunk_until)
            search_urls.append(live_url)
            label = (
                f"搜索切片{ci}/{len(chunks)}"
                f"（{chunk_since.strftime('%m-%d')}→{chunk_until.strftime('%m-%d')}）"
            )
            remain = max_tweets - len(merged)
            # 单段不必滚太深：短窗 + Latest 通常一屏到几屏就够
            seg_scroll = max(12, min(max_scroll, 28))
            search_res = _crawl_timeline_at_url(
                url=live_url,
                label=label,
                handle=h,
                since=chunk_since,
                max_tweets=remain,
                max_scroll=seg_scroll,
                progress=progress,
                should_abort=_aborted,
                page=page,
                filter_author=False,
                page_kind="search",
                prefer_live=True,
                stall_limit=12,
            )
            before = len(merged)
            ps, po = _merge_items(merged, search_res)
            total_seen += ps
            total_old += po
            gained = len(merged) - before
            _log(
                progress,
                f"{label} 本段新增 {gained} · 累计窗口内 {len(merged)}",
            )
            # 空段继续往更早切（可能该周没发帖），不要提前 break 整月

        min_want = max(10, min(max_tweets // 3, 40))
        if len(merged) < min_want and not _aborted():
            _log(
                progress,
                f"切片搜索仅 {len(merged)} 条，补充抓取主页时间线…",
            )
            profile_res = _crawl_timeline_at_url(
                url=profile_url,
                label="博主主页",
                handle=h,
                since=since,
                max_tweets=max_tweets,
                max_scroll=max_scroll,
                progress=progress,
                should_abort=_aborted,
                page=page,
                filter_author=True,
                page_kind="profile",
                stall_limit=18,
            )
            ps, po = _merge_items(merged, profile_res)
            total_seen += ps
            total_old += po

        if len(merged) < min_want and not _aborted():
            replies_url = f"{profile_url.rstrip('/')}/with_replies"
            _log(progress, f"主页仍仅 {len(merged)} 条，尝试回复时间线…")
            replies_res = _crawl_timeline_at_url(
                url=replies_url,
                label="博主回复",
                handle=h,
                since=since,
                max_tweets=max_tweets,
                max_scroll=max_scroll,
                progress=progress,
                should_abort=_aborted,
                page=page,
                filter_author=True,
                page_kind="profile",
                stall_limit=16,
            )
            ps, po = _merge_items(merged, replies_res)
            total_seen += ps
            total_old += po

        items = list(merged.values())

        def _key(x: Dict[str, Any]):
            dt = parse_dt(str(x.get("created_at") or ""))
            return dt or datetime(1970, 1, 1, tzinfo=timezone.utc)

        items.sort(key=_key, reverse=True)
        # 最终再按总 since 过滤，防止切片边界混入
        since_cmp = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
        filtered: List[Dict[str, Any]] = []
        for it in items:
            created = parse_dt(str(it.get("created_at") or ""))
            if created is not None and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created and created < since_cmp:
                continue
            filtered.append(it)
        items = filtered[:max_tweets]
        try:
            n_fill = _enrich_missing_images(page, items, progress=progress, limit=28)
            if n_fill:
                _log(progress, f"原帖补图完成 {n_fill} 条")
        except Exception as e:
            _log(progress, f"原帖补图跳过: {e}")
        img_n = sum(1 for it in items if isinstance(it.get("images"), list) and it.get("images"))
        _log(
            progress,
            f"博主抓取结束：@{h} 窗口内 {len(items)} 条 · 含图 {img_n} · 页面累计见过 {total_seen}（过旧 {total_old}）"
            f" · 切片 {len(chunks)}",
        )
        return {
            "success": True,
            "handle": h,
            "url": profile_url,
            "search_urls": search_urls,
            "chunks": len(chunks),
            "items": items,
            "count": len(items),
            "page_seen": total_seen,
            "page_old": total_old,
        }
    except Exception as e:
        _close_session()
        return {"success": False, "error": str(e), "items": []}
    finally:
        if _orig is not None:
            try:
                import allnews_mornitor.cdp_browser as cdp_mod

                cdp_mod.get_debugger_url = _orig  # type: ignore
            except Exception:
                pass
        # 保留 _SESSION 供下次抓取复用，不 detach / 不 close tab

