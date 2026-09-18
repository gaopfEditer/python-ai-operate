# coding=utf-8
"""推文卡片流水线：解析链接 → 拉取 → LLM → 入库。"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from tweet_cards.analyze import analyze_tweet_text
from tweet_cards.fetch import fetch_tweet, split_inputs
from tweet_cards.store import list_cards, list_categories, stats, update_card, upsert_card

ProgressCb = Optional[Callable[[str], None]]


def _log(cb: ProgressCb, msg: str) -> None:
    print(f"[tweet_cards] {msg}")
    if cb:
        try:
            cb(msg)
        except Exception:
            pass


def ingest_one(url_or_id: str, *, progress: ProgressCb = None) -> Dict[str, Any]:
    _log(progress, f"拉取 {url_or_id[:80]}…")
    fetched = fetch_tweet(url_or_id)
    if not fetched.get("success"):
        return fetched

    text = str(fetched.get("text") or "")
    author = str(fetched.get("author_handle") or fetched.get("author_name") or "")
    _log(progress, f"LLM 结构化 @{author or fetched.get('tweet_id')}…")
    llm = analyze_tweet_text(text, author=author)

    payload = {
        "tweet_id": fetched.get("tweet_id"),
        "url": fetched.get("url"),
        "author_name": fetched.get("author_name"),
        "author_handle": fetched.get("author_handle"),
        "author_avatar": fetched.get("author_avatar"),
        "text": text,
        "created_at_tweet": fetched.get("created_at_tweet"),
        "likes": fetched.get("likes") or 0,
        "replies": fetched.get("replies") or 0,
        "retweets": fetched.get("retweets") or 0,
        "bookmarks": fetched.get("bookmarks") or 0,
        "views": fetched.get("views") or 0,
        "images": fetched.get("images") or [],
        "media": fetched.get("media") or {},
        "summary": llm.get("summary") or "",
        "core_points": llm.get("core_points") or [],
        "emotion": llm.get("emotion") or "",
        "tags": llm.get("tags") or [],
        "category": llm.get("category") or "",
        "llm": llm,
        "source": fetched.get("source") or "",
        "raw": fetched.get("raw") or {},
    }
    card = upsert_card(payload)
    return {"success": True, "card": card, "source": fetched.get("source")}


def ingest_tweet_input(
    raw: str,
    *,
    progress: ProgressCb = None,
) -> Dict[str, Any]:
    items = split_inputs(raw)
    if not items:
        return {"success": False, "error": "请粘贴推特/X 链接（含 /status/ID）"}

    ok: List[Dict[str, Any]] = []
    fail: List[Dict[str, Any]] = []
    for i, item in enumerate(items, 1):
        _log(progress, f"[{i}/{len(items)}] {item[:60]}")
        try:
            r = ingest_one(item, progress=progress)
            if r.get("success"):
                ok.append(r.get("card") or {})
            else:
                fail.append({"input": item, "error": r.get("error") or "失败"})
        except Exception as e:
            fail.append({"input": item, "error": str(e)})

    return {
        "success": len(ok) > 0,
        "cards": ok,
        "failed": fail,
        "ok_count": len(ok),
        "fail_count": len(fail),
        "stats": stats(),
        "message": f"成功 {len(ok)} · 失败 {len(fail)}",
        "error": None if ok else (fail[0]["error"] if fail else "全部失败"),
    }


def _parse_favorited(raw: Any) -> Optional[bool]:
    if raw is None or raw == "" or str(raw).lower() == "all":
        return None
    s = str(raw).strip().lower()
    if s in ("1", "true", "yes", "favorited", "starred"):
        return True
    if s in ("0", "false", "no", "unfavorited"):
        return False
    return None


def list_tweet_cards(
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    category: str = "",
    favorited: Any = None,
) -> Dict[str, Any]:
    result = list_cards(
        page=page,
        page_size=page_size,
        keyword=keyword,
        category=category,
        favorited=_parse_favorited(favorited),
    )
    return {
        "success": True,
        **result,
        "categories": list_categories(),
        "stats": stats(),
    }


def patch_tweet_card(tweet_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    if "favorited" in body:
        fields["favorited"] = bool(body.get("favorited"))
    if "user_category" in body or "category" in body:
        fields["user_category"] = str(
            body.get("user_category") if "user_category" in body else body.get("category") or ""
        ).strip()
    card = update_card(tweet_id, fields)
    if not card:
        return {"success": False, "error": "未找到卡片"}
    return {"success": True, "card": card, "stats": stats()}
