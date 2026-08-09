# coding=utf-8
"""
xgrowth.tools 爆款热榜 → CDP 打开原帖 → AI 四要素拆解入库。

全程 CDP 页面抓取，不走对方 HTTP API。
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from corpus.viral_deconstruct import deconstruct_viral_post

XGROWTH_VIRAL_URL = "https://xgrowth.tools/viral-tweets"

LIST_EXTRACT_JS = r"""
function parseNum(s){
  s=(s||'').toString().trim().replace(/,/g,'');
  const m=s.match(/^([\d.]+)\s*([KMB万])?/i);
  if(!m) return 0;
  let n=parseFloat(m[1]);
  const u=(m[2]||'').toUpperCase();
  if(u==='K') n*=1e3; if(u==='M') n*=1e6; if(u==='B') n*=1e9; if(u==='万') n*=1e4;
  return Math.round(n);
}
const out=[];
const seen=new Set();
for (const a of document.querySelectorAll('a.tweet-card')) {
  const href=(a.href||'').split('?')[0];
  if(!/\/status\//.test(href) || seen.has(href)) continue;
  seen.add(href);
  const col = a.closest('.viral-column');
  let colTitle = '';
  if (col) {
    const h = col.querySelector('h2,h3,.column-title,header,.viral-column-title');
    colTitle = ((h && h.innerText) || (col.getAttribute('data-title') || '') || '').trim();
    if (!colTitle) {
      const first = (col.innerText||'').split('\n').map(x=>x.trim()).filter(Boolean)[0] || '';
      colTitle = first.slice(0, 40);
    }
  }
  let bucket = 'unknown';
  if (/potential|潜力/i.test(colTitle)) bucket = 'potential';
  else if (/viral|爆款/i.test(colTitle)) bucket = 'viral';
  else if (/4h|0–4|0-4/.test(colTitle)) bucket = 'potential';
  else if (/24h|4–24|4-24/.test(colTitle)) bucket = 'viral';

  const text=(a.innerText||'').trim();
  const lines=text.split(/\n+/).map(x=>x.trim()).filter(Boolean);
  let velocity=0;
  for(let i=0;i<lines.length;i++){
    if(lines[i]==='/hour' || lines[i]==='/小时'){ velocity=parseNum(lines[i-1]); break; }
    const vm=lines[i].match(/^([\d.]+[KMB万]?)\s*\/\s*(hour|小时)/i);
    if(vm){ velocity=parseNum(vm[1]); break; }
  }
  const handle=(href.match(/x\.com\/([^/]+)/)||[])[1]||'';
  let bodyLines=[];
  const idx=lines.findIndex(l=>l==='/hour'||l==='/小时'||/\/hour|\/小时/.test(l));
  if(idx>=0) bodyLines=lines.slice(idx+1);
  else bodyLines=lines.slice(1);
  const metricNums=[];
  while(bodyLines.length && /^[\d.]+[KMB万]?$/.test(bodyLines[bodyLines.length-1])){
    metricNums.unshift(parseNum(bodyLines.pop()));
  }
  const preview=bodyLines.join('\n').trim();
  // metrics after body: views, replies, likes, reposts?, bookmarks?
  const views = metricNums[0] || 0;
  const replies = metricNums[1] || 0;
  const likes = metricNums[2] || 0;
  const reposts = metricNums[3] || 0;
  const bookmarks = metricNums[4] || 0;
  out.push({
    url: href,
    handle,
    author: lines[0] || handle,
    velocity_per_hour: velocity,
    views, replies, likes, reposts, bookmarks,
    preview: preview.slice(0, 500),
    bucket,
    column: colTitle.slice(0, 60),
  });
}
out.sort((a,b)=> (b.velocity_per_hour||0) - (a.velocity_per_hour||0));
return out;
"""

TWEET_EXTRACT_JS = r"""
function clean(t){ return (t||'').replace(/\s+/g,' ').trim(); }
const arts = [...document.querySelectorAll('article')];
let main = arts[0] || null;
// prefer article that contains status text and not "Relevant"
for (const a of arts) {
  const t = a.innerText || '';
  if (t.includes('Views') || t.includes('次查看') || /·/.test(t)) { main = a; break; }
}
const root = main || document.body;
const textBlocks = [...root.querySelectorAll('[data-testid="tweetText"]')]
  .map(el => (el.innerText||'').trim())
  .filter(Boolean);
let body = textBlocks.join('\n\n');
if (!body) {
  // fallback: take early lines, drop chrome UI
  const lines = (root.innerText||'').split('\n').map(x=>x.trim()).filter(Boolean);
  const skip = /^(Home|Explore|Notifications|Messages|Grok|Premium|Relevant|Show translation|Views|Repost|Quote|Share|Copy link)$/i;
  body = lines.filter(l => !skip.test(l) && !/^[\d,.]+[KMB]?$/.test(l)).slice(0, 40).join('\n');
}
const viewsEl = [...root.querySelectorAll('span,a')].find(el => /Views|次查看|浏览/.test(el.innerText||''));
const viewsText = viewsEl ? (viewsEl.innerText||'') : '';
return {
  url: location.href.split('?')[0],
  text: body.slice(0, 6000),
  views_label: clean(viewsText).slice(0, 80),
  article_count: arts.length,
};
"""


ProgressCb = Optional[Callable[[str], None]]


def _log(cb: ProgressCb, msg: str) -> None:
    print(f"[xgrowth] {msg}")
    if cb:
        try:
            cb(msg)
        except Exception:
            pass


def _status_id(url: str) -> str:
    m = re.search(r"/status/(\d+)", url or "")
    return m.group(1) if m else (url or "").rstrip("/").split("/")[-1]


def fetch_viral_list(
    page,
    *,
    wait_s: float = 5.0,
    include_potential: bool = True,
) -> List[Dict[str, Any]]:
    page.silent_navigate(XGROWTH_VIRAL_URL)
    time.sleep(max(2.0, wait_s))
    # 轻滚触发懒加载
    try:
        page.eval_js("window.scrollBy(0, 800); return true;")
        time.sleep(0.8)
        page.eval_js("window.scrollBy(0, 800); return true;")
        time.sleep(0.8)
    except Exception:
        pass
    raw = page.eval_js(LIST_EXTRACT_JS) or []
    if not isinstance(raw, list):
        return []
    items: List[Dict[str, Any]] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        if not include_potential and str(it.get("bucket") or "") == "potential":
            continue
        items.append(it)
    return items


def fetch_tweet_body(page, url: str, *, wait_s: float = 4.5) -> Dict[str, Any]:
    page.silent_navigate(url)
    deadline = time.time() + max(3.0, wait_s)
    last: Dict[str, Any] = {}
    while time.time() < deadline:
        try:
            last = page.eval_js(TWEET_EXTRACT_JS) or {}
            if isinstance(last, dict) and (last.get("text") or "").strip():
                # SPA 有时先出壳
                if len(str(last.get("text") or "")) > 8:
                    break
        except Exception:
            pass
        time.sleep(0.35)
    return last if isinstance(last, dict) else {}


def run_xgrowth_viral_pipeline(
    *,
    limit: int = 8,
    include_potential: bool = True,
    open_tweet: bool = True,
    min_velocity: int = 0,
    progress: ProgressCb = None,
) -> Dict[str, Any]:
    """
    CDP：热榜 →（可选）打开原帖 → AI 拆解入库。
    """
    from allnews_mornitor.cdp_browser import BackgroundTarget, _CdpClient, _browser_ws_url, _http_json

    limit = max(1, min(int(limit or 8), 30))
    min_velocity = max(0, int(min_velocity or 0))
    started = datetime.now().isoformat(timespec="seconds")

    try:
        _http_json("/json/version")
    except Exception as e:
        return {
            "success": False,
            "error": f"无法连接 Chrome CDP，请先用 --remote-debugging-port=9222 启动: {e}",
        }

    client = None
    page = None
    ok = 0
    fail = 0
    items: List[Dict[str, Any]] = []
    errors: List[str] = []
    ranked: List[Dict[str, Any]] = []

    try:
        _log(progress, "连接 CDP，打开 xgrowth 热榜…")
        client = _CdpClient(_browser_ws_url())
        page = BackgroundTarget.create(client, "about:blank")
        ranked = fetch_viral_list(page, include_potential=include_potential)
        if min_velocity:
            ranked = [x for x in ranked if int(x.get("velocity_per_hour") or 0) >= min_velocity]
        ranked = ranked[:limit]
        _log(progress, f"热榜解析到 {len(ranked)} 条（limit={limit}）")

        for i, card in enumerate(ranked, 1):
            url = str(card.get("url") or "")
            preview = str(card.get("preview") or "").strip()
            handle = str(card.get("handle") or "")
            velocity = int(card.get("velocity_per_hour") or 0)
            _log(progress, f"[{i}/{len(ranked)}] {handle} · {velocity}/h · 打开原帖分析…")

            raw_text = preview
            tweet_meta: Dict[str, Any] = {}
            if open_tweet and url:
                try:
                    tweet_meta = fetch_tweet_body(page, url)
                    full = str(tweet_meta.get("text") or "").strip()
                    # 列表页只有 [Image/video only] 时更依赖原帖
                    if full and (not preview or preview.startswith("[Image") or len(full) > len(preview)):
                        raw_text = full
                except Exception as e:
                    errors.append(f"{url}: 打开原帖失败 {e}")

            if not raw_text or raw_text.startswith("[Image"):
                # 仍尝试用 preview；纯图帖给占位说明
                if not raw_text or raw_text.startswith("[Image"):
                    raw_text = preview if preview and not preview.startswith("[Image") else (
                        f"（图文/视频帖，列表摘要为空）作者 @{handle}，流速 {velocity}/小时"
                    )

            title = (preview.split("\n")[0] if preview else "")[:120] or f"@{handle} 热帖"
            try:
                result = deconstruct_viral_post(
                    title=title,
                    raw_text=raw_text,
                    platform="x",
                    url=url,
                    source_key=f"xgrowth:{_status_id(url)}",
                    collect_meta={
                        "via": "xgrowth.tools/viral-tweets",
                        "fetched_at": datetime.now().isoformat(timespec="seconds"),
                        "author": card.get("author") or handle,
                        "handle": handle,
                        "bucket": card.get("bucket"),
                        "velocity_per_hour": velocity,
                        "views": card.get("views"),
                        "likes": card.get("likes"),
                        "replies": card.get("replies"),
                        "reposts": card.get("reposts"),
                        "bookmarks": card.get("bookmarks"),
                        "list_preview": preview[:300],
                        "tweet_views_label": tweet_meta.get("views_label"),
                    },
                )
                if result.get("success"):
                    ok += 1
                    tpl = result.get("template") or {}
                    items.append(
                        {
                            "id": tpl.get("id"),
                            "url": url,
                            "handle": handle,
                            "velocity_per_hour": velocity,
                            "domain": (result.get("factors") or {}).get("domain"),
                            "tags": (result.get("factors") or {}).get("tags"),
                            "reason_tags": (result.get("factors") or {}).get("reason_tags"),
                            "viral_reason": (result.get("factors") or {}).get("viral_reason"),
                            "provider": result.get("provider"),
                        }
                    )
                else:
                    fail += 1
                    errors.append(str(result.get("error") or "拆解失败"))
            except Exception as e:
                fail += 1
                errors.append(f"{url}: {e}")
                _log(progress, f"失败: {e}")

            time.sleep(0.6)

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "ok": ok,
            "fail": fail,
            "items": items,
            "errors": errors[:12],
            "ranked_count": len(ranked),
            "started_at": started,
        }
    finally:
        if page is not None:
            try:
                page.detach()
            except Exception:
                pass
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    _log(progress, f"完成：成功 {ok}，失败 {fail}")
    return {
        "success": True,
        "ok": ok,
        "fail": fail,
        "items": items,
        "errors": errors[:12],
        "ranked_count": len(ranked),
        "source": XGROWTH_VIRAL_URL,
        "started_at": started,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
