# coding=utf-8
"""36氪 — CDP 抓取首页/热榜。"""

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
document.querySelectorAll("a[href*='/p/'], a[href*='/newsflashes/']").forEach((a) => {
  const href = abs(a.getAttribute('href') || '');
  if (!href || seen.has(href) || !/36kr\.com/.test(href)) return;
  const title = (a.innerText || '').trim().split('\n')[0].slice(0, 200);
  if (!title || title.length < 6) return;
  const root = a.closest("div, article, li") || a;
  let likes = 0, comments = 0, views = 0;
  const t = root.innerText || '';
  const vm = t.match(/(\d+)\s*阅读|阅读\s*(\d+)/);
  if (vm) views = num(vm[1] || vm[2]);
  const cm = t.match(/(\d+)\s*评论/);
  if (cm) comments = num(cm[1]);
  const lm = t.match(/(\d+)\s*赞/);
  if (lm) likes = num(lm[1]);
  seen.add(href);
  out.push({title, url: href, author:'', summary:title, likes, comments, collects:0, shares:0, views});
});
return out.slice(0, 40);
"""
)


@register
class Kr36Platform(BasePlatform):
    id = "kr36"
    name = "36氪"

    def fetch(self, driver=None) -> List[Post]:
        cfg = store.load_config().get("cdp") or {}
        wait_ms = int(cfg.get("wait_ms") or 2500)
        posts: List[Post] = []
        with cdp_browser.borrow_driver(driver) as drv:
            for url in self.entry_urls():
                cdp_browser.navigate(drv, url)
                cdp_browser.jitter_sleep(wait_ms)
                cdp_browser.scroll_page(drv, rounds=5, step=900, wait_ms=wait_ms)
                raw = cdp_browser.exec_js(drv, EXTRACT_JS)
                posts.extend(parse_cards(raw, self.id))
        seen, uniq = set(), []
        for p in posts:
            if p.post_id in seen:
                continue
            seen.add(p.post_id)
            uniq.append(p)
        return uniq
