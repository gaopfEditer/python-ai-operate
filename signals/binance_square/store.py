# coding=utf-8
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "binance_square_signals.yaml"
STATE_PATH = PROJECT_ROOT / "output" / "signals" / "binance_square_state.json"
_LOCK = threading.RLock()
_PROFILE_BASE = "https://www.binance.com/zh-CN/square/profile/"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _empty_state() -> Dict[str, Any]:
    return {
        "seen_hrefs": [],
        "seen_content_ids": [],
        "last_posts": [],
        "last_run_at": "",
        "updated_at": "",
    }


def default_config() -> Dict[str, Any]:
    return {
        "debugger_url": "127.0.0.1:9223",
        "backfill_range": "last_7d",
        "cutoff_hours": 24,
        "max_posts_per_profile": 40,
        "try_bapi_first": False,
        "replay_whisper_auto": False,
        "replay_whisper_max_days": 2,
        "cycle_enabled": False,
        "cycle_min_minutes": 5,
        "cycle_max_minutes": 15,
        "first_crawl_hours": 8,
        "cycle_cutoff_hours": 8,
        "last_crawl_at": "",
        "profiles": [],
    }


def load_config() -> Dict[str, Any]:
    with _LOCK:
        if not CONFIG_PATH.is_file():
            return default_config()
        try:
            raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        except Exception:
            return default_config()
    cfg = default_config()
    if isinstance(raw, dict):
        cfg.update({k: raw[k] for k in cfg if k in raw})
        for extra in ("cycle_enabled", "last_crawl_at"):
            if extra in raw:
                cfg[extra] = raw[extra]
        profs = raw.get("profiles")
        if isinstance(profs, list):
            cfg["profiles"] = profs
    return cfg


def save_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    payload = default_config()
    payload.update(cfg or {})
    profiles = payload.get("profiles") or []
    norm_profiles: List[Dict[str, Any]] = []
    for p in profiles:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "").strip()
        url = str(p.get("url") or "").strip()
        if not url and pid:
            url = f"{_PROFILE_BASE}{pid.lstrip('/')}"
        if not pid and url:
            m = re.search(r"/square/profile/([^/?#]+)", url, re.I)
            pid = m.group(1) if m else url.rstrip("/").split("/")[-1]
        if not pid:
            continue
        norm_profiles.append(
            {
                "id": pid,
                "name": str(p.get("name") or pid).strip(),
                "url": url,
                "enabled": bool(p.get("enabled", True)),
            }
        )
    payload["profiles"] = norm_profiles
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        CONFIG_PATH.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    return payload


def load_state() -> Dict[str, Any]:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        if not STATE_PATH.is_file():
            return _empty_state()
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return _empty_state()
    if not isinstance(data, dict):
        return _empty_state()
    base = _empty_state()
    base.update({k: data.get(k, base[k]) for k in base})
    if not isinstance(base.get("seen_hrefs"), list):
        base["seen_hrefs"] = []
    if not isinstance(base.get("seen_content_ids"), list):
        base["seen_content_ids"] = []
    if not isinstance(base.get("last_posts"), list):
        base["last_posts"] = []
    return base


def _content_ids_from_hrefs(hrefs: List[Any]) -> set[str]:
    out: set[str] = set()
    for h in hrefs or []:
        cid = post_content_id({"href": str(h or "")})
        if cid:
            out.add(cid)
    return out


def known_square_content_ids() -> set[str]:
    """已抓取过的 Square 文章 contentId（state + SQLite 卡片）。"""
    known: set[str] = set()
    st = load_state()
    for raw in st.get("seen_content_ids") or []:
        cid = str(raw or "").strip()
        if cid.isdigit():
            known.add(cid)
    known |= _content_ids_from_hrefs(st.get("seen_hrefs") or [])
    try:
        from signals.card_db import db_known_binance_content_ids

        known |= db_known_binance_content_ids()
    except Exception:
        pass
    return known


