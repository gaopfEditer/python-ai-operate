# coding=utf-8
"""交易信号状态：配置、爬取时间窗、已见 tweet、卡片。"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORE_DIR = PROJECT_ROOT / "output" / "signals"
STATE_PATH = STORE_DIR / "state.json"
MEDIA_DIR = STORE_DIR / "media"

_LOCK = threading.Lock()

DEFAULT_LIST_ID = "2088443239435215337"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ensure_dirs() -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def parse_list_id(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    m = re.search(r"/lists/(\d+)", text)
    if m:
        return m.group(1)
    m = re.search(r"^(\d{6,})$", text)
    return m.group(1) if m else ""


def list_url(list_id: str) -> str:
    lid = parse_list_id(list_id) or (list_id or "").strip()
    return f"https://x.com/i/lists/{lid}" if lid else ""


_USER_PATH_SKIP = frozenset(
    {
        "i",
        "home",
        "search",
        "explore",
        "notifications",
        "messages",
        "settings",
        "compose",
        "intent",
        "hashtag",
        "lists",
    }
)


def parse_user_handle(raw: str) -> str:
    """从 x.com/用户名 或 @handle 解析博主 handle。"""
    text = (raw or "").strip()
    if not text:
        return ""
    m = re.search(r"(?:x\.com|twitter\.com)/([^/?#]+)", text, re.I)
    if m:
        handle = m.group(1).strip().lstrip("@")
        if handle.lower() in _USER_PATH_SKIP:
            return ""
        return handle
    if text.startswith("@"):
        return text[1:].split("/")[0].strip()
    if re.match(r"^[A-Za-z0-9_]{1,15}$", text):
        return text
    return ""


def user_profile_url(handle: str) -> str:
    h = parse_user_handle(handle) or (handle or "").strip().lstrip("@")
    return f"https://x.com/{h}" if h else ""


def user_scope_id(handle: str) -> str:
    h = parse_user_handle(handle) or (handle or "").strip().lstrip("@")
    return f"user:{h.lower()}" if h else ""


def normalize_debugger_url(raw: str) -> str:
    s = str(raw or "").strip()
    s = re.sub(r"^https?://", "", s, flags=re.I).strip().strip("/")
    return s


def resolve_signals_debugger_url(cfg: Optional[Dict[str, Any]] = None) -> str:
    """信号 CDP 地址：signals 配置 > 全局 crawl_cdp > 默认 9223。"""
    c = cfg if cfg is not None else get_config()
    raw = normalize_debugger_url(str(c.get("debugger_url") or ""))
    if raw:
        return raw
    try:
        from utils.crawl_cdp import resolve_crawl_debugger_url

        return resolve_crawl_debugger_url()
    except Exception:
        return "127.0.0.1:9223"


def _empty_state() -> Dict[str, Any]:
    return {
        "config": {
            "list_id": DEFAULT_LIST_ID,
            "list_url": list_url(DEFAULT_LIST_ID),
            "cutoff_hours": 24,
            "max_tweets": 40,
            "skip_non_trade": False,
            "push_enabled": True,
            # 分时自动监听（北京时间阶梯频率）
            "watch_enabled": False,
            # 周期抓取：5–15 分钟随机间隔
            "cycle_enabled": False,
            "last_crawl_at": "",
            "first_crawl_hours": 8,
            "cycle_min_minutes": 5,
            "cycle_max_minutes": 15,
            # deep 时段：sleep=完全休眠到 07:30；patrol=30–60 分钟巡检
            "deep_sleep_mode": "sleep",
            "user_profile_url": "",
            "user_weeks": 1,
            "user_max_tweets": 50,
            "user_skip_non_trade": True,
            "user_reparse_seen": False,
            "user_push_enabled": True,
            "user_force_push": False,
            "debugger_url": "127.0.0.1:9223",
        },
        "windows": [],
        "seen_tweet_ids": [],
        "pushed_tweet_ids": [],
        "push_log": [],
        "cards": [],
        "updated_at": "",
    }


def load_state() -> Dict[str, Any]:
    ensure_dirs()
    with _LOCK:
        if not STATE_PATH.exists():
            return _empty_state()
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return _empty_state()
        if not isinstance(data, dict):
            return _empty_state()
        base = _empty_state()
        base.update({k: data.get(k, base[k]) for k in base})
        cfg = base.get("config") if isinstance(base.get("config"), dict) else {}
        merged = _empty_state()["config"]
        merged.update(cfg or {})
        if not merged.get("list_id"):
            merged["list_id"] = DEFAULT_LIST_ID
        merged["list_url"] = list_url(str(merged.get("list_id") or ""))
        base["config"] = merged
        if not isinstance(base.get("windows"), list):
            base["windows"] = []
        if not isinstance(base.get("seen_tweet_ids"), list):
            base["seen_tweet_ids"] = []
        if not isinstance(base.get("pushed_tweet_ids"), list):
            base["pushed_tweet_ids"] = []
        if not isinstance(base.get("push_log"), list):
            base["push_log"] = []
        if not isinstance(base.get("cards"), list):
            base["cards"] = []
        return base


def save_state(state: Dict[str, Any]) -> None:
    ensure_dirs()
    payload = dict(state or {})
    payload["updated_at"] = _now_iso()
    with _LOCK:
        STATE_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def get_config() -> Dict[str, Any]:
    return dict(load_state().get("config") or {})


def save_config(patch: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state()
    cfg = dict(state.get("config") or {})
    if "list_url" in patch or "list_id" in patch:
        raw = str(patch.get("list_url") or patch.get("list_id") or "")
        lid = parse_list_id(raw) or parse_list_id(str(cfg.get("list_id") or ""))
        if lid:
            cfg["list_id"] = lid
            cfg["list_url"] = list_url(lid)
    for key in ("cutoff_hours", "max_tweets"):
        if key in patch and patch[key] is not None:
            try:
                cfg[key] = int(patch[key])
            except Exception:
                pass
    if "skip_non_trade" in patch:
        cfg["skip_non_trade"] = bool(patch["skip_non_trade"])
    if "push_enabled" in patch:
        cfg["push_enabled"] = bool(patch["push_enabled"])
    if "watch_enabled" in patch:
        cfg["watch_enabled"] = bool(patch["watch_enabled"])
    if "cycle_enabled" in patch:
        cfg["cycle_enabled"] = bool(patch["cycle_enabled"])
    if "last_crawl_at" in patch:
        cfg["last_crawl_at"] = str(patch.get("last_crawl_at") or "")
    for key in ("first_crawl_hours", "cycle_min_minutes", "cycle_max_minutes"):
        if key in patch and patch[key] is not None:
            try:
                cfg[key] = int(patch[key])
            except Exception:
                pass
    if "deep_sleep_mode" in patch:
        mode = str(patch.get("deep_sleep_mode") or "sleep").strip().lower()
        cfg["deep_sleep_mode"] = mode if mode in ("sleep", "patrol") else "sleep"
    if "user_profile_url" in patch or "user_handle" in patch:
        raw = str(patch.get("user_profile_url") or patch.get("user_handle") or "")
        handle = parse_user_handle(raw)
        if handle:
            cfg["user_profile_url"] = user_profile_url(handle)
    if "user_weeks" in patch and patch["user_weeks"] is not None:
        try:
            cfg["user_weeks"] = max(1, min(int(patch["user_weeks"]), 52))
        except Exception:
            pass
    if "user_max_tweets" in patch and patch["user_max_tweets"] is not None:
        try:
            cfg["user_max_tweets"] = max(5, min(int(patch["user_max_tweets"]), 300))
        except Exception:
            pass
    if "user_skip_non_trade" in patch:
        cfg["user_skip_non_trade"] = bool(patch["user_skip_non_trade"])
    if "user_reparse_seen" in patch:
        cfg["user_reparse_seen"] = bool(patch["user_reparse_seen"])
    if "user_push_enabled" in patch:
        cfg["user_push_enabled"] = bool(patch["user_push_enabled"])
    if "user_force_push" in patch:
        cfg["user_force_push"] = bool(patch["user_force_push"])
    if "debugger_url" in patch:
        raw = normalize_debugger_url(str(patch.get("debugger_url") or ""))
        if raw:
            cfg["debugger_url"] = raw
    state["config"] = cfg
    save_state(state)
    return cfg


def media_root() -> Path:
    ensure_dirs()
    return MEDIA_DIR


def resolve_media(rel: str) -> Path:
    ensure_dirs()
    clean = (rel or "").replace("\\", "/").lstrip("/")
    if ".." in clean.split("/"):
        raise ValueError("非法路径")
    path = (MEDIA_DIR / clean).resolve()
    root = MEDIA_DIR.resolve()
    if path != root and root not in path.parents:
        raise ValueError("越界路径")
    return path


def upsert_card(card: Dict[str, Any]) -> Dict[str, Any]:
    from signals.card_db import db_upsert_card, ensure_migrated

    state = load_state()
    ensure_migrated(list(state.get("cards") or []))
    saved = db_upsert_card(card)
    tid = str(card.get("tweet_id") or "")
    seen = list(state.get("seen_tweet_ids") or [])
    if tid and tid not in seen:
        seen.append(tid)
    state["seen_tweet_ids"] = seen[-5000:]
    # cards 数组仅作兼容占位，主存储在 SQLite
    if not state.get("cards"):
        state["cards"] = []
    save_state(state)
    return saved


def mark_seen(tweet_ids: List[str]) -> None:
    state = load_state()
    seen = list(state.get("seen_tweet_ids") or [])
    sset = set(seen)
    for tid in tweet_ids:
        t = str(tid or "").strip()
        if t and t not in sset:
            seen.append(t)
            sset.add(t)
    state["seen_tweet_ids"] = seen[-5000:]
    save_state(state)


def add_window(
    *,
    list_id: str,
    window_from: str,
    window_to: str,
    fetched: int = 0,
    parsed: int = 0,
    skipped: int = 0,
) -> Dict[str, Any]:
    state = load_state()
    win = {
        "list_id": list_id,
        "from": window_from,
        "to": window_to,
        "fetched": int(fetched),
        "parsed": int(parsed),
        "skipped": int(skipped),
        "fetched_at": _now_iso(),
    }
    windows = list(state.get("windows") or [])
    windows.insert(0, win)
    state["windows"] = windows[:100]
    save_state(state)
    return win


def latest_window_end(list_id: str) -> Optional[datetime]:
    """该列表最近一次成功爬取覆盖到的结束时间（本地/带时区）。"""
    state = load_state()
    lid = parse_list_id(list_id) or list_id
    for w in state.get("windows") or []:
        if str(w.get("list_id") or "") != str(lid):
            continue
        raw = str(w.get("to") or "").strip()
        if not raw:
            continue
        dt = parse_dt(raw)
        if dt:
            return dt
    return None


def parse_dt(raw: str) -> Optional[datetime]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _card_sort_ts(card: Dict[str, Any]) -> datetime:
    """卡片排序用时间戳：优先发帖时间，其次解析时间。"""
    for key in ("created_at", "parsed_at", "display_time"):
        dt = parse_dt(str(card.get(key) or ""))
        if dt is not None:
            return dt
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def card_count() -> int:
    from signals.card_db import db_count, ensure_migrated

    state = load_state()
    ensure_migrated(list(state.get("cards") or []))
    return db_count()


def list_cards(
    *,
    list_id: str = "",
    user_handle: str = "",
    only_trade: bool = False,
    limit: int = 100,
    from_ts: Optional[int] = None,
    to_ts: Optional[int] = None,
    days: Optional[int] = None,
    from_raw: str = "",
    to_raw: str = "",
) -> List[Dict[str, Any]]:
    from signals.card_db import db_list_cards, ensure_migrated, resolve_time_range

    state = load_state()
    cards_json = list(state.get("cards") or [])
    if ensure_migrated(cards_json) and cards_json:
        state["cards"] = []
        save_state(state)
    f_ts, t_ts = resolve_time_range(days=days, from_raw=from_raw, to_raw=to_raw)
    if from_ts is not None:
        f_ts = from_ts
    if to_ts is not None:
        t_ts = to_ts
    return db_list_cards(
        list_id=list_id,
        user_handle=user_handle,
        only_trade=only_trade,
        limit=limit,
        from_ts=f_ts,
        to_ts=t_ts,
    )


def get_card_by_tweet_id(tweet_id: str) -> Optional[Dict[str, Any]]:
    """按 tweet_id 查找本地卡片（含 cache_only 缓存项）。"""
    from signals.card_db import db_get_card_by_tweet_id, ensure_migrated

    tid = str(tweet_id or "").strip()
    if not tid:
        return None
    state = load_state()
    ensure_migrated(list(state.get("cards") or []))
    row = db_get_card_by_tweet_id(tid)
    if row:
        return row
    for c in state.get("cards") or []:
        if str(c.get("tweet_id") or "") == tid:
            return dict(c)
    return None


def save_card_remote_id(tweet_id: str, cards_api_id: int) -> None:
    """推送成功后记住远端 Cards id，回测时可直接使用。"""
    from signals.card_db import db_save_card_remote_id, ensure_migrated

    tid = str(tweet_id or "").strip()
    if not tid or not cards_api_id:
        return
    state = load_state()
    ensure_migrated(list(state.get("cards") or []))
    db_save_card_remote_id(tid, int(cards_api_id))


def clear_user_cache(handle: str) -> Dict[str, Any]:
    """清除博主回溯 scope 下的卡片与 seen/pushed 记录。"""
    from signals.card_db import db_delete_user_cards, ensure_migrated

    h = parse_user_handle(handle) or (handle or "").strip().lstrip("@")
    if not h:
        return {"success": False, "error": "请填写有效的博主 handle"}
    scope = user_scope_id(h)
    state = load_state()
    ensure_migrated(list(state.get("cards") or []))
    removed_tids = db_delete_user_cards(h)
    rset = set(removed_tids)
    seen = [t for t in list(state.get("seen_tweet_ids") or []) if t not in rset]
    pushed = [t for t in list(state.get("pushed_tweet_ids") or []) if t not in rset]
    state["seen_tweet_ids"] = seen
    state["pushed_tweet_ids"] = pushed
    state["cards"] = []
    save_state(state)
    return {
        "success": True,
        "handle": h,
        "scope_id": scope,
        "removed_cards": len(removed_tids),
        "tweet_ids": removed_tids,
    }


def is_seen(tweet_id: str) -> bool:
    tid = str(tweet_id or "").strip()
    if not tid:
        return False
    state = load_state()
    return tid in set(state.get("seen_tweet_ids") or [])


def is_pushed(tweet_id: str) -> bool:
    tid = str(tweet_id or "").strip()
    if not tid:
        return False
    state = load_state()
    return tid in set(state.get("pushed_tweet_ids") or [])


def mark_pushed(tweet_ids: List[str], *, status: str = "ok") -> None:
    state = load_state()
    pushed = list(state.get("pushed_tweet_ids") or [])
    pset = set(pushed)
    log = list(state.get("push_log") or [])
    now = _now_iso()
    for tid in tweet_ids:
        t = str(tid or "").strip()
        if not t:
            continue
        if t not in pset:
            pushed.append(t)
            pset.add(t)
        log.insert(0, {"tweet_id": t, "status": status, "at": now})
    state["pushed_tweet_ids"] = pushed[-8000:]
    state["push_log"] = log[:200]
    save_state(state)


def unmark_pushed(tweet_ids: List[str]) -> None:
    """编辑/重解析后清除已推送标记，便于再次推送回测。"""
    ids = {str(x).strip() for x in tweet_ids if str(x).strip()}
    if not ids:
        return
    state = load_state()
    pushed = [t for t in list(state.get("pushed_tweet_ids") or []) if t not in ids]
    state["pushed_tweet_ids"] = pushed
    save_state(state)
