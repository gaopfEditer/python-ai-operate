# coding=utf-8
"""CDP 抓取 X List 时间线推文（含时间、正文、图片）。"""

from __future__ import annotations

import re
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from signals.store import media_root, parse_dt, parse_list_id
from signals.tweet_log import fmt_tweet_line

ProgressCb = Optional[Callable[[str], None]]

# 专用静默标签标记（用于复用 / 清理，避免每次 createTarget 堆 tab）
_SIGNALS_TAB_MARKER = "trendradar-signals"
_SIGNALS_TAB_BLANK = f"about:blank#{_SIGNALS_TAB_MARKER}"

_SESSION_LOCK = threading.RLock()
_SESSION: Optional[Dict[str, Any]] = None  # client, page, target_id

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
    """有 progress 时交给控制台统一打印，避免重复。"""
    if cb:
        try:
            cb(msg)
            return
        except Exception:
            pass
    print(f"[signals] {msg}", flush=True)


def _debugger_host() -> str:
    try:
        from utils.crawl_cdp import resolve_crawl_debugger_url

        return resolve_crawl_debugger_url()
    except Exception:
        return "127.0.0.1:9223"


def _patch_debugger_host(host: str):
    """临时覆盖 allnews debugger 地址。"""
    try:
        import allnews_mornitor.cdp_browser as cdp_mod

        orig = cdp_mod.get_debugger_url

        def _patched() -> str:
            return host

        cdp_mod.get_debugger_url = _patched  # type: ignore
        return orig
    except Exception:
        return None


def _list_signal_tabs() -> List[Dict[str, Any]]:
    from allnews_mornitor.cdp_browser import _http_json

    try:
        pages = _http_json("/json/list")
    except Exception:
        return []
    if not isinstance(pages, list):
        return []
    out: List[Dict[str, Any]] = []
    for p in pages:
        if not isinstance(p, dict) or p.get("type") != "page":
            continue
        url = str(p.get("url") or "")
        if _SIGNALS_TAB_MARKER in url or "/i/lists/" in url:
            out.append(p)
    return out


def _close_session(*, log: ProgressCb = None) -> None:
    global _SESSION
    with _SESSION_LOCK:
        sess = _SESSION
        _SESSION = None
    if not sess:
        return
    page = sess.get("page")
    client = sess.get("client")
    if page is not None:
        try:
            page.close()
        except Exception:
            pass
    if client is not None:
        try:
            client.close()
        except Exception:
            pass
    if log:
        _log(log, "CDP 列表抓取标签已关闭")


def _session_alive(sess: Dict[str, Any]) -> bool:
    client = sess.get("client")
    page = sess.get("page")
    if client is None or page is None:
        return False
    if getattr(client, "_closed", False):
        return False
    try:
        page.eval_js("1+1")
        return True
    except Exception:
        return False


def _acquire_list_page(list_url: str, *, progress: ProgressCb = None) -> Tuple[Any, Any]:
    """
    复用单个后台标签抓取列表，避免周期任务每次 Target.createTarget 新开 tab。
    """
    from allnews_mornitor.cdp_browser import BackgroundTarget, _CdpClient, _browser_ws_url, _http_json

    global _SESSION

    with _SESSION_LOCK:
        if _SESSION and _session_alive(_SESSION):
            page = _SESSION["page"]
            _log(progress, f"CDP 复用列表标签 → {list_url}")
            page.silent_navigate(list_url)
            return _SESSION["client"], page

        _close_session()

        try:
            _http_json("/json/version")
        except Exception as e:
            raise RuntimeError(
                f"无法连接 Chrome CDP，请先 --remote-debugging-port=9223: {e}"
            ) from e

        client = _CdpClient(_browser_ws_url())
        page = None
        marked = [p for p in _list_signal_tabs() if _SIGNALS_TAB_MARKER in str(p.get("url") or "")]

        # 清理历史遗留的多个标记 tab，只保留一个
        for extra in marked[1:]:
            BackgroundTarget.close_target_id(client, str(extra.get("id") or ""))

        if marked:
            tid = str(marked[0].get("id") or "")
            try:
                page = BackgroundTarget.attach(client, tid)
                _log(progress, "CDP 附着已有列表抓取标签（未新建 tab）")
            except Exception:
                BackgroundTarget.close_target_id(client, tid)
                page = None

        if page is None:
            page = BackgroundTarget.create(client, _SIGNALS_TAB_BLANK)
            _log(progress, "CDP 建立列表抓取专用标签（后台，仅此一个）")

        _SESSION = {
            "client": client,
            "page": page,
            "target_id": page.target_id,
        }
        page.silent_navigate(list_url)
        return client, page


