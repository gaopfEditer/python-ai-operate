# coding=utf-8
"""币安 Square 主页帖子抽取 JS（源自 auto-deal-eth/binance/market_lists_selenium.py，含配图/视频）。"""

_MEDIA_HELPERS_JS = r"""
function _bnNoiseImgUrl(src) {
  const s = (src || '').toLowerCase();
  if (!s || s.startsWith('data:')) return true;
  if (s.includes('avatar')) return true;
  if (s.includes('userpic')) return true;
  if (s.includes('/icon')) return true;
  if (s.includes('favicon')) return true;
  if (s.includes('emoji')) return true;
  if (s.includes('badge')) return true;
  if (s.includes('qrcode') || s.includes('qr-code')) return true;
  if (s.includes('sprite')) return true;
  if (s.includes('logo') && s.includes('binance')) return true;
  const wh = s.match(/\b(\d{1,3})x(\d{1,3})\b/);
  if (wh) {
    const w = parseInt(wh[1], 10), h = parseInt(wh[2], 10);
    if (w <= 96 && h <= 96) return true;
  }
  return false;
}
function _bnInAvatarOrHeader(im) {
  let n = im;
  for (let i = 0; i < 14 && n; i++) {
    const cls = String(n.className || '');
    const tag = (n.tagName || '').toLowerCase();
    if (/avatar|user-?pic|head-?portrait|author.?pic|profile.?pic/i.test(cls)) return true;
    if (tag === 'header' || tag === 'nav') return true;
    if (/sidebar|side-bar|leftnav|rightnav|global-nav/i.test(cls)) return true;
    n = n.parentElement;
  }
  return false;
}
function _bnCardFromAnchor(a) {
  return a.closest('article')
    || a.closest('[class*="article"]')
    || a.closest('[class*="Article"]')
    || a.closest('[class*="PostCard"]')
    || a.closest('[class*="post-card"]')
    || a.parentElement;
}
function _bnCollectArticleImagesRelaxed(a) {
  const card = _bnCardFromAnchor(a);
  if (!card) return [];
  const urls = [];
  const imgs = card.querySelectorAll('img[src]');
  for (const im of imgs) {
    if (!im || a.contains(im)) continue;
    if (_bnInAvatarOrHeader(im)) continue;
    let src = im.currentSrc || im.src
      || (im.getAttribute && (im.getAttribute('src') || im.getAttribute('data-src'))) || '';
    if (_bnNoiseImgUrl(src)) continue;
    const iw = im.naturalWidth || 0;
    const ih = im.naturalHeight || 0;
    const ir = im.getBoundingClientRect();
    if (iw > 0 && ih > 0) {
      if (iw < 64 || ih < 64) continue;
      if (iw * ih < 4096) continue;
    } else if (ir.width < 56 || ir.height < 56) continue;
    urls.push(src);
  }
  return [...new Set(urls)].slice(0, 16);
}
function _bnCollectVideoUrlFromCard(a) {
  const card = _bnCardFromAnchor(a);
  if (!card) return '';
  const vids = Array.from(card.querySelectorAll('video, source'));
  for (const v of vids) {
    const src = (v.currentSrc || v.src
      || (v.getAttribute && (v.getAttribute('src') || v.getAttribute('data-src'))) || '').trim();
    if (!src) continue;
    const s = src.toLowerCase();
    if (s.startsWith('blob:') || s.startsWith('data:')) continue;
    if (s.includes('avatar') || s.includes('emoji') || s.includes('icon')) continue;
    return src;
  }
  const av = card.querySelector('[class*="aspect-video"] video, [class*="aspect-video"] source');
  if (av) {
    const src = (av.currentSrc || av.src || av.getAttribute('src') || '').trim();
    if (src && !src.toLowerCase().startsWith('blob:')) return src;
  }
  return '';
}
function _bnLocaleFromPath() {
  const pm = (location.pathname || '').match(/^\/([a-z]{2}(?:-[A-Za-z]+)?)(\/|$)/i);
  return pm ? pm[1] : 'zh-CN';
}
function _bnReplayUrlFromContentId(id) {
  const cid = String(id || '').trim();
  if (!cid || !/^\d+$/.test(cid)) return '';
  const locale = _bnLocaleFromPath();
  return (location.origin || 'https://www.binance.com') + '/' + locale + '/square/audio/replay?id=' + cid;
}
function _bnCollectLiveReplayFromCard(el) {
  const card = _bnCardFromAnchor(el) || _bnFindCardRoot(el) || el;
  if (!card || !card.querySelector) return { replay_url: '', live_content_id: '' };
  const pick = card.querySelector('[class*="aspect-video"][data-content-id], [data-content-id][class*="aspect-video"]')
    || card.querySelector('[data-content-id]');
  if (!pick) return { replay_url: '', live_content_id: '' };
  const cid = String(pick.getAttribute('data-content-id') || '').trim();
  if (!cid || !/^\d+$/.test(cid)) return { replay_url: '', live_content_id: '' };
  return { replay_url: _bnReplayUrlFromContentId(cid), live_content_id: cid };
}
"""

