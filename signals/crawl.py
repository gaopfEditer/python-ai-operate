# coding=utf-8
"""CDP 抓取 X List 时间线推文（含时间、正文、图片）。"""

from __future__ import annotations

import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from signals.store import media_root, parse_dt, parse_list_id

ProgressCb = Optional[Callable[[str], None]]

LIST_FEED_JS = r"""
function abs(u){
  try { return new URL(u, location.origin).href.split('?')[0]; } catch(e){ return (u||''); }
}
const out = [];
const arts = [...document.querySelectorAll("article[data-testid='tweet']")];
for (const a of arts) {
  const links = [...a.querySelectorAll("a[href*='/status/']")];
  let status = '';
  for (const l of links) {
    const h = (l.getAttribute('href') || '');
    if (/\/status\/\d+/.test(h) && !/\/(analytics|photo|video|media)\//.test(h)) {
      status = abs(h);
      break;
    }
  }
  if (!status) continue;
  const idm = status.match(/\/status\/(\d+)/);
  const tweet_id = idm ? idm[1] : '';
  const timeEl = a.querySelector('time');
  const created_at = timeEl ? (timeEl.getAttribute('datetime') || '') : '';
  const time_label = timeEl ? (timeEl.textContent || '').trim() : '';
  const text = [...a.querySelectorAll('[data-testid="tweetText"]')]
    .map(el => (el.innerText || '').trim())
    .filter(Boolean)
    .join('\n\n');
  let author = '';
  for (const s of a.querySelectorAll('a[role="link"] span')) {
    const t = (s.textContent || '').trim();
    if (t.startsWith('@')) { author = t; break; }
  }
  const images = [];
  const seenImg = new Set();
  for (const img of a.querySelectorAll('img')) {
    const src = img.getAttribute('src') || '';
    if (!src) continue;
    if (/profile_images|emoji|ext_tw_video_thumb|hashflag/i.test(src)) continue;
    if (!/twimg\.com|pbs\.|media/i.test(src)) continue;
    const url = abs(src.replace(/&name=\w+/, '&name=large').replace(/\?format=/, '?format='));
    const key = url.replace(/name=\w+/, 'name=large');
    if (seenImg.has(key)) continue;
    seenImg.add(key);
    images.push({
      url: key,
      alt: (img.getAttribute('alt') || '').slice(0, 300),
    });
  }
  out.push({
    tweet_id,
    url: status,
    author,
    text: (text || '').slice(0, 8000),
    created_at,
    time_label,
    images,
  });
}
return out;
"""


def _log(cb: ProgressCb, msg: str) -> None:
    print(f"[signals] {msg}")
    if cb:
        try:
            cb(msg)
        except Exception:
            pass


def _debugger_host() -> str:
    try:
        import yaml

        cfg_path = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        x = ((cfg.get("crawler") or {}).get("x_cdp") or {})
        host = str(x.get("debugger_url") or "").strip()
        if host:
            return host
    except Exception:
        pass
    try:
        from allnews_mornitor.cdp_browser import get_debugger_url

        return get_debugger_url()
    except Exception:
        return "127.0.0.1:9222"


def download_image(url: str, tweet_id: str, index: int) -> Dict[str, Any]:
    """下载配图到 output/signals/media/，失败则仅保留远端 URL。"""
    info: Dict[str, Any] = {"url": url, "local": "", "rel": "", "alt": ""}
    if not url:
        return info
    root = media_root()
    ext = ".jpg"
    m = re.search(r"format=(\w+)", url)
    if m:
        fmt = m.group(1).lower()
        ext = ".png" if fmt == "png" else ".webp" if fmt == "webp" else ".jpg"
    elif ".png" in url:
        ext = ".png"
    name = f"{tweet_id}_{index}{ext}"
    dest = root / name
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 TrendRadarSignals/1.0",
                "Referer": "https://x.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if data:
            dest.write_bytes(data)
            info["local"] = str(dest)
            info["rel"] = name
    except Exception as e:
        info["error"] = str(e)[:120]
    return info


