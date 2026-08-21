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


def _empty_state() -> Dict[str, Any]:
    return {
        "config": {
            "list_id": DEFAULT_LIST_ID,
            "list_url": list_url(DEFAULT_LIST_ID),
            "cutoff_hours": 24,
            "max_tweets": 40,
            "skip_non_trade": False,
            "push_enabled": True,
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
    state = load_state()
    cards: List[Dict[str, Any]] = list(state.get("cards") or [])
    tid = str(card.get("tweet_id") or "")
    replaced = False
    if tid:
        for i, old in enumerate(cards):
            if str(old.get("tweet_id") or "") == tid:
                cards[i] = card
                replaced = True
                break
    if not replaced:
        cards.insert(0, card)
    # 保留最近 500
    state["cards"] = cards[:500]
    seen = list(state.get("seen_tweet_ids") or [])
    if tid and tid not in seen:
        seen.append(tid)
    state["seen_tweet_ids"] = seen[-5000:]
    save_state(state)
    return card


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


def list_cards(
    *,
    list_id: str = "",
    only_trade: bool = False,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    state = load_state()
    lid = parse_list_id(list_id) if list_id else ""
    out: List[Dict[str, Any]] = []
    for c in state.get("cards") or []:
        if lid and str(c.get("list_id") or "") not in ("", lid):
            continue
        sig = c.get("signal") if isinstance(c.get("signal"), dict) else {}
        if only_trade and not sig.get("has_trade_signal"):
            continue
        out.append(c)
        if len(out) >= max(1, int(limit)):
            break
    return out


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
