# coding=utf-8
"""虎嗅网 — CDP 抓取首页/24小时。"""

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
const seen = new Set();
document.querySelectorAll("a[href*='/article/'], a[href*='/moment/']").forEach((a) => {
  const href = abs(a.getAttribute('href') || '');
  if (!href || seen.has(href) || !/huxiu\.com/.test(href)) return;
  const title = (a.innerText || '').trim().split('\n')[0].slice(0, 200);
  if (!title || title.length < 6) return;
  const root = a.closest("div, article, li") || a;
  let likes = 0, comments = 0;
  const t = root.innerText || '';
  const cm = t.match(/(\d+)\s*评论/);
  if (cm) comments = num(cm[1]);
  const lm = t.match(/(\d+)\s*赞|赞\s*(\d+)/);
  if (lm) likes = num(lm[1] || lm[2]);
  seen.add(href);
  out.push({title, url: href, author:'', summary:title, likes, comments, collects:0, shares:0, views:0});
});
return out.slice(0, 40);
"""
)


@register
class HuxiuPlatform(BasePlatform):
    id = "huxiu"
    name = "虎嗅网"

    def fetch(self) -> List[Post]:
        cfg = store.load_config().get("cdp") or {}
        wait_ms = int(cfg.get("wait_ms") or 2500)
        posts: List[Post] = []
        with cdp_browser.cdp_session() as driver:
            for url in self.entry_urls():
                cdp_browser.navigate_dedicated_tab(driver, url)
                cdp_browser.jitter_sleep(wait_ms)
                cdp_browser.scroll_page(driver, rounds=5, step=900, wait_ms=wait_ms)
                raw = cdp_browser.exec_js(driver, EXTRACT_JS)
                posts.extend(parse_cards(raw, self.id))
        seen, uniq = set(), []
        for p in posts:
            if p.post_id in seen:
                continue
            seen.add(p.post_id)
            uniq.append(p)
        return uniq
