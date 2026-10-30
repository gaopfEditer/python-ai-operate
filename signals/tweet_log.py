# coding=utf-8
"""列表信号终端可读摘要（作者 / 时间 / 正文预览 / 信号结论）。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def _load_beijing_tz():
    """Windows 常缺 IANA tzdata，ZoneInfo 会抛 ZoneInfoNotFoundError。"""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Asia/Shanghai")
    except Exception:
        pass
    try:
        import pytz

        return pytz.timezone("Asia/Shanghai")
    except Exception:
        return timezone(timedelta(hours=8))


BEIJING_TZ = _load_beijing_tz()

from signals.labels import direction_cn
from signals.store import parse_dt


def to_beijing(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BEIJING_TZ)


def fmt_beijing(dt: datetime) -> str:
    """北京时间展示：YYYY-MM-DD HH:MM:SS"""
    return to_beijing(dt).strftime("%Y-%m-%d %H:%M:%S")


def fmt_beijing_iso(dt: datetime) -> str:
    """Cards API signalAt：北京时间 ISO +08:00"""
    return to_beijing(dt).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def clip_text(text: str, n: int = 200) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip())
    if len(s) <= n:
        return s
    return s[:n].rstrip() + "…"


def fmt_post_time(created_raw: str = "", time_label: str = "", created: Optional[datetime] = None) -> str:
    if created is None:
        created = parse_dt(str(created_raw or ""))
    if created is not None:
        try:
            return fmt_beijing(created)
        except Exception:
            return created.isoformat()
    if time_label:
        return str(time_label)
    return (created_raw or "")[:32] or "未知"


_TWITTER_EN_REL = re.compile(
    r"^(\d+)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|"
    r"h|hr|hrs|hour|hours|d|day|days)\b",
    re.I,
)
_TWITTER_EN_AGO = re.compile(
    r"(\d+)\s*(second|seconds|minute|minutes|hour|hours|day|days)\s+ago",
    re.I,
)
_TWITTER_EN_MD = re.compile(
    r"^([A-Za-z]{3,9})\s+(\d{1,2})(?:\s*,\s*(\d{4}))?\b",
)


def tweet_id_to_post_datetime(tweet_id: str) -> Optional[datetime]:
    """X 推文 ID（Snowflake）→ UTC 发帖时间，DOM 无 time 时兜底。"""
    tid = str(tweet_id or "").strip()
    if not tid.isdigit():
        return None
    try:
        n = int(tid)
        ms = (n >> 22) + 1288834974657
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def parse_twitter_time_label(label: str, *, now: Optional[datetime] = None) -> Optional[datetime]:
    """解析 X 列表 time 文案（2h / Oct 24 / 3小时前 等），相对时间以 now 为锚。"""
    text = str(label or "").strip()
    if not text:
        return None
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    dt = parse_dt(text)
    if dt is not None:
        return dt

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

    m = _TWITTER_EN_REL.match(text)
    if m:
        n = int(m.group(1))
        u = m.group(2).lower()
        if u.startswith("s"):
            return now - timedelta(seconds=n)
        if u.startswith("m"):
            return now - timedelta(minutes=n)
        if u.startswith("h"):
            return now - timedelta(hours=n)
        return now - timedelta(days=n)

    m = _TWITTER_EN_AGO.search(text)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("second"):
            return now - timedelta(seconds=n)
        if unit.startswith("minute"):
            return now - timedelta(minutes=n)
        if unit.startswith("hour"):
            return now - timedelta(hours=n)
        return now - timedelta(days=n)

    m = _TWITTER_EN_MD.match(text)
    if m:
        mon_s, day_s, year_s = m.group(1), m.group(2), m.group(3)
        try:
            from calendar import month_abbr

            months = {abbr.lower(): i for i, abbr in enumerate(month_abbr) if abbr}
            mo = months.get(mon_s[:3].lower())
            if not mo:
                return None
            y = int(year_s) if year_s else now.astimezone(BEIJING_TZ).year
            d = int(day_s)
            dt_local = datetime(y, mo, d, tzinfo=BEIJING_TZ)
            return dt_local.astimezone(timezone.utc)
        except (ValueError, TypeError):
            return None

    m2 = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if m2:
        y = now.astimezone(BEIJING_TZ).year
        mo, d = int(m2.group(1)), int(m2.group(2))
        try:
            dt_local = datetime(y, mo, d, tzinfo=BEIJING_TZ)
            return dt_local.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def infer_tweet_post_datetime(
    *,
    created_raw: str = "",
    time_label: str = "",
    tweet_id: str = "",
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    """发帖时间：time[datetime] > 列表文案 > tweet_id，绝不用 parsed_at。"""
    dt = parse_dt(str(created_raw or "").strip())
    if dt is not None:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    dt = parse_twitter_time_label(str(time_label or ""), now=now)
    if dt is not None:
        return dt
    return tweet_id_to_post_datetime(tweet_id)


def tweet_created_at_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def normalize_tweet_item_times(it: Dict[str, Any], *, now: Optional[datetime] = None) -> Dict[str, Any]:
    """抓取结果补全 created_at（供历史/实时共用）。"""
    out = dict(it)
    tid = str(out.get("tweet_id") or "").strip()
    raw = str(out.get("created_at") or "").strip()
    label = str(out.get("time_label") or "").strip()
    if parse_dt(raw):
        return out
    dt = infer_tweet_post_datetime(created_raw=raw, time_label=label, tweet_id=tid, now=now)
    if dt is not None:
        out["created_at"] = tweet_created_at_iso(dt)
    return out


def resolve_display_time(
    created_raw: str = "",
    time_label: str = "",
    *,
    tweet_id: str = "",
    fallback_now: bool = False,
) -> str:
    """展示/推送用发帖时间（禁止 parsed_at / 抓取时间冒充发帖时间）。"""
    dt = infer_tweet_post_datetime(
        created_raw=created_raw,
        time_label=time_label,
        tweet_id=tweet_id,
    )
    if dt is not None:
        return fmt_beijing(dt)
    if time_label:
        return str(time_label).strip()
    raw = str(created_raw or "").strip()
    if raw:
        return raw[:32]
    if fallback_now:
        return fmt_beijing(datetime.now(timezone.utc))
    return "未知"


_TIME_PREFIX_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2}[^\]]*\]\s*")


def strip_time_prefix(body: str) -> str:
    """去掉正文开头的 [时间] 前缀。"""
    return _TIME_PREFIX_RE.sub("", (body or "").strip()).strip()


def with_time_prefix(body: str, time_s: str) -> str:
    """正文前加 [时间] 前缀（已有则不重复）。"""
    text = (body or "").strip()
    if _TIME_PREFIX_RE.match(text):
        return text
    prefix = f"[{time_s}]"
    return f"{prefix} {text}" if text else prefix


def fmt_tweet_line(it: Dict[str, Any], *, preview_n: int = 200) -> str:
    author = str(it.get("author") or "").strip() or "(未知作者)"
    text = str(it.get("text") or "").strip()
    preview = clip_text(text, preview_n) or (
        "（无文字，含图）" if it.get("images") else "（空）"
    )
    time_s = fmt_post_time(
        str(it.get("created_at") or ""),
        str(it.get("time_label") or ""),
    )
    return f"发帖人={author} | 发帖时间={time_s} | 正文={preview}"


def fmt_signal_line(signal: Dict[str, Any], *, time_s: str = "") -> str:
    has = bool(signal.get("has_trade_signal"))
    if not has:
        return f"是否交易信号=否" + (f" | 时间={time_s}" if time_s else "")
    coins = ",".join(str(c) for c in (signal.get("coins") or [])[:6]) or "-"
    direction = direction_cn(str(signal.get("direction") or "unknown"))
    entries = "/".join(str(x) for x in (signal.get("entries") or [])[:3])
    tps = "/".join(str(x) for x in (signal.get("take_profits") or [])[:3])
    sl = str(signal.get("stop_loss") or "")
    summary = clip_text(str(signal.get("summary") or ""), 80)
    parts = [
        "是否交易信号=是",
        f"币种={coins}",
        f"方向={direction}",
    ]
    if entries:
        parts.append(f"入场={entries}")
    if tps:
        parts.append(f"止盈={tps}")
    if sl:
        parts.append(f"止损={sl}")
    if summary:
        parts.append(f"摘要={summary}")
    if time_s:
        parts.append(f"时间={time_s}")
    return " | ".join(parts)


def fmt_item_summary_line(
    log: Dict[str, Any],
    *,
    index: int = 0,
    total: int = 0,
) -> str:
    """单条解析摘要（前端验证用一行）。"""
    idx = ""
    if index and total:
        idx = f"[{index}/{total}] "
    elif index:
        idx = f"[{index}] "
    author = str(log.get("author") or "").strip() or "(未知)"
    time_s = str(log.get("display_time") or "").strip()
    if not time_s or time_s == "未知":
        time_s = fmt_post_time(
            str(log.get("created_at") or ""),
            str(log.get("time_label") or ""),
        )
    preview = clip_text(str(log.get("preview") or ""), 80) or "（空）"
    if log.get("skipped"):
        flag = "跳过"
        coins_s = "-"
        dir_s = "-"
    elif log.get("has_trade_signal"):
        flag = "交易"
        coins_s = ",".join(str(c) for c in (log.get("coins") or [])[:6]) or "-"
        dir_s = direction_cn(str(log.get("direction") or "unknown"))
    else:
        flag = "非交易"
        coins_s = "-"
        dir_s = "-"
    result = str(log.get("result") or "").strip()
    cache = " · 缓存" if log.get("from_cache") else ""
    head = (
        f"{idx}{time_s} | {author} | {flag} | 币种={coins_s} | 方向={dir_s} | {preview}"
    )
    if result:
        return f"{head} → {result}{cache}"
    return head
