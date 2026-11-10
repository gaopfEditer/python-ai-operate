# coding=utf-8
"""X GraphQL/REST 抓取（Cookie 会话，输出与 signals.crawl DOM 结构兼容）。"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from signals.store import parse_dt, parse_list_id, parse_user_handle
from signals.cdp_session_loader import (
    ensure_x_graphql_query_ids,
    get_cached_x_session,
    invalidate_cached_x_query_id,
)
from signals.http_proxy import urlopen as vpn_urlopen
from signals.x_session import DEFAULT_QUERY_IDS, query_id, resolve_x_session, session_ready

logger = logging.getLogger(__name__)

ProgressCb = Optional[Callable[[str], None]]

GRAPHQL_FEATURES = {
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}

_TWITTER_DATE_RE = re.compile(
    r"^(\w{3})\s+(\w{3})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\s+([+-]\d{4})\s+(\d{4})$"
)


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)


def twitter_created_to_iso(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if "T" in text and re.search(r"\d{4}-\d{2}-\d{2}", text):
        return text
    try:
        dt = datetime.strptime(text, "%a %b %d %H:%M:%S %z %Y")
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    parsed = parse_dt(text)
    if parsed:
        return parsed.astimezone(timezone.utc).isoformat()
    return ""


def _media_url_from_entity(ent: Dict[str, Any]) -> str:
    media_url = str(ent.get("media_url_https") or ent.get("media_url") or "").strip()
    if not media_url:
        return ""
    try:
        url = urllib.parse.urlparse(media_url)
        q = urllib.parse.parse_qs(url.query)
        fmt = (q.get("format") or ["jpg"])[0]
        name = (q.get("name") or ["large"])[0]
        base = media_url.split("?")[0]
        return f"{base}?format={fmt}&name={name}"
    except Exception:
        return media_url


def _images_from_legacy(legacy: Dict[str, Any]) -> List[Dict[str, str]]:
    images: List[Dict[str, str]] = []
    seen: set = set()
    for key in ("extended_entities", "entities"):
        block = legacy.get(key) if isinstance(legacy.get(key), dict) else {}
        for ent in block.get("media") or []:
            if not isinstance(ent, dict):
                continue
            if str(ent.get("type") or "").lower() not in ("photo", "animated_gif"):
                continue
            u = _media_url_from_entity(ent)
            if not u or u in seen:
                continue
            seen.add(u)
            images.append({"url": u, "alt": str(ent.get("ext_alt_text") or "")})
    return images


def _unwrap_tweet_result(node: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(node, dict):
        return None
    t = node.get("tweet") if isinstance(node.get("tweet"), dict) else node
    if t.get("__typename") == "TweetWithVisibilityResults" and isinstance(t.get("tweet"), dict):
        t = t["tweet"]
    legacy = t.get("legacy") if isinstance(t.get("legacy"), dict) else None
    if not legacy:
        return None
    return t


def tweet_node_to_item(node: Any) -> Optional[Dict[str, Any]]:
    t = _unwrap_tweet_result(node)
    if not t:
        return None
    legacy = t["legacy"]
    tid = str(t.get("rest_id") or legacy.get("id_str") or "").strip()
    if not tid:
        return None
    user = {}
    try:
        user = (
            t.get("core", {})
            .get("user_results", {})
            .get("result", {})
            .get("legacy", {})
        )
    except Exception:
        user = {}
    if not isinstance(user, dict):
        user = {}
    screen = str(user.get("screen_name") or legacy.get("screen_name") or "").strip()
    author = f"@{screen}" if screen else ""
    created_raw = str(legacy.get("created_at") or "")
    created_iso = twitter_created_to_iso(created_raw)
    text = str(legacy.get("full_text") or legacy.get("text") or "").strip()
    images = _images_from_legacy(legacy)
    item = {
        "tweet_id": tid,
        "url": f"https://x.com/{screen}/status/{tid}" if screen else f"https://x.com/i/web/status/{tid}",
        "text": text[:8000],
        "author": author,
        "created_at": created_iso or created_raw,
        "images": images,
        "has_media": bool(images) or bool(legacy.get("extended_entities")),
        "source": "x_api",
    }
    from signals.publish_time import normalize_tweet_item_times

    return normalize_tweet_item_times(item)


def _iter_instruction_lists(data: Any) -> Iterable[List[Any]]:
    if isinstance(data, dict):
        ins = data.get("instructions")
        if isinstance(ins, list):
            yield ins
        for v in data.values():
            yield from _iter_instruction_lists(v)
    elif isinstance(data, list):
        for x in data:
            yield from _iter_instruction_lists(x)


def parse_timeline_payload(data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    items: List[Dict[str, Any]] = []
    next_cursor = ""
    for instructions in _iter_instruction_lists(data):
        for ins in instructions:
            if not isinstance(ins, dict):
                continue
            if ins.get("type") not in ("TimelineAddEntries", "TimelineReplaceEntry"):
                continue
            for ent in ins.get("entries") or []:
                if not isinstance(ent, dict):
                    continue
                content = ent.get("content") if isinstance(ent.get("content"), dict) else {}
                if content.get("entryType") == "TimelineTimelineCursor":
                    if content.get("cursorType") == "Bottom":
                        next_cursor = str(content.get("value") or "")
                    continue
                item_content = content.get("itemContent") if isinstance(content.get("itemContent"), dict) else {}
                tw = item_content.get("tweet_results", {}).get("result")
                parsed = tweet_node_to_item(tw)
                if parsed:
                    items.append(parsed)
    return items, next_cursor


def _is_x_auth_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "401" in msg or "could not authenticate" in msg or 'code":32' in msg


def _is_x_query_not_found_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "query not found" in msg or (
        "404" in msg and ("query" in msg or "graphql" in msg)
    )


def _refresh_session_query_ids(
    client: "XApiClient",
    operations: Tuple[str, ...],
    *,
    debugger_url: str = "",
    navigate_urls: Tuple[str, ...] = (),
    progress: ProgressCb = None,
    invalidate_op: str = "",
) -> bool:
    """401 或 404 Query not found 后 force 刷新 queryId；成功则更新 client 会话。仅调用方重试一次。"""
    if invalidate_op:
        invalidate_cached_x_query_id(invalidate_op)
    refreshed = ensure_x_graphql_query_ids(
        operations,
        debugger_url=debugger_url,
        navigate_urls=navigate_urls or None,
        progress=progress,
        force=True,
    )
    if not refreshed:
        return False
    client.replace_session(refreshed)
    return True


class XApiClient:
    def __init__(self, session: Optional[Dict[str, Any]] = None) -> None:
        self.session = session or get_cached_x_session() or {}
        if not session_ready(self.session):
            raise RuntimeError("X 会话未配置（需要 auth_token + ct0）")

    def replace_session(self, session: Dict[str, Any]) -> None:
        self.session = dict(session)

    def _headers(self) -> Dict[str, str]:
        s = self.session
        return {
            "authorization": str(s.get("authorization") or ""),
            "x-csrf-token": str(s.get("ct0") or ""),
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "zh-cn",
            "content-type": "application/json",
            "accept": "*/*",
            "cookie": str(s.get("cookie_header") or ""),
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "referer": "https://x.com/",
        }

    def graphql(
        self,
        operation: str,
        variables: Dict[str, Any],
        *,
        method: str = "GET",
    ) -> Dict[str, Any]:
        qid = query_id(self.session, operation) or DEFAULT_QUERY_IDS.get(operation, "")
        if not qid:
            raise RuntimeError(f"缺少 GraphQL queryId: {operation}")
        payload = {
            "variables": variables,
            "features": GRAPHQL_FEATURES,
            "queryId": qid,
        }
        url = f"https://x.com/i/api/graphql/{qid}/{operation}"
        if method.upper() == "GET":
            q = urllib.parse.urlencode(
                {
                    "variables": json.dumps(variables, separators=(",", ":")),
                    "features": json.dumps(GRAPHQL_FEATURES, separators=(",", ":")),
                }
            )
            full = f"{url}?{q}"
            req = urllib.request.Request(full, headers=self._headers(), method="GET")
        else:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers=self._headers(), method="POST")
        try:
            with vpn_urlopen(req, timeout=25) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"{operation} HTTP {e.code}: {err_body}") from e
        data = json.loads(raw)
        if data.get("errors"):
            msg = data["errors"][0].get("message") if isinstance(data["errors"], list) else str(data["errors"])
            raise RuntimeError(f"{operation} GraphQL: {msg}")
        return data

    def user_id_by_screen_name(self, screen_name: str) -> str:
        sn = parse_user_handle(screen_name) or str(screen_name or "").strip().lstrip("@")
        data = self.graphql(
            "UserByScreenName",
            {"screen_name": sn, "withSafetyModeUserFields": True},
            method="POST",
        )
        uid = (
            data.get("data", {})
            .get("user", {})
            .get("result", {})
            .get("rest_id")
        )
        if not uid:
            raise RuntimeError(f"找不到用户 @{sn}")
        return str(uid)

    def fetch_timeline_page(
        self,
        operation: str,
        variables: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], str]:
        data = self.graphql(operation, variables, method="GET")
        return parse_timeline_payload(data)


def _ingest_timeline_chunk(
    chunk: List[Dict[str, Any]],
    *,
    since_cmp: datetime,
    by_id: Dict[str, Dict[str, Any]],
    max_tweets: int,
    realtime_incremental: bool,
    is_known: Optional[Callable[[str], bool]],
) -> Tuple[bool, bool, int, int]:
    """返回 (stop_pagination, page_stale, page_seen_delta, page_old_delta)。"""
    from signals.incremental import filter_newest_until_known, tweet_id_from_item

    stop = False
    if realtime_incremental and is_known:
        chunk, stop = filter_newest_until_known(
            chunk,
            id_fn=tweet_id_from_item,
            is_known=is_known,
            enabled=True,
        )
    stale = True
    seen_delta = 0
    old_delta = 0
    for it in chunk:
        tid = str(it.get("tweet_id") or "")
        if not tid:
            continue
        seen_delta += 1
        created = parse_dt(str(it.get("created_at") or ""))
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        too_old = bool(created and created < since_cmp)
        if too_old:
            old_delta += 1
        else:
            stale = False
            by_id[tid] = it
    return stop, stale, seen_delta, old_delta


def fetch_list_timeline_api(
    list_id: str,
    *,
    since: datetime,
    max_tweets: int = 40,
    progress: ProgressCb = None,
    should_abort: Optional[Callable[[], bool]] = None,
    realtime_incremental: bool = False,
    is_known: Optional[Callable[[str], bool]] = None,
    debugger_url: str = "",
) -> Dict[str, Any]:
    resolve_x_session(debugger_url=debugger_url, progress=progress, force_refresh=False)
    if not session_ready():
        return {"success": False, "error": "X API 会话未配置", "items": [], "route": "x_api"}
    lid = parse_list_id(list_id) or str(list_id or "").strip()
    if not lid:
        return {"success": False, "error": "缺少 list_id", "items": []}
    ensure_x_graphql_query_ids(
        ("ListLatestTweetsTimeline",),
        debugger_url=debugger_url,
        navigate_urls=(
            f"https://x.com/i/lists/{lid}",
            "https://x.com/home",
        ),
        progress=progress,
    )
    since_cmp = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
    client = XApiClient()
    by_id: Dict[str, Dict[str, Any]] = {}
    cursor = ""
    page_seen = 0
    page_old = 0
    max_pages = max(3, min(max_tweets // 8 + 4, 30))

    _log(progress, f"X API 列表 {lid}（最多 {max_tweets} 条）…")
    for page_i in range(max_pages):
        if should_abort and should_abort():
            break
        variables: Dict[str, Any] = {
            "listId": lid,
            "count": min(40, max(20, max_tweets)),
        }
        if cursor:
            variables["cursor"] = cursor
        try:
            chunk, next_cur = client.fetch_timeline_page("ListLatestTweetsTimeline", variables)
        except Exception as e:
            if by_id:
                break
            if page_i == 0 and (_is_x_auth_error(e) or _is_x_query_not_found_error(e)):
                if _is_x_query_not_found_error(e):
                    _log(progress, "X API 404 Query not found：清除 queryId 并 force 刷新后重试…")
                else:
                    _log(progress, "X API 401：刷新 CDP queryId/Cookie 后重试…")
                op = "ListLatestTweetsTimeline"
                if _refresh_session_query_ids(
                    client,
                    (op,),
                    debugger_url=debugger_url,
                    navigate_urls=(
                        f"https://x.com/i/lists/{lid}",
                        "https://x.com/home",
                    ),
                    progress=progress,
                    invalidate_op=op if _is_x_query_not_found_error(e) else "",
                ):
                    try:
                        chunk, next_cur = client.fetch_timeline_page(op, variables)
                    except Exception as e2:
                        return {"success": False, "error": str(e2), "items": [], "route": "x_api"}
                else:
                    return {"success": False, "error": str(e), "items": [], "route": "x_api"}
            else:
                return {"success": False, "error": str(e), "items": [], "route": "x_api"}
        if not chunk and not by_id:
            return {"success": False, "error": "列表 API 无数据", "items": [], "route": "x_api"}
        stop, stale, seen_delta, old_delta = _ingest_timeline_chunk(
            chunk,
            since_cmp=since_cmp,
            by_id=by_id,
            max_tweets=max_tweets,
            realtime_incremental=realtime_incremental,
            is_known=is_known,
        )
        page_seen += seen_delta
        page_old += old_delta
        _log(
            progress,
            f"X API 列表页 {page_i + 1} · 窗口内 {len(by_id)} · 本页 {len(chunk)}"
            + (" · 已到时间窗之前" if stale and chunk else "")
            + (" · 命中已存帖，停止翻页" if stop else ""),
        )
        if len(by_id) >= max_tweets:
            break
        if stop:
            break
        if stale and len(by_id) >= 3 and not realtime_incremental:
            break
        if not next_cur or next_cur == cursor:
            break
        cursor = next_cur
        time.sleep(0.35)

    items = sorted(
        by_id.values(),
        key=lambda x: parse_dt(str(x.get("created_at") or ""))
        or datetime(1970, 1, 1, tzinfo=timezone.utc),
        reverse=True,
    )[:max_tweets]
    return {
        "success": True,
        "list_id": lid,
        "url": f"https://x.com/i/lists/{lid}",
        "items": items,
        "count": len(items),
        "page_seen": page_seen,
        "page_old": page_old,
        "route": "x_api",
    }


def fetch_user_timeline_api(
    handle: str,
    *,
    since: datetime,
    max_tweets: int = 80,
    include_replies: bool = False,
    progress: ProgressCb = None,
    should_abort: Optional[Callable[[], bool]] = None,
    realtime_incremental: bool = False,
    is_known: Optional[Callable[[str], bool]] = None,
    debugger_url: str = "",
) -> Dict[str, Any]:
    resolve_x_session(debugger_url=debugger_url, progress=progress, force_refresh=False)
    if not session_ready():
        return {"success": False, "error": "X API 会话未配置", "items": [], "route": "x_api"}
    h = parse_user_handle(handle) or str(handle or "").strip().lstrip("@")
    if not h:
        return {"success": False, "error": "缺少 handle", "items": []}
    op = "UserTweetsAndReplies" if include_replies else "UserTweets"
    ensure_x_graphql_query_ids(
        ("UserByScreenName", op),
        debugger_url=debugger_url,
        navigate_urls=(f"https://x.com/{h}", "https://x.com/home"),
        progress=progress,
    )
    since_cmp = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
    client = XApiClient()
    try:
        uid = client.user_id_by_screen_name(h)
    except Exception as e:
        if _is_x_auth_error(e) or _is_x_query_not_found_error(e):
            if _is_x_query_not_found_error(e):
                _log(progress, "X API 404 Query not found：清除 UserByScreenName queryId 并 force 刷新…")
            else:
                _log(progress, "X API 401：刷新 CDP queryId/Cookie 后重试用户解析…")
            resolve_op = "UserByScreenName"
            if _refresh_session_query_ids(
                client,
                (resolve_op, op),
                debugger_url=debugger_url,
                navigate_urls=(f"https://x.com/{h}", "https://x.com/home"),
                progress=progress,
                invalidate_op=resolve_op if _is_x_query_not_found_error(e) else "",
            ):
                try:
                    uid = client.user_id_by_screen_name(h)
                except Exception as e2:
                    return {"success": False, "error": str(e2), "items": [], "route": "x_api"}
            else:
                return {"success": False, "error": str(e), "items": [], "route": "x_api"}
        else:
            return {"success": False, "error": str(e), "items": [], "route": "x_api"}
    by_id: Dict[str, Dict[str, Any]] = {}
    cursor = ""
    page_seen = 0
    page_old = 0
    max_pages = max(4, min(max_tweets // 10 + 6, 40))

    _log(progress, f"X API @{h}（uid={uid} · {op}）…")
    for page_i in range(max_pages):
        if should_abort and should_abort():
            break
        variables: Dict[str, Any] = {
            "userId": uid,
            "count": min(40, max(20, max_tweets)),
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": True,
            "withVoice": True,
        }
        if cursor:
            variables["cursor"] = cursor
        try:
            chunk, next_cur = client.fetch_timeline_page(op, variables)
        except Exception as e:
            if by_id:
                break
            if page_i == 0 and (_is_x_auth_error(e) or _is_x_query_not_found_error(e)):
                if _is_x_query_not_found_error(e):
                    _log(progress, f"X API 404 Query not found：清除 {op} queryId 并 force 刷新…")
                else:
                    _log(progress, "X API 401：刷新 CDP queryId 后重试时间线…")
                if _refresh_session_query_ids(
                    client,
                    (op,),
                    debugger_url=debugger_url,
                    navigate_urls=(f"https://x.com/{h}", "https://x.com/home"),
                    progress=progress,
                    invalidate_op=op if _is_x_query_not_found_error(e) else "",
                ):
                    try:
                        chunk, next_cur = client.fetch_timeline_page(op, variables)
                    except Exception as e2:
                        return {"success": False, "error": str(e2), "items": [], "route": "x_api"}
                else:
                    return {"success": False, "error": str(e), "items": [], "route": "x_api"}
            else:
                return {"success": False, "error": str(e), "items": [], "route": "x_api"}
        stop, stale, seen_delta, old_delta = _ingest_timeline_chunk(
            chunk,
            since_cmp=since_cmp,
            by_id=by_id,
            max_tweets=max_tweets,
            realtime_incremental=realtime_incremental,
            is_known=is_known,
        )
        page_seen += seen_delta
        page_old += old_delta
        _log(
            progress,
            f"X API @{h} 页 {page_i + 1} · 窗口内 {len(by_id)} · 本页 {len(chunk)}"
            + (" · 命中已存帖，停止翻页" if stop else ""),
        )
        if len(by_id) >= max_tweets:
            break
        if stop:
            break
        if stale and page_i >= 1 and not realtime_incremental:
            break
        if not next_cur or next_cur == cursor:
            break
        cursor = next_cur
        time.sleep(0.35)

    items = sorted(
        by_id.values(),
        key=lambda x: parse_dt(str(x.get("created_at") or ""))
        or datetime(1970, 1, 1, tzinfo=timezone.utc),
        reverse=True,
    )[:max_tweets]
    return {
        "success": bool(items),
        "items": items,
        "count": len(items),
        "page_seen": page_seen,
        "page_old": page_old,
        "route": "x_api",
        "handle": h,
    }
