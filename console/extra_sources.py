# coding=utf-8
"""
额外资讯源：Reddit 公开搜索 + 可选 Telegram（Telethon 会话）。
结果合并写入 output/trendradar_posts_state.json。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = PROJECT_ROOT / "output" / "trendradar_posts_state.json"


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
        entry = {
            "href": href,
            "title": title,
            "raw": str(it.get("raw") or it.get("content") or title),
            "content": str(it.get("content") or ""),
            "author": str(it.get("author") or ""),
            "fetched_at": fetched,
            "first_fetched_at": prev.get("first_fetched_at") or fetched,
            "rank": it.get("rank"),
            "star": it.get("star", prev.get("star", 0)),
            "isUseful": bool(it.get("isUseful", prev.get("isUseful", False))),
            "source_query": str(it.get("source_query") or ""),
        }
        bucket[key] = entry
        added += 1
    _save_state(state)
    return added


def search_reddit(queries: List[str], limit_per_query: int = 15) -> List[Dict[str, Any]]:
    """Reddit 公开 JSON 搜索（无需登录）。"""
    headers = {"User-Agent": "TrendRadarConsole/1.0 (news research bot)"}
    results: List[Dict[str, Any]] = []
    seen = set()
    for q in queries:
        q = (q or "").strip()
        if not q:
            continue
        try:
            r = requests.get(
                "https://www.reddit.com/search.json",
                params={"q": q, "sort": "new", "limit": max(5, min(25, limit_per_query))},
                headers=headers,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
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
                results.append(
                    {
                        "href": href,
                        "title": title,
                        "raw": selftext or title,
                        "content": selftext[:2000],
                        "author": str(d.get("author") or ""),
                        "source_query": q,
                        "rank": d.get("score"),
                    }
                )
        except Exception as e:
            print(f"[extra] Reddit 搜索失败 q={q!r}: {e}")
    return results


def search_telegram(queries: List[str], limit_per_query: int = 20) -> List[Dict[str, Any]]:
    """
    用已有 Telethon 会话做全局消息搜索（可选）。
    无会话或依赖缺失时返回空列表。
    """
    session = PROJECT_ROOT / "messages" / "telegram_session.session"
    if not session.exists():
        print("[extra] Telegram 跳过：未找到 messages/telegram_session.session")
        return []

    try:
        from messages.telegram_listener import API_ID, API_HASH
    except Exception as e:
        print(f"[extra] Telegram 跳过：无法导入 API 配置: {e}")
        return []

    try:
        from telethon.sync import TelegramClient
    except Exception as e:
        print(f"[extra] Telegram 跳过：未安装 telethon: {e}")
        return []

    results: List[Dict[str, Any]] = []
    seen = set()
    try:
        with TelegramClient(str(session), API_ID, API_HASH) as client:
            if not client.is_user_authorized():
                print("[extra] Telegram 跳过：会话未授权")
                return []
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
                            author = getattr(sender, "username", None) or getattr(sender, "first_name", "") or ""
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
                            }
                        )
                except Exception as e:
                    print(f"[extra] Telegram 搜索失败 q={q!r}: {e}")
    except Exception as e:
        print(f"[extra] Telegram 客户端失败: {e}")
    return results


def run_extra_searches(
    reddit_queries: Optional[List[str]] = None,
    telegram_queries: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """按平台执行额外搜索并写入缓存。"""
    plats = {str(p).strip().lower() for p in (platforms or ["reddit", "telegram"]) if str(p).strip()}
    summary: Dict[str, Any] = {"reddit": 0, "telegram": 0, "errors": []}

    if "reddit" in plats and reddit_queries:
        items = search_reddit(reddit_queries)
        summary["reddit"] = _merge_items("reddit", "Reddit", items)
        print(f"[extra] Reddit 写入 {summary['reddit']} 条")

    if "telegram" in plats and telegram_queries:
        items = search_telegram(telegram_queries)
        summary["telegram"] = _merge_items("telegram", "Telegram", items)
        print(f"[extra] Telegram 写入 {summary['telegram']} 条")

    return summary
