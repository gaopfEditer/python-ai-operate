/**
 * 多平台贴文上下文提取 + 评论框填入
 * 支持：X/Twitter、币安 Square、OKX、Bitget、Reddit
 */

function cleanText(s) {
  return (s || '').replace(/\s+/g, ' ').trim();
}

function cleanBlock(s) {
  return (s || '').replace(/\n{3,}/g, '\n\n').trim();
}

function getSelectionText() {
  const sel = window.getSelection && window.getSelection();
  return cleanText(sel ? sel.toString() : '');
}

function pickMeta(name) {
  const el =
    document.querySelector(`meta[property="${name}"]`) ||
    document.querySelector(`meta[name="${name}"]`);
  return cleanText(el?.getAttribute('content'));
}

function currentPlatform() {
  const kit = self.PlatformKit;
  if (!kit) return 'generic';
  return kit.detectPlatformFromLocation(location.href, location.hostname);
}

function extractTwitter() {
  const host = location.hostname;
  if (!host.includes('x.com') && !host.includes('twitter.com')) return null;
  const articles = [...document.querySelectorAll('article[data-testid="tweet"]')];
  const article = articles.find((a) => {
    const t = a.innerText || '';
    return t.length > 8 && !/^Relevant$/m.test(t);
  }) || articles[0];
  const textNodes = article
    ? [...article.querySelectorAll('[data-testid="tweetText"]')].map((n) => cleanBlock(n.innerText))
    : [];
  const body = textNodes.join('\n\n') || cleanBlock(article?.innerText || '');
  const author =
    cleanText(article?.querySelector('[data-testid="User-Name"] span')?.textContent) ||
    cleanText(article?.querySelector('a[role="link"] span')?.textContent) ||
    '';
  const handle = cleanText(
    [...(article?.querySelectorAll('a[href*="/"]') || [])]
      .map((a) => a.getAttribute('href') || '')
      .find((h) => /^\/[^/]+$/.test(h) && !h.includes('/status'))
  ).replace(/^\//, '@');
  return {
    site: 'twitter',
    title: cleanText(document.title),
    author: author || handle,
    body: body.slice(0, 2800),
    subreddit: '',
  };
}

function extractBinance() {
  const host = location.hostname;
  if (!host.includes('binance.com')) return null;
  const title =
    cleanText(document.querySelector('h1')?.textContent) ||
    pickMeta('og:title') ||
    cleanText(document.title);
  const author =
    cleanText(document.querySelector('[class*="author"]')?.textContent) ||
    cleanText(document.querySelector('a[href*="/square/profile/"]')?.textContent) ||
    cleanText(document.querySelector('[class*="nickname"]')?.textContent) ||
    '';
  const body =
    cleanBlock(document.querySelector('[class*="post-content"]')?.innerText) ||
    cleanBlock(document.querySelector('[class*="PostContent"]')?.innerText) ||
    cleanBlock(document.querySelector('article')?.innerText) ||
    cleanBlock(document.querySelector('main')?.innerText) ||
    pickMeta('og:description');
  return {
    site: 'binance',
    title,
    author,
    body: body.slice(0, 2800),
    subreddit: '',
  };
}

function extractOkx() {
  const host = location.hostname;
  if (!host.includes('okx.com')) return null;
  const title =
    cleanText(document.querySelector('h1')?.textContent) ||
    pickMeta('og:title') ||
    cleanText(document.title);
  const author =
    cleanText(document.querySelector('[class*="author"]')?.textContent) ||
    cleanText(document.querySelector('[class*="user-name"]')?.textContent) ||
    cleanText(document.querySelector('[class*="nickname"]')?.textContent) ||
    '';
  const body =
    cleanBlock(document.querySelector('[class*="article-content"]')?.innerText) ||
    cleanBlock(document.querySelector('[class*="post-content"]')?.innerText) ||
    cleanBlock(document.querySelector('article')?.innerText) ||
    cleanBlock(document.querySelector('main')?.innerText) ||
    pickMeta('og:description');
  return {
    site: 'okx',
    title,
    author,
    body: body.slice(0, 2800),
    subreddit: '',
  };
}

function extractBitget() {
  const host = location.hostname;
  if (!host.includes('bitget.com')) return null;
  const title =
    cleanText(document.querySelector('h1')?.textContent) ||
    pickMeta('og:title') ||
    cleanText(document.title);
  const author =
    cleanText(document.querySelector('[class*="author"]')?.textContent) ||
    cleanText(document.querySelector('[class*="user-name"]')?.textContent) ||
    cleanText(document.querySelector('[class*="nickname"]')?.textContent) ||
    '';
  const body =
    cleanBlock(document.querySelector('[class*="article-content"]')?.innerText) ||
    cleanBlock(document.querySelector('[class*="post-content"]')?.innerText) ||
    cleanBlock(document.querySelector('article')?.innerText) ||
    cleanBlock(document.querySelector('main')?.innerText) ||
    pickMeta('og:description');
  return {
    site: 'bitget',
    title,
    author,
    body: body.slice(0, 2800),
    subreddit: '',
  };
}

function extractReddit() {
  const host = location.hostname;
  if (!host.includes('reddit.com')) return null;
  const subMatch = location.pathname.match(/\/r\/([^/]+)/i);
  const subreddit = subMatch ? subMatch[1] : '';
  const title =
    cleanText(document.querySelector('h1')?.textContent) ||
    cleanText(document.querySelector('[slot="title"]')?.textContent) ||
    cleanText(document.querySelector('shreddit-post')?.getAttribute('post-title')) ||
    pickMeta('og:title') ||
    cleanText(document.title);
  const body =
    cleanBlock(document.querySelector('[data-test-id="post-content"]')?.innerText) ||
    cleanBlock(document.querySelector('div[slot="text-body"]')?.innerText) ||
    cleanBlock(document.querySelector('.md')?.innerText) ||
    cleanBlock(document.querySelector('article')?.innerText) ||
    pickMeta('og:description');
  const author =
    cleanText(document.querySelector('a[href*="/user/"]')?.textContent) ||
    cleanText(document.querySelector('[data-testid="post_author_link"]')?.textContent) ||
    '';
  return {
    site: 'reddit',
    title,
    author,
    body: body.slice(0, 2800),
    subreddit,
  };
}

function extractYoutube() {
  if (!location.hostname.includes('youtube.com')) return null;
  const title =
    cleanText(document.querySelector('h1.ytd-watch-metadata yt-formatted-string')?.textContent) ||
    cleanText(document.querySelector('h1.title')?.textContent) ||
    cleanText(document.title);
  const author = cleanText(
    document.querySelector('#channel-name a')?.textContent ||
      document.querySelector('ytd-channel-name a')?.textContent
  );
  const desc =
    cleanText(document.querySelector('#description-inline-expander')?.innerText) ||
    cleanText(document.querySelector('#description')?.innerText) ||
    pickMeta('og:description');
  return { site: 'youtube', title, author, body: desc.slice(0, 2500), subreddit: '' };
}

function extractBilibili() {
  if (!location.hostname.includes('bilibili.com')) return null;
  const title =
    cleanText(document.querySelector('h1.video-title')?.textContent) ||
    cleanText(document.querySelector('.video-info-title')?.textContent) ||
    cleanText(document.title);
  const author = cleanText(
    document.querySelector('.up-name')?.textContent ||
      document.querySelector('.username')?.textContent
  );
  const desc =
    cleanText(document.querySelector('.desc-info-text')?.innerText) ||
    cleanText(document.querySelector('#v_desc')?.innerText) ||
    pickMeta('description');
  return { site: 'bilibili', title, author, body: desc.slice(0, 2500), subreddit: '' };
}

function extractGeneric() {
  const title = pickMeta('og:title') || cleanText(document.title);
  const body =
    pickMeta('og:description') ||
    pickMeta('description') ||
    cleanText(document.querySelector('article')?.innerText) ||
    cleanText(document.querySelector('main')?.innerText).slice(0, 2500);
  return {
    site: currentPlatform() === 'generic' ? 'generic' : currentPlatform(),
    title,
    author: '',
    body: body.slice(0, 2500),
    subreddit: '',
  };
}

function extractContext() {
  const selection = getSelectionText();
  const platform = currentPlatform();
  const specialized =
    extractTwitter() ||
    extractReddit() ||
    extractBinance() ||
    extractOkx() ||
    extractBitget() ||
    extractYoutube() ||
    extractBilibili() ||
    extractGeneric();
  const meta = self.PlatformKit?.getPlatformMeta(specialized.site || platform);
  return {
    ok: true,
    url: location.href,
    selection,
    title: specialized.title || '',
    author: specialized.author || '',
    body: specialized.body || '',
    site: specialized.site || platform,
    platform: specialized.site || platform,
    subreddit: specialized.subreddit || '',
    platformName: meta?.name || specialized.site || '通用',
    maxLen: meta?.maxLen || 500,
    platformHint: meta?.hint || '',
  };
}

function setNativeValue(el, value) {
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
  if (setter) setter.call(el, value);
  else el.value = value;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}

function isVisible(el) {
  if (!(el instanceof HTMLElement)) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 4 || r.height < 4) return false;
  const st = getComputedStyle(el);
  if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) < 0.05) return false;
  return true;
}