def crawl_list_timeline(
    list_id: str,
    *,
    since: datetime,
    max_tweets: int = 40,
    max_scroll: int = 18,
    progress: ProgressCb = None,
) -> Dict[str, Any]:
    """
    静默 CDP 打开列表页，滚动直到推文时间早于 since 或达到上限。
    """
    from allnews_mornitor.cdp_browser import BackgroundTarget, _CdpClient, _browser_ws_url, _http_json

    lid = parse_list_id(list_id) or str(list_id or "").strip()
    if not lid:
        return {"success": False, "error": "缺少 list_id", "items": []}
    url = f"https://x.com/i/lists/{lid}"
    max_tweets = max(1, min(int(max_tweets or 40), 120))
    max_scroll = max(3, min(int(max_scroll or 18), 40))

    # 临时覆盖 allnews debugger（BackgroundTarget 用其 get_debugger_url）
    host = _debugger_host()
    _orig = None
    try:
        import allnews_mornitor.cdp_browser as cdp_mod

        _orig = cdp_mod.get_debugger_url

        def _patched() -> str:
            return host

        cdp_mod.get_debugger_url = _patched  # type: ignore
    except Exception:
        pass

    client = None
    page = None
    try:
        try:
            _http_json("/json/version")
        except Exception as e:
            return {
                "success": False,
                "error": f"无法连接 Chrome CDP（{host}），请先 --remote-debugging-port=9222: {e}",
                "items": [],
            }

        _log(progress, f"CDP 打开列表 {url}")
        client = _CdpClient(_browser_ws_url())
        page = BackgroundTarget.create(client, "about:blank")
        page.silent_navigate(url)
        time.sleep(3.2)

        by_id: Dict[str, Dict[str, Any]] = {}
        reached_old = False
        for round_i in range(max_scroll):
            try:
                raw = page.eval_js(LIST_FEED_JS) or []
            except Exception as e:
                _log(progress, f"抽取失败 round={round_i}: {e}")
                raw = []
            if not isinstance(raw, list):
                raw = []
            oldest_in_batch = None
            for it in raw:
                if not isinstance(it, dict):
                    continue
                tid = str(it.get("tweet_id") or "").strip()
                if not tid:
                    continue
                created = parse_dt(str(it.get("created_at") or ""))
                if created:
                    if oldest_in_batch is None or created < oldest_in_batch:
                        oldest_in_batch = created
                    if created < since:
                        reached_old = True
                        continue
                if tid not in by_id:
                    by_id[tid] = it
            _log(
                progress,
                f"滚动 {round_i + 1}/{max_scroll} · 累计 {len(by_id)} 条"
                + (f" · 最旧 {oldest_in_batch.isoformat()}" if oldest_in_batch else ""),
            )
            if len(by_id) >= max_tweets:
                break
            if reached_old and len(by_id) >= 3:
                break
            try:
                page.eval_js("window.scrollBy(0, 1400); return true;")
            except Exception:
                break
            time.sleep(1.15)

        items = list(by_id.values())

        def _key(x: Dict[str, Any]):
            dt = parse_dt(str(x.get("created_at") or ""))
            return dt or datetime(1970, 1, 1, tzinfo=timezone.utc)

        items.sort(key=_key, reverse=True)
        items = items[:max_tweets]
        return {
            "success": True,
            "list_id": lid,
            "url": url,
            "items": items,
            "count": len(items),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "items": []}
    finally:
        try:
            if page is not None:
                page.detach()
        except Exception:
            pass
        try:
            if client is not None:
                client.close()
        except Exception:
            pass
        if _orig is not None:
            try:
                import allnews_mornitor.cdp_browser as cdp_mod

                cdp_mod.get_debugger_url = _orig  # type: ignore
            except Exception:
                pass
