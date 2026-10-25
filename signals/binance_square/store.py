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
        "seen_content_registry": {},
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
        "cycle_profile_ids": [],
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
        cyc = raw.get("cycle_profile_ids")
        if isinstance(cyc, list):
            cfg["cycle_profile_ids"] = [
                str(x).strip().lower() for x in cyc if str(x).strip()
            ]
    return cfg


def normalize_profile_id_list(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = re.split(r"[\s,]+", raw.strip())
        return [p.strip().lower() for p in parts if p.strip()]
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for x in raw:
        pid = str(x or "").strip().lower().lstrip("@")
        if pid:
            out.append(pid)
    return out


def cycle_profile_ids(cfg: Optional[Dict[str, Any]] = None) -> List[str]:
    """周期/后台抓取仅使用控制台勾选的博主 id。"""
    cfg = cfg or load_config()
    return normalize_profile_id_list(cfg.get("cycle_profile_ids"))


def save_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    payload = default_config()
    payload.update(cfg or {})
    payload["cycle_profile_ids"] = normalize_profile_id_list(payload.get("cycle_profile_ids"))
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
    if not isinstance(base.get("seen_content_registry"), dict):
        base["seen_content_registry"] = {}
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
    """已登记过的 Square contentId（兼容旧逻辑，含 registry 全量 key）。"""
    st = load_state()
    known: set[str] = set()
    reg = st.get("seen_content_registry")
    if isinstance(reg, dict):
        for cid in reg.keys():
            c = str(cid or "").strip()
            if c.isdigit():
                known.add(c)
    for raw in st.get("seen_content_ids") or []:
        cid = str(raw or "").strip()
        if cid.isdigit():
            known.add(cid)
    known |= _content_ids_from_hrefs(st.get("seen_hrefs") or [])
    return known


def square_content_ids_skip_recent(hours: float = 24.0) -> set[str]:
    """近 N 小时内已抓取过的 contentId（增量跳过 AI/详情，超时后可再处理）。"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1.0, float(hours or 24)))
    out: set[str] = set()
    st = load_state()
    reg = st.get("seen_content_registry")
    if isinstance(reg, dict):
        for cid, raw in reg.items():
            cid_s = str(cid or "").strip()
            if not cid_s.isdigit():
                continue
            dt = _parse_iso_time(str(raw or ""))
            if dt is not None and dt >= cutoff:
                out.add(cid_s)
    return out


def register_square_content_ids(ids: List[Any], *, posts: Optional[List[Dict[str, Any]]] = None) -> None:
    st = load_state()
    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    reg: Dict[str, str] = {}
    if isinstance(st.get("seen_content_registry"), dict):
        reg = {str(k): str(v) for k, v in st["seen_content_registry"].items() if str(k).strip()}
    seen: set[str] = set(reg.keys())
    for raw in st.get("seen_content_ids") or []:
        cid = str(raw or "").strip()
        if cid.isdigit():
            seen.add(cid)
    for raw in ids or []:
        cid = str(raw or "").strip()
        if cid.isdigit():
            seen.add(cid)
            reg[cid] = now_iso
    if posts:
        for p in posts:
            if not isinstance(p, dict):
                continue
            cid = post_content_id(p)
            if cid:
                seen.add(cid)
                reg[cid] = now_iso
            href = str(p.get("href") or "").strip()
            if href:
                hrefs = list(st.get("seen_hrefs") or [])
                if href not in hrefs:
                    hrefs.append(href)
                st["seen_hrefs"] = hrefs[-5000:]
    st["seen_content_ids"] = sorted(seen)[-8000:]
    if len(reg) > 8000:
        items = sorted(reg.items(), key=lambda x: x[1], reverse=True)[:8000]
        reg = dict(items)
    st["seen_content_registry"] = reg
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


def _square_post_time_rank(post: Dict[str, Any]) -> int:
    """列表 create-time 越完整分数越高，深滚合并时覆盖劣质时间。"""
    iso = str(post.get("published_iso") or "").strip()
    tl = str(post.get("time_label") or post.get("time") or "").strip()
    score = 0
    if iso:
        score += 8
        if _parse_iso_time(iso) is not None:
            score += 12
    if tl:
        score += 2
        if _extract_create_time_snippet(tl):
            score += 4
    return score


def _merge_square_post_time_fields(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    if _square_post_time_rank(src) > _square_post_time_rank(dst):
        if src.get("time_label"):
            dst["time_label"] = src["time_label"]
        if src.get("published_iso"):
            dst["published_iso"] = src["published_iso"]
        return
    if not dst.get("published_iso") and src.get("published_iso"):
        dst["published_iso"] = src["published_iso"]
    if not dst.get("time_label") and src.get("time_label"):
        dst["time_label"] = src["time_label"]


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
            by[key] = p
            continue
        o = by[key]
        if len(str(p.get("raw") or "")) > len(str(o.get("raw") or "")):
            o["raw"] = p.get("raw")
            o["title"] = p.get("title") or o.get("title")
        _merge_square_post_time_fields(o, p)
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
    if re.fullmatch(r"\d{10,13}", raw):
        try:
            n = int(raw)
            sec = n / 1000.0 if len(raw) >= 13 else float(n)
            return datetime.fromtimestamp(sec, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    try:
        s = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            # 币安 time[datetime] 多为北京时间无时区字段，勿当 UTC
            tz_cn = timezone(timedelta(hours=8))
            dt = dt.replace(tzinfo=tz_cn)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


_TIME_LABEL_HEAD_RE = re.compile(
    r"^(刚刚|昨天|今天|"
    r"\d+\s*(?:秒|分钟|小时|天)(?:前)?|"
    r"\d{1,2}\s*月\s*\d{1,2}\s*日|"
    r"\d{4}\s*年?\s*\d{1,2}\s*月\s*\d{1,2}\s*日|"
    r"\d+\s*(?:minutes?|hours?|days?)\s*ago|"
    r"\d{4}-\d{2}-\d{2})",
    re.I,
)


def _looks_like_time_label(text: str) -> bool:
    t = str(text or "").strip()
    if not t or len(t) > 56:
        return False
    return bool(_TIME_LABEL_HEAD_RE.match(t))


def _looks_like_relative_time_label(text: str) -> bool:
    t = str(text or "").strip()
    if not t:
        return False
    return bool(
        re.match(
            r"^(刚刚|昨天|今天|\d+\s*(?:秒|分钟|小时|天)(?:前)?|"
            r"\d+\s*(?:minutes?|hours?|days?)\s*ago)",
            t,
            re.I,
        )
    )


def _extract_create_time_snippet(text: str) -> str:
    """从 create-time 单元格文案中提取「12小时」「3天前」等，忽略作者名等前缀。"""
    t = str(text or "").strip()
    if not t:
        return ""
    if _looks_like_time_label(t):
        return t
    m = re.search(r"(刚刚|昨天|今天|\d+\s*(?:秒|分钟|小时|天)(?:前)?)", t)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"(\d{1,2}\s*月\s*\d{1,2}\s*日)", t)
    if m2:
        return m2.group(1).strip()
    m3 = re.search(r"(\d{4}-\d{2}-\d{2})", t)
    return m3.group(1).strip() if m3 else ""


def _parse_time_label(label: str, *, now: Optional[datetime] = None) -> Optional[datetime]:
    text = str(label or "").strip()
    if not text:
        return None
    now = now or datetime.now(timezone.utc)
    if "刚刚" in text:
        return now
    m = re.search(r"(\d+)\s*秒", text)
    if m:
        return now - timedelta(seconds=int(m.group(1)))
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
    dt_iso = _parse_iso_time(str(post.get("published_iso") or ""))
    label = str(post.get("time_label") or post.get("time") or "").strip()
    snippet = _extract_create_time_snippet(label)
    dt_label = _parse_time_label(snippet, now=now) if snippet else None
    if dt_label is None and _looks_like_time_label(label):
        dt_label = _parse_time_label(label, now=now)

    # create-time 上的相对时间（如「12小时」）优先于易错的 ISO/入库时间
    if dt_label is not None and snippet and _looks_like_relative_time_label(snippet):
        return dt_label
    if dt_iso is not None and dt_label is not None:
        if abs((dt_iso - dt_label).total_seconds()) <= 172800:
            return dt_iso
        if dt_iso > now + timedelta(hours=2):
            return dt_label
        if dt_iso >= now - timedelta(hours=3) and snippet:
            return dt_label
        return dt_iso
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


def backfill_soft_cutoff_utc(range_key: str) -> datetime:
    """与 filter_by_backfill_range 使用同一 soft 边界（含 grace），供深滚停滚判断。"""
    from signals.backfill_range import normalize_backfill_range, resolve_backfill_since

    key = normalize_backfill_range(range_key)
    since, _ = resolve_backfill_since(key)
    cutoff = since.astimezone(timezone.utc)
    span_days = max(1, int((datetime.now(timezone.utc) - cutoff).total_seconds() // 86400) + 1)
    grace = timedelta(days=min(3, max(1, span_days // 5)))
    return cutoff - grace


def backfill_soft_cutoff_from_time_spec(time_spec: Dict[str, Any]) -> Optional[datetime]:
    if time_spec.get("mode") != "range":
        return None
    rk = str(time_spec.get("backfill_range") or "last_7d")
    return backfill_soft_cutoff_utc(rk)


def filter_by_backfill_range(posts: List[Dict[str, Any]], range_key: str) -> List[Dict[str, Any]]:
    soft_cutoff = backfill_soft_cutoff_utc(range_key)
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
    if cutoff_hours is not None:
        try:
            hours = float(cutoff_hours)
            if hours > 0:
                return {"mode": "hours", "cutoff_hours": hours}
        except (TypeError, ValueError):
            pass
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


def _post_has_relative_time_hint(post: Dict[str, Any]) -> bool:
    label = str(post.get("time_label") or post.get("time") or "").strip()
    head = str(post.get("raw") or post.get("title") or "")[:120]
    for text in (label, head):
        if not text:
            continue
        if "刚刚" in text:
            return True
        if re.search(r"\d+\s*(?:秒|分钟|小时|天)(?:前)?", text):
            return True
        if re.search(r"\d+\s*(?:minutes?|hours?|days?)\s*ago", text, re.I):
            return True
    return False


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
        if dt is not None:
            if dt >= cutoff:
                out.append(p)
            continue
        if _post_has_relative_time_hint(p):
            out.append(p)
            continue
        # 时间未解析但确有帖文 id：仍纳入实时窗，避免「抓到了却进不了卡片」
        if post_content_id(p):
            out.append(p)
    return out
