# coding=utf-8
"""从页面抽取帖子卡片的通用 JS（各站再覆盖选择器）。"""

# 返回 [{title,url,author,summary,likes,comments,collects,shares,views}]
GENERIC_CARD_EXTRACT = r"""
const abs = (href) => {
  try { return new URL(href, location.href).href; } catch(e) { return href || ''; }
};
const num = (s) => {
  if (s == null) return 0;
  s = String(s).trim().replace(/,/g, '');
  const m = s.match(/([\d.]+)\s*([万wW亿])?/);
  if (!m) return parseInt(s.replace(/[^\d]/g, ''), 10) || 0;
  let n = parseFloat(m[1]);
  const u = m[2] || '';
  if (u === '万' || u.toLowerCase() === 'w') n *= 10000;
  if (u === '亿') n *= 100000000;
  return Math.round(n);
};
"""


def parse_cards(raw_list, platform: str):
    from allnews_mornitor.models import Post

    posts = []
    if not isinstance(raw_list, list):
        return posts
    for it in raw_list:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or "").strip()
        url = str(it.get("url") or "").strip()
        if not title and not url:
            continue
        posts.append(
            Post(
                platform=platform,
                title=title or url,
                url=url,
                author=str(it.get("author") or ""),
                summary=str(it.get("summary") or ""),
                content=str(it.get("content") or it.get("summary") or ""),
                likes=int(it.get("likes") or 0),
                comments=int(it.get("comments") or 0),
                collects=int(it.get("collects") or 0),
                shares=int(it.get("shares") or 0),
                views=int(it.get("views") or 0),
                raw=it,
            )
        )
    return posts
