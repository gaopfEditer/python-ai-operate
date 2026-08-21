# coding=utf-8
"""通过 FxTwitter / vxtwitter 拉取推文全文、配图与互动数。"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

UA = "Mozilla/5.0 TrendRadarTweetCards/1.0"


def extract_tweet_id(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    m = re.search(
        r"(?:twitter\.com|x\.com|vxtwitter\.com|fxtwitter\.com)/[^/\s]+/status/(\d+)",
        raw,
        re.I,
    )
    if m:
        return m.group(1)
    m = re.search(r"/status/(\d+)", raw)
    if m:
        return m.group(1)
    m = re.fullmatch(r"(\d{6,})", raw)
    return m.group(1) if m else ""


def extract_handle(text: str) -> str:
    m = re.search(
        r"(?:twitter\.com|x\.com|vxtwitter\.com|fxtwitter\.com)/([^/\s?#]+)/status/",
        text or "",
        re.I,
    )
    if not m:
        return ""
    h = m.group(1)
    if h.lower() in ("i", "intent", "share"):
        return ""
    return h


def _http_json(url: str, timeout: float = 20.0) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw) if raw else {}
    return data if isinstance(data, dict) else {}


def _int(v: Any) -> int:
    try:
        if v is None or v == "":
            return 0
        return int(float(v))
    except Exception:
        return 0


def _images_from_fxtwitter(tweet: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    media = tweet.get("media") if isinstance(tweet.get("media"), dict) else {}
    for key in ("photos", "images"):
        items = media.get(key) or []
        if not isinstance(items, list):
            continue
        for it in items:
            if isinstance(it, str) and it.startswith("http"):
                out.append(it)
            elif isinstance(it, dict):
                u = it.get("url") or it.get("image") or it.get("thumbnail_url") or ""
                if u:
                    out.append(str(u))
    # all / videos 封面
    for it in media.get("all") or []:
        if not isinstance(it, dict):
            continue
        u = it.get("url") or it.get("thumbnail_url") or ""
        t = str(it.get("type") or "")
        if u and (t in ("photo", "image", "") or "photo" in t):
            if str(u) not in out:
                out.append(str(u))
        elif u and t in ("video", "gif") and it.get("thumbnail_url"):
            thumb = str(it.get("thumbnail_url"))
            if thumb not in out:
                out.append(thumb)
    # 去重保序
    seen = set()
    uniq = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq[:12]


def _normalize_fx(tweet: Dict[str, Any], source: str) -> Dict[str, Any]:
    author = tweet.get("author") if isinstance(tweet.get("author"), dict) else {}
    handle = str(author.get("screen_name") or author.get("username") or "").lstrip("@")
    images = _images_from_fxtwitter(tweet)
    tid = str(tweet.get("id") or tweet.get("id_str") or "")
    url = str(tweet.get("url") or "")
    if not url and handle and tid:
        url = f"https://x.com/{handle}/status/{tid}"
    return {
        "tweet_id": tid,
        "url": url,
        "author_name": str(author.get("name") or handle or ""),
        "author_handle": handle,
        "author_avatar": str(
            author.get("avatar_url")
            or author.get("profile_image_url_https")
            or author.get("avatar")
            or ""
        ),
        "text": str(tweet.get("text") or tweet.get("raw_text") or "").strip(),
        "created_at_tweet": str(tweet.get("created_at") or tweet.get("date") or ""),
        "likes": _int(tweet.get("likes") if tweet.get("likes") is not None else tweet.get("like_count")),
        "replies": _int(tweet.get("replies") if tweet.get("replies") is not None else tweet.get("reply_count")),
        "retweets": _int(
            tweet.get("retweets") if tweet.get("retweets") is not None else tweet.get("retweet_count")
        ),
        "bookmarks": _int(
            tweet.get("bookmarks")
            if tweet.get("bookmarks") is not None
            else tweet.get("bookmark_count")
        ),
        "views": _int(tweet.get("views") if tweet.get("views") is not None else tweet.get("view_count")),
        "images": images,
        "media": tweet.get("media") if isinstance(tweet.get("media"), dict) else {},
        "source": source,
        "raw": tweet,
    }


def _normalize_vx(data: Dict[str, Any], source: str) -> Dict[str, Any]:
    tid = str(data.get("tweetID") or data.get("conversationID") or data.get("id") or "")
    handle = str(data.get("user_screen_name") or data.get("user_name") or "").lstrip("@")
    images: List[str] = []
    for u in data.get("mediaURLs") or []:
        if isinstance(u, str) and u.startswith("http"):
            images.append(u)
    media = data.get("media_extended") or []
    if isinstance(media, list):
        for it in media:
            if isinstance(it, dict):
                u = it.get("url") or it.get("thumbnail_url") or ""
                if u and str(u) not in images:
                    images.append(str(u))
    url = str(data.get("tweetURL") or "")
    if not url and handle and tid:
        url = f"https://x.com/{handle}/status/{tid}"
    return {
        "tweet_id": tid,
        "url": url,
        "author_name": str(data.get("user_name") or handle),
        "author_handle": handle,
        "author_avatar": str(data.get("user_profile_image_url") or ""),
        "text": str(data.get("text") or "").strip(),
        "created_at_tweet": str(data.get("date") or ""),
        "likes": _int(data.get("likes")),
        "replies": _int(data.get("replies")),
        "retweets": _int(data.get("retweets")),
        "bookmarks": _int(data.get("bookmarks")),
        "views": _int(data.get("views") or data.get("viewCount")),
        "images": images[:12],
        "media": {"vxtwitter": media} if media else {},
        "source": source,
        "raw": data,
    }


def fetch_tweet(url_or_id: str) -> Dict[str, Any]:
    """
    拉取单条推文。优先 FxTwitter，失败回退 vxtwitter。
    """
    tid = extract_tweet_id(url_or_id)
    if not tid:
        return {"success": False, "error": "无法解析 Tweet ID，请粘贴含 /status/数字 的链接"}

    handle = extract_handle(url_or_id)
    errors: List[str] = []

    # 1) FxTwitter
    try:
        data = _http_json(f"https://api.fxtwitter.com/status/{tid}")
        tweet = data.get("tweet") if isinstance(data.get("tweet"), dict) else None
        if tweet and (tweet.get("text") is not None or tweet.get("id")):
            card = _normalize_fx(tweet, "fxtwitter")
            if not card.get("tweet_id"):
                card["tweet_id"] = tid
            return {"success": True, **card}
        errors.append(f"fxtwitter: {data.get('message') or 'empty'}")
    except Exception as e:
        errors.append(f"fxtwitter: {e}")

    # 2) vxtwitter（需要 screen_name；未知时用占位 i）
    for screen in ([handle] if handle else []) + ["i", "Twitter"]:
        try:
            data = _http_json(f"https://api.vxtwitter.com/{screen}/status/{tid}")
            if data.get("text") or data.get("tweetID"):
                card = _normalize_vx(data, "vxtwitter")
                if not card.get("tweet_id"):
                    card["tweet_id"] = tid
                return {"success": True, **card}
            errors.append(f"vxtwitter/{screen}: empty")
        except Exception as e:
            errors.append(f"vxtwitter/{screen}: {e}")

    return {
        "success": False,
        "error": "拉取失败：" + " | ".join(errors[:4]),
        "tweet_id": tid,
    }


def split_inputs(raw: str) -> List[str]:
    """支持多行：每行一个链接/ID；也支持同一段里多个 URL。"""
    text = (raw or "").strip()
    if not text:
        return []
    found = re.findall(
        r"https?://(?:www\.)?(?:twitter\.com|x\.com|vxtwitter\.com|fxtwitter\.com)/[^\s]+",
        text,
        re.I,
    )
    if found:
        # 去重保序
        out = []
        seen = set()
        for u in found:
            u = u.rstrip(").,，；;]")
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out
    parts = re.split(r"[\n\r]+", text)
    return [p.strip() for p in parts if p.strip()]