PROFILE_POST_EXTRACT_JS = (
    _MEDIA_HELPERS_JS
    + r"""
function _bnNormTimeLabel(raw) {
  const t = String(raw || '').replace(/\s+/g, ' ').trim();
  if (!t) return '';
  if (/^(刚刚|昨天|今天|\d+\s*(?:秒|分钟|小时|天)(?:前)?|\d{1,2}\s*月\s*\d{1,2}\s*日|\d{4}-\d{2}-\d{2})/i.test(t)) return t;
  const rel = t.match(/(刚刚|昨天|今天|\d+\s*(?:秒|分钟|小时|天)(?:前)?)/);
  if (rel) return rel[1].trim();
  const m = t.match(/(\d{1,2}\s*月\s*\d{1,2}\s*日)/);
  if (m) return m[1].trim();
  const iso = t.match(/(\d{4}-\d{2}-\d{2})/);
  return iso ? iso[1] : '';
}
function _bnCardContentBox(root) {
  if (!root) return null;
  const pick = (box) => {
    if (!box || !box.querySelector) return null;
    if (box.querySelector('[class*="create-time"], .create-time, time[datetime]')) return box;
    return null;
  };
  if (root.matches && root.matches('.card-content-box, [class*="card-content-box"]')) {
    return pick(root) || root;
  }
  if (root.querySelector) {
    const hits = root.querySelectorAll('.card-content-box, [class*="card-content-box"]');
    for (const hit of hits) {
      const ok = pick(hit);
      if (ok) return ok;
    }
    const flex = root.querySelector('[class*="flex-1"][class*="min-w-0"]');
    const flexOk = pick(flex);
    if (flexOk) return flexOk;
  }
  let n = root;
  for (let i = 0; i < 24 && n; i++) {
    const cls = String(n.className || '');
    if (/card-content-box/i.test(cls)) {
      const ok = pick(n);
      if (ok) return ok;
    }
    n = n.parentElement;
  }
  return null;
}
function _bnFirstCreateTimeInCard(card) {
  if (!card || !card.querySelectorAll) return { publishedIso: '', timeLabel: '' };
  const nodes = [...card.querySelectorAll('[class*="create-time"], .create-time')];
  nodes.sort((a, b) => _bnAnchorTop(a) - _bnAnchorTop(b));
  for (const ct of nodes) {
    const got = _bnReadCreateTimeEl(ct);
    if (got.timeLabel || got.publishedIso) return got;
  }
  const times = [...card.querySelectorAll('time[datetime]')];
  times.sort((a, b) => _bnAnchorTop(a) - _bnAnchorTop(b));
  for (const te of times) {
    const got = _bnReadCreateTimeEl(te);
    if (got.timeLabel || got.publishedIso) return got;
  }
  return { publishedIso: '', timeLabel: '' };
}
function _bnReadCreateTimeEl(ct) {
  if (!ct) return { publishedIso: '', timeLabel: '' };
  const te = ct.matches && ct.matches('time[datetime]') ? ct : ct.querySelector('time[datetime]');
  let publishedIso = '';
  let timeLabel = '';
  if (te) {
    publishedIso = te.getAttribute('datetime') || '';
    timeLabel = _bnNormTimeLabel(te.innerText || te.textContent || '');
  }
  if (!timeLabel) timeLabel = _bnNormTimeLabel(ct.innerText || ct.textContent || '');
  return { publishedIso, timeLabel };
}
/** 列表卡片未点进详情：以 card-content-box 内 create-time 为准 */
function _bnReadCreateTimeFromContentBox(root) {
  const box = _bnCardContentBox(root);
  if (!box || !box.querySelector) return { publishedIso: '', timeLabel: '' };
  const ct = box.querySelector('[class*="create-time"], .create-time');
  if (ct) return _bnReadCreateTimeEl(ct);
  const te = box.querySelector('time[datetime]');
  if (te) return _bnReadCreateTimeEl(te);
  return { publishedIso: '', timeLabel: '' };
}
function _bnFindCreateTimeInCard(card) {
  const primary = _bnReadCreateTimeFromContentBox(card);
  if (primary.timeLabel || primary.publishedIso) return primary;
  if (!card || !card.querySelector) return { publishedIso: '', timeLabel: '' };
  const nodes = card.querySelectorAll('[class*="create-time"], .create-time, time[datetime]');
  for (const ct of nodes) {
    const got = _bnReadCreateTimeEl(ct);
    if (got.timeLabel || got.publishedIso) return got;
  }
  return { publishedIso: '', timeLabel: '' };
}
function _bnReadCreateTimeFromNickContainer(root) {
  if (!root || !root.querySelector) return { publishedIso: '', timeLabel: '' };
  const nick = root.querySelector('[class*="avatar-nick-container"]');
  if (!nick) return { publishedIso: '', timeLabel: '' };
  const ct = nick.querySelector('[class*="create-time"]') || nick.querySelector('.create-time');
  if (!ct) return { publishedIso: '', timeLabel: '' };
  let publishedIso = '';
  let timeLabel = '';
  const te = ct.querySelector('time[datetime]');
  if (te) {
    publishedIso = te.getAttribute('datetime') || '';
    timeLabel = _bnNormTimeLabel(te.innerText || '');
  }
  if (!timeLabel) timeLabel = _bnNormTimeLabel(ct.innerText || ct.textContent || '');
  return { publishedIso, timeLabel };
}
function _bnPostTimeFromCard(a) {
  let publishedIso = '';
  let timeLabel = '';
  let isPinned = false;
  const card = _bnCardFromAnchor(a);
  if (card) {
    const got = _bnReadCreateTimeFromContentBox(card);
    publishedIso = got.publishedIso;
    timeLabel = got.timeLabel;
    if (!timeLabel && !publishedIso) {
      const top = _bnFirstCreateTimeInCard(card);
      publishedIso = top.publishedIso;
      timeLabel = top.timeLabel;
    }
  }
  if (!timeLabel && !publishedIso) {
    let el = a;
    for (let depth = 0; depth < 24 && el; depth++) {
      const got = _bnReadCreateTimeFromNickContainer(el);
      if (got.timeLabel || got.publishedIso) {
        publishedIso = got.publishedIso;
        timeLabel = got.timeLabel;
        break;
      }
      el = el.parentElement;
    }
  }
  if ((!timeLabel || !publishedIso) && card) {
    const got = _bnFindCreateTimeInCard(card);
    if (!publishedIso) publishedIso = got.publishedIso;
    if (!timeLabel) timeLabel = got.timeLabel;
  }
  if (card && /置顶|pinned|🔝/i.test((card.innerText || '').slice(0, 900))) isPinned = true;
  return { published_iso: publishedIso, time_label: timeLabel, is_pinned: isPinned };
}
function _bnContentIdFromCard(el) {
  let root = el;
  for (let i = 0; i < 22 && root; i++) {
    const pairs = root.querySelector && root.querySelector('.trading-pairs, [class*="trading-pairs"]');
    if (pairs) {
      for (const a of pairs.querySelectorAll('a[href*="contentId="], a[href*="contentid="]')) {
        const href = a.getAttribute('href') || a.href || '';
        const m = href.match(/[?&]contentId=(\d+)/i);
        if (m && m[1]) return m[1];
      }
    }
    root = root.parentElement;
  }
  return '';
}
function _bnSquarePostHrefFromContentId(contentId) {
  const id = String(contentId || '').trim();
  if (!id) return '';
  let locale = 'zh-CN';
  const pm = (location.pathname || '').match(/^\/([a-z]{2}(?:-[A-Za-z]+)?)(\/|$)/i);
  if (pm) locale = pm[1];
  return (location.origin || 'https://www.binance.com') + '/' + locale + '/square/post/' + id;
}
function _bnFindCardRoot(el) {
  let n = el;
  for (let i = 0; i < 20 && n; i++) {
    const cls = String(n.className || '');
    if (n.matches && n.matches('article')) return n;
    if (/border-Line|PostCard|post-card|feed-item/i.test(cls)) return n;
    if (n.querySelector && n.querySelector('.trading-pairs, [class*="trading-pairs"], [class*="aspect-video"]')
        && n.querySelector('a[href*="/square/profile/"]')) return n;
    n = n.parentElement;
  }
  return el && el.parentElement ? el.parentElement : el;
}
function _bnAnchorTop(el) {
  try {
    const r = el.getBoundingClientRect();
    return (window.scrollY || 0) + r.top;
  } catch (e) {
    return 0;
  }
}
function _bnUpsertPost(byKey, item, top) {
  const h = item.href;
  if (!h) return;
  const cid = String(item.content_id || '').trim();
  const key = cid ? ('id:' + cid) : ('href:' + h);
  const prev = byKey.get(key);
  if (!prev) {
    byKey.set(key, { item, top: top });
    return;
  }
  const o = prev.item;
  if ((item.raw || '').length > (o.raw || '').length) {
    o.raw = item.raw;
    o.title = item.title || o.title;
  }
  function _bnTimeRank(it) {
    const iso = String((it && it.published_iso) || '').trim();
    const tl = String((it && it.time_label) || '').trim();
    let s = 0;
    if (iso) s += 8;
    if (/^\d{10,13}$/.test(iso) || iso.includes('-')) s += 12;
    if (tl) s += 2;
    if (/刚刚|昨天|今天|\d+\s*(?:秒|分钟|小时|天)|\d{1,2}\s*月\s*\d{1,2}\s*日/.test(tl)) s += 4;
    return s;
  }
  if (_bnTimeRank(item) > _bnTimeRank(o)) {
    if (item.time_label) o.time_label = item.time_label;
    if (item.published_iso) o.published_iso = item.published_iso;
  } else {
    if (!o.time_label && item.time_label) o.time_label = item.time_label;
    if (!o.published_iso && item.published_iso) o.published_iso = item.published_iso;
  }
  if (!o.video_url && item.video_url) o.video_url = item.video_url;
  if (!o.replay_url && item.replay_url) o.replay_url = item.replay_url;
  if (!o.live_content_id && item.live_content_id) o.live_content_id = item.live_content_id;
  if (item.image_urls && item.image_urls.length) {
    o.image_urls = [...new Set([...(o.image_urls || []), ...item.image_urls])].slice(0, 16);
  }
  o.is_pinned = o.is_pinned || item.is_pinned;
  if (top < prev.top) prev.top = top;
}
const maxItems = arguments[0];
const authorSlug = String(arguments[1] || '').toLowerCase();
const byKey = new Map();
const isNoise = (href) => {
  const h = (href || '').toLowerCase();
  return h.includes('/square/hashtag/') || h.includes('/square/topics/') || h.includes('/square/market')
    || h.includes('/square/leaderboard') || h.includes('fear-and-greed');
};
const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
const anchors = Array.from(document.querySelectorAll('a[href*="/square/"]')).filter((a) => {
  const h = ((a.href || '').split('#')[0] || '').toLowerCase();
  return h.includes('/square/post/') || h.includes('/square/video/') || h.includes('/square/article/');
});
anchors.sort((a, b) => _bnAnchorTop(a) - _bnAnchorTop(b));
for (const a of anchors) {
  const href = (a.href || '').split('#')[0];
  if (!href || isNoise(href)) continue;
  const text = (a.innerText || a.textContent || '').trim();
  const imageUrls = _bnCollectArticleImagesRelaxed(a);
  const videoUrl = _bnCollectVideoUrlFromCard(a);
  const live = _bnCollectLiveReplayFromCard(a);
  if ((!text || text.length < 4) && !videoUrl && !live.replay_url && imageUrls.length === 0) continue;
  const clean = norm(text);
  const parts = clean.split(' ').filter(Boolean);
  const title = parts.slice(0, 24).join(' ');
  const meta = _bnPostTimeFromCard(a);
  let contentId = _bnContentIdFromCard(a) || '';
  let finalHref = href;
  if (!contentId) {
    const hm = finalHref.match(/\/square\/(?:post|video|article)\/(\d+)/i);
    if (hm) contentId = hm[1];
  }
  if (contentId) {
    const byId = _bnSquarePostHrefFromContentId(contentId);
    if (byId) finalHref = byId;
  }
  _bnUpsertPost(byKey, {
    href: finalHref,
    title: title || (videoUrl ? '视频帖' : title),
    author_slug: authorSlug,
    raw: clean.slice(0, 2000),
    published_iso: meta.published_iso,
    time_label: meta.time_label,
    is_pinned: meta.is_pinned,
    content_id: contentId,
    image_urls: imageUrls,
    video_url: videoUrl,
    replay_url: live.replay_url || '',
    live_content_id: live.live_content_id || '',
  }, _bnAnchorTop(a));
}
const liveRoots = Array.from(document.querySelectorAll('[class*="aspect-video"][data-content-id], [data-content-id][class*="aspect-video"]'));
liveRoots.sort((a, b) => _bnAnchorTop(a) - _bnAnchorTop(b));
for (const el of liveRoots) {
  const liveCid = String(el.getAttribute('data-content-id') || '').trim();
  if (!liveCid || !/^\d+$/.test(liveCid)) continue;
  const replayUrl = _bnReplayUrlFromContentId(liveCid);
  if (!replayUrl) continue;
  const card = _bnFindCardRoot(el);
  const postCid = _bnContentIdFromCard(el) || '';
  const mergeKey = postCid ? ('id:' + postCid) : ('live:' + liveCid);
  if (postCid && byKey.has('id:' + postCid)) {
    const prev = byKey.get('id:' + postCid);
    const o = prev.item;
    if (!o.replay_url) o.replay_url = replayUrl;
    if (!o.live_content_id) o.live_content_id = liveCid;
    continue;
  }
  if (byKey.has(mergeKey)) continue;
  let finalHref = postCid ? _bnSquarePostHrefFromContentId(postCid) : replayUrl;
  const titleEl = card && card.querySelector('[class*="text-PrimaryText"], [class*="font-medium"]');
  let title = norm((titleEl && titleEl.innerText) || '');
  if (!title) title = '直播回放';
  const meta = _bnPostTimeFromCard(el);
  const imageUrls = _bnCollectArticleImagesRelaxed(el);
  const videoUrl = _bnCollectVideoUrlFromCard(el);
  _bnUpsertPost(byKey, {
    href: finalHref,
    title: title.slice(0, 120),
    author_slug: authorSlug,
    raw: norm((card && card.innerText) || title).slice(0, 2000),
    published_iso: meta.published_iso,
    time_label: meta.time_label,
    is_pinned: meta.is_pinned,
    content_id: postCid || liveCid,
    image_urls: imageUrls,
    video_url: videoUrl,
    replay_url: replayUrl,
    live_content_id: liveCid,
  }, _bnAnchorTop(el));
}
const pairRoots = Array.from(document.querySelectorAll('.trading-pairs, [class*="trading-pairs"]'));
pairRoots.sort((a, b) => _bnAnchorTop(a) - _bnAnchorTop(b));
for (const pairs of pairRoots) {
  const contentId = _bnContentIdFromCard(pairs) || '';
  if (!contentId) continue;
  const finalHref = _bnSquarePostHrefFromContentId(contentId);
  if (!finalHref) continue;
  const card = _bnFindCardRoot(pairs);
  const titleEl = card && card.querySelector('[class*="text-PrimaryText"], [class*="font-medium"]');
  let title = norm((titleEl && titleEl.innerText) || '');
  if (title.length > 120) title = title.slice(0, 120);
  const clean = norm((card && card.innerText) || title);
  const meta = _bnPostTimeFromCard(pairs);
  const imageUrls = _bnCollectArticleImagesRelaxed(pairs);
  const videoUrl = _bnCollectVideoUrlFromCard(pairs);
  const live = _bnCollectLiveReplayFromCard(pairs);
  _bnUpsertPost(byKey, {
    href: finalHref,
    title: title || (videoUrl ? '视频帖' : contentId),
    author_slug: authorSlug,
    raw: clean.slice(0, 2000),
    published_iso: meta.published_iso,
    time_label: meta.time_label,
    is_pinned: meta.is_pinned,
    content_id: contentId,
    image_urls: imageUrls,
    video_url: videoUrl,
    replay_url: live.replay_url || '',
    live_content_id: live.live_content_id || '',
  }, _bnAnchorTop(pairs));
}
const out = Array.from(byKey.values())
  .sort((a, b) => a.top - b.top)
  .map((x) => x.item);
return out.slice(0, Math.max(1, maxItems));
"""
)