function isSearchLike(el) {
  const ph = (el.getAttribute('placeholder') || '').toLowerCase();
  const aria = (el.getAttribute('aria-label') || '').toLowerCase();
  const name = (el.getAttribute('name') || '').toLowerCase();
  const combined = `${ph} ${aria} ${name}`;
  return /search|搜索|query|查找/.test(combined);
}

function findCommentBox() {
  const platform = currentPlatform();
  const kit = self.PlatformKit;
  const selectors = kit ? kit.selectorsForPlatform(platform) : ['textarea', 'div[contenteditable="true"]'];
  for (const sel of selectors) {
    const nodes = document.querySelectorAll(sel);
    for (const el of nodes) {
      if (!isVisible(el)) continue;
      if (isSearchLike(el)) continue;
      // 优先聚焦/靠近视口的输入框
      if (document.activeElement === el || el.closest('[class*="comment"], [class*="Comment"], [class*="reply"], [class*="Reply"]')) {
        return el;
      }
    }
  }
  for (const sel of selectors) {
    const nodes = document.querySelectorAll(sel);
    for (const el of nodes) {
      if (!isVisible(el)) continue;
      if (isSearchLike(el)) continue;
      return el;
    }
  }
  return null;
}

async function insertComment(text) {
  const el = findCommentBox();
  if (!el) {
    try {
      await navigator.clipboard.writeText(text);
      return { ok: true, method: 'copied', platform: currentPlatform() };
    } catch (_) {
      return { ok: false, error: '未找到评论框，且复制失败', platform: currentPlatform() };
    }
  }

  el.focus();
  el.scrollIntoView({ block: 'nearest', behavior: 'instant' });
  if (el.isContentEditable || el.getAttribute('contenteditable') === 'true') {
    el.textContent = '';
    document.execCommand('selectAll', false, null);
    const ok = document.execCommand('insertText', false, text);
    if (!ok) {
      el.textContent = text;
      el.dispatchEvent(
        new InputEvent('input', { bubbles: true, data: text, inputType: 'insertText' })
      );
    }
    return { ok: true, method: 'contenteditable', platform: currentPlatform() };
  }

  setNativeValue(el, text);
  return { ok: true, method: 'textarea', platform: currentPlatform() };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      if (msg.type === 'extractContext') {
        sendResponse(extractContext());
        return;
      }
      if (msg.type === 'insertComment') {
        sendResponse(await insertComment(String(msg.text || '')));
        return;
      }
      if (msg.type === 'getPlatform') {
        sendResponse({ ok: true, platform: currentPlatform() });
        return;
      }
      sendResponse({ ok: false, error: 'unknown' });
    } catch (e) {
      sendResponse({ ok: false, error: String(e?.message || e) });
    }
  })();
  return true;
});
