# coding=utf-8
"""小红书 — CDP 抓取探索流卡片。"""

from __future__ import annotations

from typing import List

from allnews_mornitor import cdp_browser, store
from allnews_mornitor.models import Post
from allnews_mornitor.platforms import BasePlatform, register
from allnews_mornitor.platforms.extract_utils import GENERIC_CARD_EXTRACT, parse_cards

EXTRACT_JS = (
    GENERIC_CARD_EXTRACT
    + r"""
const out = [];
const cards = document.querySelectorAll("section.note-item, div[class*='note-item'], a.cover, a[href*='/explore/'], a[href*='/search_result/']");
const seen = new Set();
const push = (title, url, likes, comments, collects, author, summary) => {
  url = abs(url);
  if (!url || seen.has(url)) return;
  seen.add(url);
  out.push({title: (title||'').trim(), url, author: author||'', summary: summary||'', likes, comments, collects, shares:0, views:0});
};
document.querySelectorAll("a[href*='/explore/'], a[href*='/search_result/']").forEach((a) => {
  const href = a.getAttribute('href') || '';
  if (!href.includes('/explore/') && !href.includes('/search_result/')) return;
  const root = a.closest("section, div") || a;
  const titleEl = root.querySelector(".title, .footer .title, span");
  const title = (titleEl && titleEl.innerText) || a.getAttribute('title') || a.innerText || '';
  let likes = 0, comments = 0, collects = 0;
  root.querySelectorAll("span, div").forEach((n) => {
    const t = (n.innerText || '').trim();
    if (/赞|like/i.test(t) || n.className.toString().includes('like')) likes = Math.max(likes, num(t));
    if (/评|comment/i.test(t)) comments = Math.max(comments, num(t));
    if (/藏|collect/i.test(t)) collects = Math.max(collects, num(t));
  });
  // 小红书常见：右下角只有点赞数
  const countEl = root.querySelector(".count, .like-wrapper .count, span.count");
  if (countEl) likes = Math.max(likes, num(countEl.innerText));
  push(title.slice(0, 200), href, likes, comments, collects, '', title.slice(0, 200));
});
return out.slice(0, 60);
"""
)


@register
class XiaohongshuPlatform(BasePlatform):
    id = "xiaohongshu"
    name = "小红书"

    def fetch(self, driver=None) -> List[Post]:
        cfg = store.load_config().get("cdp") or {}
        wait_ms = int(cfg.get("wait_ms") or 2500)
        rounds = int(cfg.get("scroll_rounds") or 8)
        step = int(cfg.get("scroll_step") or 900)
        posts: List[Post] = []
        with cdp_browser.borrow_driver(driver) as drv:
            for url in self.entry_urls():
                cdp_browser.navigate(drv, url)
                cdp_browser.jitter_sleep(wait_ms + 1000)
                cdp_browser.scroll_page(drv, rounds=rounds, step=step, wait_ms=wait_ms)
                raw = cdp_browser.exec_js(drv, EXTRACT_JS)
                posts.extend(parse_cards(raw, self.id))
        seen, uniq = set(), []
        for p in posts:
            if p.post_id in seen:
                continue
            seen.add(p.post_id)
            uniq.append(p)
        return uniq