DETAIL_MEDIA_EXTRACT_JS = (
    _MEDIA_HELPERS_JS
    + r"""
function _bnDetailArticleImages() {
  const roots = [];
  const m = document.querySelector('main');
  if (m) roots.push(m);
  document.querySelectorAll('[class*="article"], [class*="Article"], [class*="detail"], [class*="content"]').forEach((el) => {
    if (roots.length < 8) roots.push(el);
  });
  if (!roots.length) roots.push(document.body);
  const urls = [];
  const seen = new Set();
  for (const root of roots) {
    root.querySelectorAll('img[src]').forEach((im) => {
      let src = im.currentSrc || im.src
        || (im.getAttribute && (im.getAttribute('src') || im.getAttribute('data-src'))) || '';
      if (_bnNoiseImgUrl(src)) return;
      if (_bnInAvatarOrHeader(im)) return;
      const iw = im.naturalWidth || 0, ih = im.naturalHeight || 0;
      const ir = im.getBoundingClientRect();
      if (iw > 0 && ih > 0) {
        if (iw < 64 || ih < 64) return;
      } else if (ir.width < 56 || ir.height < 56) return;
      if (src && !seen.has(src)) {
        seen.add(src);
        urls.push(src);
      }
    });
  }
  return urls.slice(0, 20);
}
function _bnDetailVideoUrl() {
  const roots = [];
  const m = document.querySelector('main');
  if (m) roots.push(m);
  document.querySelectorAll('[class*="article"], [class*="Article"], [class*="detail"], [class*="content"]').forEach((el) => {
    if (roots.length < 8) roots.push(el);
  });
  if (!roots.length) roots.push(document.body);
  for (const root of roots) {
    for (const el of root.querySelectorAll('video, source')) {
      const src = (el.currentSrc || el.src
        || (el.getAttribute && (el.getAttribute('src') || el.getAttribute('data-src'))) || '').trim();
      if (!src) continue;
      const s = src.toLowerCase();
      if (s.startsWith('blob:') || s.startsWith('data:')) continue;
      if (s.includes('avatar') || s.includes('emoji') || s.includes('icon')) continue;
      return src;
    }
  }
  return '';
}
return { image_urls: _bnDetailArticleImages(), video_url: _bnDetailVideoUrl() };
"""
)
