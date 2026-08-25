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


def resolve_display_time(
    created_raw: str = "",
    time_label: str = "",
    parsed_at: str = "",
    *,
    fallback_now: bool = True,
) -> str:
    """解析用于展示/推送的时间，保证尽量有值。"""
    t = fmt_post_time(created_raw, time_label)
    if t == "未知" and parsed_at:
        t = fmt_post_time(parsed_at, "")
    if t == "未知" and fallback_now:
        return fmt_beijing(datetime.now(timezone.utc))
    return t


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
