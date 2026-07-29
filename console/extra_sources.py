# coding=utf-8
"""
额外资讯源：Reddit 公开搜索 + 可选 Telegram（Telethon 会话）。
结果合并写入 output/trendradar_posts_state.json。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = PROJECT_ROOT / "output" / "trendradar_posts_state.json"

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# 官方 Reddit 常被墙/风控；Arctic Shift 需指定 subreddit
_DEFAULT_REDDIT_SUBS = [
    "technology",
    "programming",
    "MachineLearning",
    "artificial",
    "OpenAI",
    "LocalLLaMA",
    "webdev",
    "python",
    "javascript",
    "startups",
    "entrepreneur",
    "crypto",
    "investing",
    "news",
    "worldnews",
    "business",
]

_ARCTIC_SHIFT = "https://arctic-shift.photon-reddit.com/api/posts/search"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"version": 1, "generated_at": "", "platform_labels": {}, "posts": {}}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {"version": 1, "posts": {}, "platform_labels": {}}
    except Exception:
        return {"version": 1, "generated_at": "", "platform_labels": {}, "posts": {}}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["generated_at"] = datetime.now().isoformat(timespec="seconds")
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _resolve_proxies() -> Optional[Dict[str, str]]:
    """优先环境变量，其次 config.yaml crawler.default_proxy。"""
    for key in (
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "ALL_PROXY",
        "https_proxy",
        "http_proxy",
        "all_proxy",
    ):
        val = (os.environ.get(key) or "").strip()
        if val:
            return {"http": val, "https": val}
    try:
        import yaml

        cfg_path = PROJECT_ROOT / "config" / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            crawler = cfg.get("crawler") or {}
            proxy = str(crawler.get("default_proxy") or "").strip()
            # Reddit 在国内常需代理：即使 use_proxy=false，只要配了 default_proxy 也尝试
            if proxy:
                return {"http": proxy, "https": proxy}
    except Exception:
        pass
    return None


def _merge_items(platform_id: str, platform_name: str, items: List[Dict[str, Any]]) -> int:
    if not items:
        return 0
    state = _load_state()
    posts = state.setdefault("posts", {})
    labels = state.setdefault("platform_labels", {})
    labels[platform_id] = platform_name
    bucket = posts.setdefault(platform_id, {})
    added = 0
    fetched = _now()
    for it in items:
        href = str(it.get("href") or it.get("url") or "").strip()
        title = str(it.get("title") or "").strip()
        if not href and not title:
            continue
        key = href or f"__title__:{hash(title) & 0xFFFFFFFF}"
        prev = bucket.get(key) if isinstance(bucket.get(key), dict) else {}
        raw = str(it.get("raw") or it.get("content") or title)
        summary = str(it.get("summary") or prev.get("summary") or "").strip()
        # 入库时不强制 AI 摘要，避免额外源拖慢；列表页会懒生成
        if not summary:
            cut = re.sub(r"\s+", " ", raw).strip()
            summary = (cut[:120] + ("…" if len(cut) > 120 else "")) if cut else ""
        entry = {
            "href": href,
            "title": title,
            "raw": raw,
            "content": str(it.get("content") or ""),
            "summary": summary,
            "author": str(it.get("author") or ""),
            "fetched_at": fetched,
            "first_fetched_at": prev.get("first_fetched_at") or fetched,
            "rank": it.get("rank"),
            "star": it.get("star", prev.get("star", 0)),
            "isUseful": bool(it.get("isUseful", prev.get("isUseful", False))),
            "source_query": str(it.get("source_query") or ""),
            "source": platform_name,
            "platform": platform_id,
            # 保留用户操作：归档 / 稍后观看 / 标签
            "archived": bool(prev.get("archived", False)),
            "watch_later": bool(prev.get("watch_later", False)),
            "tags": list(prev.get("tags") or []) if isinstance(prev.get("tags"), list) else [],
        }
        if prev.get("archived_at"):
            entry["archived_at"] = prev.get("archived_at")
        if prev.get("watch_later_at"):
            entry["watch_later_at"] = prev.get("watch_later_at")
        bucket[key] = entry
        added += 1
    _save_state(state)
    return added


def _parse_reddit_listing(data: Any, query: str, seen: set) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    children = (
        ((data.get("data") or {}).get("children") or [])
        if isinstance(data, dict)
        else []
    )
    for ch in children:
        d = ch.get("data") if isinstance(ch, dict) else None
        if not isinstance(d, dict):
            continue
        permalink = str(d.get("permalink") or "").strip()
        href = f"https://www.reddit.com{permalink}" if permalink else str(d.get("url") or "")
        if not href or href in seen:
            continue
        seen.add(href)
        title = str(d.get("title") or "").strip()
        selftext = str(d.get("selftext") or "").strip()
        subreddit = str(d.get("subreddit") or "").strip()
        results.append(
            {
                "href": href,
                "title": title,
                "raw": selftext or title,
                "content": selftext[:2000],
                "author": str(d.get("author") or ""),
                "source_query": query,
                "rank": d.get("score"),
                "subreddit": subreddit,
            }
        )
    return results


def _parse_pullpush(data: Any, query: str, seen: set) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return results
    for d in rows:
        if not isinstance(d, dict):
            continue
        permalink = str(d.get("permalink") or "").strip()
        fullname = str(d.get("id") or "").strip()
        if permalink:
            href = (
                permalink
                if permalink.startswith("http")
                else f"https://www.reddit.com{permalink}"
            )
        elif fullname:
            href = f"https://www.reddit.com/comments/{fullname}/"
        else:
            href = str(d.get("url") or "").strip()
        if not href or href in seen:
            continue
        seen.add(href)
        title = str(d.get("title") or "").strip()
        selftext = str(d.get("selftext") or "").strip()
        results.append(
            {
                "href": href,
                "title": title,
                "raw": selftext or title,
                "content": selftext[:2000],
                "author": str(d.get("author") or ""),
                "source_query": query,
                "rank": d.get("score"),
                "subreddit": str(d.get("subreddit") or ""),
            }
        )
    return results


def _http_get_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    proxies: Optional[Dict[str, str]] = None,
    timeout: int = 25,
) -> Tuple[Optional[Any], str]:
    headers = {
        "User-Agent": _BROWSER_UA,
        "Accept": "application/json,text/plain,*/*",
    }
    # 先试代理，再直连
    proxy_modes: List[Optional[Dict[str, str]]] = []
    if proxies:
        proxy_modes.append(proxies)
    proxy_modes.append(None)
    last_err = ""
    for px in proxy_modes:
        try:
            session = requests.Session()
            r = session.get(
                url,
                params=params,
                headers=headers,
                proxies=px,
                timeout=timeout,
            )
            if r.status_code >= 400:
                last_err = f"HTTP {r.status_code}"
                continue
            try:
                return r.json(), ""
            except Exception:
                text = (r.text or "").strip()
                if text.startswith("{") or text.startswith("["):
                    return json.loads(text), ""
                last_err = "响应非 JSON"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
    return None, last_err


def _parse_arctic_posts(data: Any, query: str, seen: set) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return results
    for d in rows:
        if not isinstance(d, dict):
            continue
        permalink = str(d.get("permalink") or "").strip()
        fullname = str(d.get("id") or "").strip()
        if permalink:
            href = (
                permalink
                if permalink.startswith("http")
                else f"https://www.reddit.com{permalink}"
            )
        elif fullname:
            href = f"https://www.reddit.com/comments/{fullname}/"
        else:
            continue
        if href in seen:
            continue
        seen.add(href)
        title = str(d.get("title") or "").strip()
        selftext = str(d.get("selftext") or "").strip()
        results.append(
            {
                "href": href,
                "title": title,
                "raw": selftext or title,
                "content": selftext[:2000],
                "author": str(d.get("author") or ""),
                "source_query": query,
                "rank": d.get("score"),
                "subreddit": str(d.get("subreddit") or ""),
            }
        )
    return results


def _subs_for_query(query: str) -> List[str]:
    """从查询里提取 r/xxx，并附带默认版块。"""
    found = re.findall(r"(?:^|[^\w])/r/([A-Za-z0-9_]+)", f" {query} ")
    found += re.findall(r"(?:^|\s)r/([A-Za-z0-9_]+)", query)
    ordered: List[str] = []
    seen = set()
    for s in list(found) + list(_DEFAULT_REDDIT_SUBS):
        key = s.strip()
        if not key:
            continue
        low = key.lower()
        if low in seen:
            continue
        seen.add(low)
        ordered.append(key)
    return ordered[:16]


def search_reddit(
    queries: List[str], limit_per_query: int = 15
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Reddit 搜索。官方常 403，失败时走 Arctic Shift 多版块兜底。"""
    proxies = _resolve_proxies()
    results: List[Dict[str, Any]] = []
    errors: List[str] = []
    seen = set()
    if proxies:
        print(f"[extra] Reddit 使用代理: {proxies.get('https') or proxies.get('http')}")
    else:
        print("[extra] Reddit 未检测到代理（建议设置 HTTPS_PROXY，例如 http://127.0.0.1:7890）")

    for q in queries:
        q = (q or "").strip()
        if not q:
            continue
        got = 0
        last_err = ""

        # 1) 官方 search.json（海外住宅 IP 才较稳）
        data, err = _http_get_json(
            "https://www.reddit.com/search.json",
            params={
                "q": q,
                "sort": "new",
                "limit": max(5, min(25, limit_per_query)),
                "raw_json": 1,
            },
            proxies=proxies,
        )
        if data is not None:
            batch = _parse_reddit_listing(data, q, seen)
            results.extend(batch)
            got += len(batch)
            if batch:
                print(f"[extra] Reddit 官方 q={q!r} +{len(batch)}")
        elif err:
            last_err = f"官方接口失败: {err}"

        # 2) PullPush
        if got < 3:
            data2, err2 = _http_get_json(
                "https://api.pullpush.io/reddit/search/submission/",
                params={"q": q, "size": max(5, min(25, limit_per_query))},
                proxies=proxies,
            )
            if data2 is not None:
                batch = _parse_pullpush(data2, q, seen)
                results.extend(batch)
                got += len(batch)
                if batch:
                    print(f"[extra] Reddit PullPush q={q!r} +{len(batch)}")
            elif err2:
                last_err = last_err or f"PullPush 失败: {err2}"

        # 3) Arctic Shift：按版块关键词搜索（当前最稳的免费兜底）
        if got < limit_per_query:
            per_sub = max(2, min(8, limit_per_query // 3 or 3))
            arctic_got = 0
            for sub in _subs_for_query(q):
                if got + arctic_got >= limit_per_query * 2:
                    break
                data3, err3 = _http_get_json(
                    _ARCTIC_SHIFT,
                    params={
                        "subreddit": sub,
                        "query": q,
                        "limit": per_sub,
                    },
                    proxies=proxies,
                    timeout=30,
                )
                if data3 is None:
                    if err3 and not last_err:
                        last_err = f"Arctic Shift 失败: {err3}"
                    continue
                batch = _parse_arctic_posts(data3, q, seen)
                if batch:
                    results.extend(batch)
                    arctic_got += len(batch)
            if arctic_got:
                got += arctic_got
                print(f"[extra] Reddit ArcticShift q={q!r} +{arctic_got}")
            elif got == 0 and not last_err:
                last_err = "Arctic Shift 多版块无命中"

        if got == 0:
            msg = (
                f"Reddit 搜索无结果 q={q!r}"
                + (f"（{last_err}）" if last_err else "")
                + "。常见原因：官方 Reddit 对当前代理 IP 返回 403；请确认代理可用后重试"
            )
            errors.append(msg)
            print(f"[extra] {msg}")
        else:
            print(f"[extra] Reddit q={q!r} 合计 +{got}")
    return results, errors


def search_telegram(
    queries: List[str], limit_per_query: int = 20
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    用已有 Telethon 会话做全局消息搜索（可选）。
    无会话或依赖缺失时返回空列表。
    """
    errors: List[str] = []
    session = PROJECT_ROOT / "messages" / "telegram_session.session"
    if not session.exists():
        msg = (
            "Telegram 跳过：未登录。请在项目根目录执行 "
            "`python messages/telegram_listener.py`，按提示输入手机号与验证码，"
            "生成 messages/telegram_session.session 后再抓取"
        )
        print(f"[extra] {msg}")
        return [], [msg]

    try:
        from messages.telegram_listener import API_ID, API_HASH
    except Exception as e:
        msg = f"Telegram 跳过：无法导入 API 配置: {e}"
        print(f"[extra] {msg}")
        return [], [msg]

    try:
        from telethon.sync import TelegramClient
    except Exception as e:
        msg = f"Telegram 跳过：未安装 telethon（pip install telethon）: {e}"
        print(f"[extra] {msg}")
        return [], [msg]

    results: List[Dict[str, Any]] = []
    seen = set()
    try:
        with TelegramClient(str(session), API_ID, API_HASH) as client:
            if not client.is_user_authorized():
                msg = "Telegram 跳过：会话未授权，请重新运行 messages/telegram_listener.py 登录"
                print(f"[extra] {msg}")
                return [], [msg]
            for q in queries:
                q = (q or "").strip()
                if not q:
                    continue
                try:
                    for msg in client.iter_messages(None, search=q, limit=limit_per_query):
                        text = (msg.message or "").strip()
                        if not text:
                            continue
                        chat = msg.chat
                        username = getattr(chat, "username", None) if chat else None
                        chat_id = getattr(chat, "id", None) if chat else None
                        chat_title = ""
                        if chat is not None:
                            chat_title = (
                                getattr(chat, "title", None)
                                or getattr(chat, "username", None)
                                or ""
                            )
                        if username:
                            href = f"https://t.me/{username}/{msg.id}"
                        elif chat_id is not None:
                            href = f"https://t.me/c/{str(chat_id).lstrip('-')}/{msg.id}"
                        else:
                            href = f"tg://message?id={msg.id}"
                        if href in seen:
                            continue
                        seen.add(href)
                        title = text.splitlines()[0][:120]
                        author = ""
                        try:
                            sender = msg.get_sender()
                            author = (
                                getattr(sender, "username", None)
                                or getattr(sender, "first_name", "")
                                or ""
                            )
                        except Exception:
                            pass
                        results.append(
                            {
                                "href": href,
                                "title": title,
                                "raw": text[:2000],
                                "content": text[:2000],
                                "author": str(author or ""),
                                "source_query": q,
                                "chat": str(chat_title or ""),
                            }
                        )
                except Exception as e:
                    err = f"Telegram 搜索失败 q={q!r}: {e}"
                    errors.append(err)
                    print(f"[extra] {err}")
    except Exception as e:
        err = f"Telegram 客户端失败: {e}"
        errors.append(err)
        print(f"[extra] {err}")
    return results, errors

def run_extra_searches(
    reddit_queries: Optional[List[str]] = None,
    telegram_queries: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """按平台执行额外搜索并写入缓存。"""
    plats = {str(p).strip().lower() for p in (platforms or ["reddit", "telegram"]) if str(p).strip()}
    summary: Dict[str, Any] = {
        "reddit": 0,
        "telegram": 0,
        "errors": [],
        "reddit_errors": [],
        "telegram_errors": [],
    }

    if "reddit" in plats and reddit_queries:
        items, errs = search_reddit(reddit_queries)
        summary["reddit"] = _merge_items("reddit", "Reddit", items)
        summary["reddit_errors"] = errs
        summary["errors"].extend(errs)
        print(f"[extra] Reddit 写入 {summary['reddit']} 条")

    if "telegram" in plats and telegram_queries:
        items, errs = search_telegram(telegram_queries)
        summary["telegram"] = _merge_items("telegram", "Telegram", items)
        summary["telegram_errors"] = errs
        summary["errors"].extend(errs)
        print(f"[extra] Telegram 写入 {summary['telegram']} 条")

    return summary
