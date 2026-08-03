# coding=utf-8
"""少数派 — CDP + 公开接口兜底。"""

from __future__ import annotations

from typing import List

import requests

from allnews_mornitor import cdp_browser, store
from allnews_mornitor.models import Post
from allnews_mornitor.platforms import BasePlatform, register
from allnews_mornitor.platforms.extract_utils import GENERIC_CARD_EXTRACT, parse_cards

EXTRACT_JS = (
    GENERIC_CARD_EXTRACT
    + r"""
const out = [];
const seen = new Set();
document.querySelectorAll("a[href*='/post/']").forEach((a) => {
  const href = abs(a.getAttribute('href') || '');
  if (!href || seen.has(href) || !/sspai\.com\/post\//.test(href)) return;
  const root = a.closest("div, article, li") || a;
  const title = (a.innerText || '').trim().split('\n')[0].slice(0, 200);
  if (!title) return;
  let likes = 0, comments = 0, collects = 0;
  const t = root.innerText || '';
  const lm = t.match(/(\d+)\s*点赞|赞\s*(\d+)/);
  if (lm) likes = num(lm[1] || lm[2]);
  const cm = t.match(/(\d+)\s*评论/);
  if (cm) comments = num(cm[1]);
  seen.add(href);
  out.push({title, url: href, author:'', summary:title, likes, comments, collects, shares:0, views:0});
});
return out.slice(0, 40);
"""
)


def _api_fallback() -> List[Post]:
    posts: List[Post] = []
    try:
        r = requests.get(
            "https://sspai.com/api/v1/article/index/page/get",
            params={"limit": 40, "offset": 0, "created_at": 0},
            headers={"User-Agent": "AllNewsMonitor/1.0"},
            timeout=20,
        )
        data = r.json() if r.content else {}
        items = data.get("data") or []
        if isinstance(items, dict):
            items = items.get("data") or []
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                continue
            aid = it.get("id")
            title = str(it.get("title") or "").strip()
            if not aid or not title:
                continue
            posts.append(
                Post(
                    platform="sspai",
                    title=title,
                    url=f"https://sspai.com/post/{aid}",
                    author=str((it.get("author") or {}).get("nickname") or ""),
                    summary=str(it.get("summary") or ""),
                    likes=int(it.get("like_count") or it.get("likes") or 0),
                    comments=int(it.get("comment_count") or 0),
                    collects=int(it.get("favorite_count") or 0),
                    views=int(it.get("view_count") or 0),
                    raw=it,
                )
            )
    except Exception as e:
        print(f"[sspai] API 兜底失败: {e}")
    return posts


@register
class SspaiPlatform(BasePlatform):
    id = "sspai"
    name = "少数派"

    def fetch(self) -> List[Post]:
        cfg = store.load_config().get("cdp") or {}
        wait_ms = int(cfg.get("wait_ms") or 2500)
        posts: List[Post] = []
        try:
            with cdp_browser.cdp_session() as driver:
                for url in self.entry_urls():
                    cdp_browser.navigate_dedicated_tab(driver, url)
                    cdp_browser.jitter_sleep(wait_ms)
                    cdp_browser.scroll_page(driver, rounds=5, step=800, wait_ms=wait_ms)
                    raw = cdp_browser.exec_js(driver, EXTRACT_JS)
                    posts.extend(parse_cards(raw, self.id))
        except Exception as e:
            print(f"[sspai] CDP 失败，尝试 API: {e}")
        if len(posts) < 5:
            posts.extend(_api_fallback())
        seen, uniq = set(), []
        for p in posts:
            if p.post_id in seen:
                continue
            seen.add(p.post_id)
            uniq.append(p)
        return uniq