def register_square_content_ids(ids: List[Any], *, posts: Optional[List[Dict[str, Any]]] = None) -> None:
    st = load_state()
    seen: set[str] = set()
    for raw in st.get("seen_content_ids") or []:
        cid = str(raw or "").strip()
        if cid.isdigit():
            seen.add(cid)
    for raw in ids or []:
        cid = str(raw or "").strip()
        if cid.isdigit():
            seen.add(cid)
    if posts:
        for p in posts:
            if not isinstance(p, dict):
                continue
            cid = post_content_id(p)
            if cid:
                seen.add(cid)
            href = str(p.get("href") or "").strip()
            if href:
                hrefs = list(st.get("seen_hrefs") or [])
                if href not in hrefs:
                    hrefs.append(href)
                st["seen_hrefs"] = hrefs[-5000:]
    st["seen_content_ids"] = sorted(seen)[-8000:]
    st["updated_at"] = _now_iso()
    save_state(st)


def partition_square_posts_by_known(
    posts: List[Dict[str, Any]],
    known: Optional[set[str]] = None,
) -> tuple[List[Dict[str, Any]], int]:
    known_set = known if known is not None else known_square_content_ids()
    new_rows: List[Dict[str, Any]] = []
    skipped = 0
    for p in posts or []:
        if not isinstance(p, dict):
            continue
        cid = post_content_id(p)
        if cid and cid in known_set:
            skipped += 1
            continue
        new_rows.append(p)
    return new_rows, skipped


def post_content_id(post: Dict[str, Any]) -> str:
    cid = str(post.get("content_id") or "").strip()
    if cid.isdigit():
        return cid
    href = str(post.get("href") or "")
    m = re.search(r"/square/(?:post|video|article)/(\d+)", href, re.I)
    if m and m.group(1).isdigit():
        return m.group(1)
    m2 = re.search(r"[?&]contentId=(\d+)", href, re.I)
    if m2 and m2.group(1).isdigit():
        return m2.group(1)
    return ""


def canonical_square_post_href(post: Dict[str, Any], *, locale: str = "zh-CN") -> str:
    cid = post_content_id(post)
    if cid:
        return f"https://www.binance.com/{locale}/square/post/{cid}"
    return str(post.get("href") or "").strip().split("#")[0]


_TIME_LABEL_RE = re.compile(
    r"(刚刚|昨天|"
    r"\d+\s*分钟(?:前)?|\d+\s*小时(?:前)?|\d+\s*天(?:前)?|"
    r"\d{4}\s*年?\s*\d{1,2}\s*月\s*\d{1,2}\s*日?|"
    r"\d{1,2}\s*月\s*\d{1,2}\s*日|"
    r"\d+\s*(?:minutes?|hours?|days?)\s*ago)",
    re.I,
)


def sanitize_time_label(label: str) -> str:
    """从 DOM 文本中抽出时间片段，避免把点赞/评论数等当成时间。"""
    text = re.sub(r"\s+", " ", str(label or "").strip())
    if not text:
        return ""
    if re.search(r"(点赞|评论|转发|收藏|views?|阅读|万|k\b|K\b)", text, re.I):
        m = _TIME_LABEL_RE.search(text)
        return m.group(0).strip() if m else ""
    if len(text) > 40:
        m = _TIME_LABEL_RE.search(text)
        return m.group(0).strip() if m else text[:32]
    m = _TIME_LABEL_RE.search(text)
    if m:
        return m.group(0).strip()
    if _TIME_LABEL_RE.fullmatch(text):
        return text
    return text if len(text) <= 24 and not re.search(r"\d{2,}", text.replace(" ", "")) else ""


def _time_meta_score(post: Dict[str, Any]) -> int:
    iso = _parse_iso_time(str(post.get("published_iso") or ""))
    label = sanitize_time_label(str(post.get("time_label") or ""))
    score = 0
    if iso:
        score += 4
    if label:
        score += 2
    if label and _TIME_LABEL_RE.search(label):
        score += 1
    return score