def close_list_crawl_tab(*, log: ProgressCb = None) -> None:
    """手动关闭列表抓取专用标签（一般不必调用，周期任务会自动复用）。"""
    _close_session(log=log)


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
    should_abort: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """
    静默 CDP 打开列表页，滚动直到推文时间早于 since 或达到上限。
    should_abort: 返回 True 时提前结束滚动。
    """
    from allnews_mornitor.cdp_browser import _http_json

    lid = parse_list_id(list_id) or str(list_id or "").strip()
    if not lid:
        return {"success": False, "error": "缺少 list_id", "items": []}
    url = f"https://x.com/i/lists/{lid}"
    max_tweets = max(1, min(int(max_tweets or 40), 120))
    max_scroll = max(3, min(int(max_scroll or 18), 40))

    def _aborted() -> bool:
        try:
            return bool(should_abort and should_abort())
        except Exception:
            return False

    host = _debugger_host()
    _orig = _patch_debugger_host(host)

    page = None
    try:
        try:
            _http_json("/json/version")
        except Exception as e:
            return {
                "success": False,
                "error": f"无法连接 Chrome CDP（{host}），请先 --remote-debugging-port=9223: {e}",
                "items": [],
            }

        _, page = _acquire_list_page(url, progress=progress)
        time.sleep(2.5)

        by_id: Dict[str, Dict[str, Any]] = {}
        seen_log: set = set()
        page_seen = 0
        page_kept = 0
        page_old = 0
        reached_old = False
        for round_i in range(max_scroll):
            if _aborted():
                _log(progress, "抓取已终止（滚动中）")
                break
            try:
                raw = page.eval_js(LIST_FEED_JS) or []
            except Exception as e:
                _log(progress, f"抽取失败 round={round_i}: {e}")
                raw = []
            if not isinstance(raw, list):
                raw = []
            oldest_in_batch = None
            new_in_round = 0
            for it in raw:
                if not isinstance(it, dict):
                    continue
                tid = str(it.get("tweet_id") or "").strip()
                if not tid:
                    continue
                created = parse_dt(str(it.get("created_at") or ""))
                if created is not None and created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                since_cmp = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
                too_old = bool(created and created < since_cmp)
                if created:
                    if oldest_in_batch is None or created < oldest_in_batch:
                        oldest_in_batch = created
                    if too_old:
                        reached_old = True

                if tid not in seen_log:
                    seen_log.add(tid)
                    page_seen += 1
                    new_in_round += 1
                    if too_old:
                        page_old += 1
                        _log(
                            progress,
                            f"[页面] #{page_seen} 过旧跳过 · {fmt_tweet_line(it)}",
                        )
                    else:
                        page_kept += 1
                        _log(
                            progress,
                            f"[页面] #{page_seen} 纳入候选 · {fmt_tweet_line(it)}",
                        )

                if too_old:
                    continue
                if tid not in by_id:
                    by_id[tid] = it
            _log(
                progress,
                f"滚动 {round_i + 1}/{max_scroll} · 窗口内累计 {len(by_id)} · 页面见过 {page_seen}"
                f"（新 {new_in_round}）"
                + (f" · 本批最旧 {oldest_in_batch.isoformat()}" if oldest_in_batch else ""),
            )
            if len(by_id) >= max_tweets:
                break
            if reached_old and len(by_id) >= 3:
                break
            # 全是过旧且已滚几屏：停止
            if reached_old and len(by_id) == 0 and round_i >= 2:
                _log(progress, "页面可见帖均早于时间窗，停止继续滚动")
                break
            try:
                page.eval_js("window.scrollBy(0, 1400); return true;")
            except Exception:
                break
            time.sleep(1.15)
            if _aborted():
                _log(progress, "抓取已终止（滚动中）")
                break

        items = list(by_id.values())

        def _key(x: Dict[str, Any]):
            dt = parse_dt(str(x.get("created_at") or ""))
            return dt or datetime(1970, 1, 1, tzinfo=timezone.utc)

        items.sort(key=_key, reverse=True)
        items = items[:max_tweets]
        _log(
            progress,
            f"抓取结束：窗口内 {len(items)} 条 · 页面见过 {page_seen}（过旧 {page_old}）",
        )
        return {
            "success": True,
            "list_id": lid,
            "url": url,
            "items": items,
            "count": len(items),
            "page_seen": page_seen,
            "page_old": page_old,
        }
    except Exception as e:
        _close_session()
        return {"success": False, "error": str(e), "items": []}
    finally:
        if _orig is not None:
            try:
                import allnews_mornitor.cdp_browser as cdp_mod

                cdp_mod.get_debugger_url = _orig  # type: ignore
            except Exception:
                pass
        # 保留 _SESSION 供下次周期抓取复用，不 detach / 不 close tab
