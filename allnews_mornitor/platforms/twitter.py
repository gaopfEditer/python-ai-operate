# coding=utf-8
"""X / Twitter — CDP 抓取热门/高赞搜索。"""

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
const arts = document.querySelectorAll("article[data-testid='tweet']");
arts.forEach((article) => {
  let url = '', title = '', author = '';
  article.querySelectorAll("a[href*='/status/']").forEach((a) => {
    const href = a.getAttribute('href') || '';
    if (href.includes('/status/') && !url) url = abs(href);
  });
  const text = article.querySelector("[data-testid='tweetText']");
  title = (text && text.innerText || article.innerText || '').trim().slice(0, 280);
  const user = article.querySelector("a[role='link'] span");
  // 找 @handle
  article.querySelectorAll("a[role='link'] span").forEach((n) => {
    const t = (n.innerText || '').trim();
    if (t.startsWith('@')) author = t;
  });
  const like = article.querySelector("[data-testid='like']");
  const reply = article.querySelector("[data-testid='reply']");
  const rt = article.querySelector("[data-testid='retweet']");
  out.push({
    title,
    url,
    author,
    summary: title,
    likes: num(like && like.getAttribute('aria-label')),
    comments: num(reply && reply.getAttribute('aria-label')),
    shares: num(rt && rt.getAttribute('aria-label')),
    collects: 0,
    views: 0,
  });
});
return out;
"""
)


@register
class TwitterPlatform(BasePlatform):
    id = "twitter"
    name = "X / Twitter"

    def fetch(self) -> List[Post]:
        cfg = store.load_config().get("cdp") or {}
        wait_ms = int(cfg.get("wait_ms") or 2500)
        rounds = int(cfg.get("scroll_rounds") or 8)
        step = int(cfg.get("scroll_step") or 900)
        posts: List[Post] = []
        with cdp_browser.cdp_session() as driver:
            for url in self.entry_urls():
                cdp_browser.navigate_dedicated_tab(driver, url)
                cdp_browser.jitter_sleep(wait_ms)
                cdp_browser.scroll_page(driver, rounds=rounds, step=step, wait_ms=wait_ms)
                raw = cdp_browser.exec_js(driver, EXTRACT_JS)
                posts.extend(parse_cards(raw, self.id))
        # 去重
        seen = set()
        uniq = []
        for p in posts:
            if p.post_id in seen:
                continue
            seen.add(p.post_id)
            uniq.append(p)
        return uniq