def _pick_better_time_fields(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    """合并两条记录时保留更可靠的时间字段，避免重抓覆盖正确时间。"""
    if _time_meta_score(src) > _time_meta_score(dst):
        for field in ("published_iso", "time_label"):
            if src.get(field):
                dst[field] = src[field]
        return
    for field in ("published_iso", "time_label"):
        if not dst.get(field) and src.get(field):
            dst[field] = src[field]


def merge_square_post_times_from_prior(
    prior: List[Dict[str, Any]], rows: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """重扫时沿用已入库帖的发布时间，防止相对时间被刷成「刚刚」。"""
    by_cid: Dict[str, Dict[str, Any]] = {}
    for p in prior or []:
        if not isinstance(p, dict):
            continue
        cid = post_content_id(p)
        if cid:
            by_cid[cid] = p
    out: List[Dict[str, Any]] = []
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        p = dict(raw)
        cid = post_content_id(p)
        old = by_cid.get(cid) if cid else None
        if old:
            _pick_better_time_fields(p, old)
        tl = sanitize_time_label(str(p.get("time_label") or ""))
        if tl:
            p["time_label"] = tl
        elif p.get("time_label"):
            p.pop("time_label", None)
        out.append(p)
    return out


def merge_square_posts(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按 square/post/{contentId} 去重，合并媒体与正文。"""
    by: Dict[str, Dict[str, Any]] = {}
    for raw in posts or []:
        if not isinstance(raw, dict):
            continue
        p = dict(raw)
        cid = post_content_id(p)
        if cid:
            p["content_id"] = cid
            p["href"] = canonical_square_post_href(p)
        key = f"id:{cid}" if cid else f"href:{str(p.get('href') or '').split('#')[0]}"
        if not key or key == "href:":
            continue
        if key not in by:
            tl = sanitize_time_label(str(p.get("time_label") or ""))
            if tl:
                p["time_label"] = tl
            elif "time_label" in p:
                p.pop("time_label", None)
            by[key] = p
            continue
        o = by[key]
        if len(str(p.get("raw") or "")) > len(str(o.get("raw") or "")):
            o["raw"] = p.get("raw")
            o["title"] = p.get("title") or o.get("title")
        _pick_better_time_fields(o, p)
        for field in ("profile_name", "profile_id"):
            if not o.get(field) and p.get(field):
                o[field] = p[field]
        imgs = list(
            dict.fromkeys(
                [str(x) for x in (o.get("image_urls") or []) if str(x).strip()]
                + [str(x) for x in (p.get("image_urls") or []) if str(x).strip()]
            )
        )[:24]
        o["image_urls"] = imgs
        if str(p.get("video_url") or "").strip() and not str(o.get("video_url") or "").strip():
            o["video_url"] = p.get("video_url")
        if str(p.get("replay_url") or "").strip() and not str(o.get("replay_url") or "").strip():
            o["replay_url"] = p.get("replay_url")
        if str(p.get("live_content_id") or "").strip() and not str(o.get("live_content_id") or "").strip():
            o["live_content_id"] = p.get("live_content_id")
        o["is_pinned"] = bool(o.get("is_pinned")) or bool(p.get("is_pinned"))
    return list(by.values())


def _parse_iso_time(iso: str) -> Optional[datetime]:
    raw = (iso or "").strip()
    if not raw:
        return None
    try:
        s = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _parse_time_label(label: str, *, now: Optional[datetime] = None) -> Optional[datetime]:
    text = sanitize_time_label(str(label or "").strip())
    if not text:
        return None
    if re.search(r"(点赞|评论|转发|收藏|万\s*$|\d+\.\d+k)", text, re.I):
        return None
    now = now or datetime.now(timezone.utc)
    if "刚刚" in text:
        return now
    m = re.search(r"(\d+)\s*分钟", text)
    if m:
        return now - timedelta(minutes=int(m.group(1)))
    m = re.search(r"(\d+)\s*小时", text)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    m = re.search(r"(\d+)\s*天", text)
    if m:
        return now - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\s*days?\s*ago", text, re.I)
    if m:
        return now - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\s*hours?\s*ago", text, re.I)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    if "昨天" in text:
        return now - timedelta(days=1)
    return _parse_cn_month_day(text, now=now)


def save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(state or {})
    payload["updated_at"] = _now_iso()
    with _LOCK:
        STATE_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def parse_post_time(post: Dict[str, Any]) -> Optional[datetime]:
    now = datetime.now(timezone.utc)
    label = sanitize_time_label(str(post.get("time_label") or post.get("time") or ""))
    dt_label = _parse_time_label(label, now=now) if label else None
    dt_iso = _parse_iso_time(str(post.get("published_iso") or ""))
    if dt_iso and dt_iso > now + timedelta(hours=2):
        dt_iso = None
    if dt_label and dt_iso:
        # 有 ISO 时优先 ISO（来自 time[datetime]），相对文案仅作辅助
        if dt_iso >= now - timedelta(days=400):
            if dt_label > now + timedelta(minutes=5):
                return dt_iso
            if abs((dt_iso - dt_label).total_seconds()) > 86400 * 3:
                return dt_iso if dt_iso <= now else dt_label
            return dt_iso
        return dt_label or dt_iso
    return dt_iso or dt_label


def _parse_cn_month_day(label: str, *, now: datetime) -> Optional[datetime]:
    tz_cn = timezone(timedelta(hours=8))
    m = re.search(r"(\d{4})\s*年?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", label)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m2 = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", label)
        if not m2:
            return None
        y = now.astimezone(tz_cn).year
        mo, d = int(m2.group(1)), int(m2.group(2))
    try:
        dt_local = datetime(y, mo, d, tzinfo=tz_cn)
    except ValueError:
        return None
    dt = dt_local.astimezone(timezone.utc)
    if dt > now + timedelta(days=1):
        try:
            dt = datetime(y - 1, mo, d, tzinfo=tz_cn).astimezone(timezone.utc)
        except ValueError:
            return None
    return dt


def filter_by_backfill_range(posts: List[Dict[str, Any]], range_key: str) -> List[Dict[str, Any]]:
    from signals.backfill_range import normalize_backfill_range, resolve_backfill_since

    key = normalize_backfill_range(range_key)
    since, _ = resolve_backfill_since(key)
    cutoff = since.astimezone(timezone.utc)
    span_days = max(1, int((datetime.now(timezone.utc) - cutoff).total_seconds() // 86400) + 1)
    grace = timedelta(days=min(3, max(1, span_days // 5)))
    soft_cutoff = cutoff - grace
    out: List[Dict[str, Any]] = []
    for p in posts:
        dt = parse_post_time(p)
        pinned = bool(p.get("is_pinned"))
        if pinned:
            if dt is None or dt < soft_cutoff:
                continue
            out.append(p)
            continue
        if dt is None or dt >= soft_cutoff:
            out.append(p)
    return out


def resolve_binance_time_filter(
    *,
    backfill_range: Optional[str] = None,
    cutoff_hours: Optional[float] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """返回 filter_by_backfill_range 或 filter_by_cutoff 所需参数。"""
    c = cfg or load_config()
    rk = str(backfill_range if backfill_range is not None else c.get("backfill_range") or "").strip()
    if rk:
        from signals.backfill_range import normalize_backfill_range

        key = normalize_backfill_range(rk)
        return {"mode": "range", "backfill_range": key}
    try:
        hours = float(
            cutoff_hours
            if cutoff_hours is not None
            else c.get("cutoff_hours")
            if c.get("cutoff_hours") is not None
            else 24
        )
    except (TypeError, ValueError):
        hours = 24.0
    return {"mode": "hours", "cutoff_hours": hours}


def apply_binance_time_filter(
    posts: List[Dict[str, Any]],
    *,
    backfill_range: Optional[str] = None,
    cutoff_hours: Optional[float] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    spec = resolve_binance_time_filter(
        backfill_range=backfill_range, cutoff_hours=cutoff_hours, cfg=cfg
    )
    if spec.get("mode") == "range":
        return filter_by_backfill_range(posts, str(spec.get("backfill_range") or "last_7d"))
    return filter_by_cutoff(posts, float(spec.get("cutoff_hours") or 24))


def filter_by_cutoff(posts: List[Dict[str, Any]], hours: float) -> List[Dict[str, Any]]:
    if hours <= 0:
        return list(posts)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    out: List[Dict[str, Any]] = []
    for p in posts:
        dt = parse_post_time(p)
        pinned = bool(p.get("is_pinned"))
        if pinned:
            if dt is None or dt < cutoff:
                continue
            out.append(p)
            continue
        if dt is None or dt >= cutoff:
            out.append(p)
    return out
