# coding=utf-8
"""task-os live_watch 的信号 / 发布 / VPN 条目整形。

只消费已有数据源里的字段。算不出的段落写成「不可用」，不补数字。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from public.publish_log import sanitize_message, sanitize_url  # noqa: E402
from scripts import daily_cdp_and_signals_report as dcdr  # noqa: E402
from signals.labels import direction_cn, is_trade_signal, normalize_direction  # noqa: E402

TZ = dcdr.HKT
CANON_SITES = ("ChatGPT", "YouTube", "X", "币安广场")
_SITE_ALIASES = {
    "chatgpt": "ChatGPT",
    "openai": "ChatGPT",
    "chat.openai.com": "ChatGPT",
    "youtube": "YouTube",
    "youtu.be": "YouTube",
    "yt": "YouTube",
    "x": "X",
    "twitter": "X",
    "x.com": "X",
    "币安广场": "币安广场",
    "币安": "币安广场",
    "binance": "币安广场",
    "binance_square": "币安广场",
    "binance-square": "币安广场",
    "square": "币安广场",
}
_DISCONNECT_KINDS = {
    "disconnect",
    "down",
    "offline",
    "fail",
    "failure",
    "timeout",
    "high_latency",
    "unstable",
    "断开",
    "掉线",
    "超时",
    "高延迟",
}
_SWITCH_KINDS = {"switch", "rotate", "failover", "handoff", "切换", "轮换", "换节点"}
_RESTART_KINDS = {"restart", "relaunch", "app_restart", "重启", "重启应用"}
_SITE_KINDS = {"site", "site_check", "probe", "block", "blocked", "屏蔽", "站点"}
_ROLLUP_KINDS = {"daily", "summary", "rollup", "day"}
_EVENT_LIST_KEYS = (
    "events",
    "history",
    "log",
    "timeline",
    "probes",
    "checks",
    "site_checks",
    "switches",
    "rotations",
    "disconnects",
)
_SECRET_KEY = ("token", "secret", "password", "passwd", "cookie", "authorization", "api_key", "apikey")


def _local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def _hm_range(start: datetime, end: datetime) -> str:
    a, b = _local(start), _local(end)
    if a.date() == b.date():
        return f"{a:%H:%M}–{b:%H:%M}"
    return f"{a:%m-%d %H:%M}–{b:%m-%d %H:%M}"


def _stamp(dt: datetime) -> str:
    return _local(dt).strftime("%Y-%m-%d %H:%M")


def _hm(dt: datetime) -> str:
    return _local(dt).strftime("%H:%M")


def _one_line(text: Any, limit: int = 80) -> str:
    s = str(text or "").replace("\n", " ").replace("\r", " ").strip()
    s = " ".join(s.split())
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value in (0, 1, 0.0, 1.0):
            return bool(value)
        return None
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("1", "true", "yes", "ok", "up", "正常", "通"):
            return True
        if s in ("0", "false", "no", "down", "fail", "异常", "不通", "屏蔽"):
            return False
    return None


def _first(raw: Dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in raw and raw.get(key) not in (None, ""):
            if _secret_key(key):
                continue
            return raw.get(key)
    return None


def _secret_key(key: str) -> bool:
    low = key.lower().replace("-", "_")
    return any(part in low for part in _SECRET_KEY)


def _fmt_minutes(minutes: float) -> str:
    if abs(minutes - round(minutes)) < 0.05:
        return str(int(round(minutes)))
    return f"{minutes:.1f}"


def _minutes_from_sec(seconds: float) -> float:
    return round(seconds / 60.0, 1)


def _reason_label(reason: str) -> str:
    return {"timeout": "超时", "high_latency": "高延迟", "other": "其他"}.get(reason, "其他")


def _site_label(ok: Optional[bool]) -> str:
    if ok is True:
        return "通"
    if ok is False:
        return "不通"
    return "未探测"


def index_display_names(raw_channels: Dict[str, Any], profiles: Sequence[Any]) -> Dict[str, str]:
    """全部账号的展示名（含非重点），供汇总里写「禹柔」这类名字。"""
    names: Dict[str, str] = {}
    channels = raw_channels if isinstance(raw_channels, dict) else {}
    for handle, row in channels.items():
        if not isinstance(row, dict):
            continue
        disp = str(row.get("channelName") or row.get("name") or handle).strip()
        keys = {str(handle).strip().lower()}
        for alias in row.get("aliases") or []:
            a = str(alias).strip().lower()
            if a:
                keys.add(a)
        for key in keys:
            if key and disp:
                names[f"x:{key}"] = disp
    for prof in profiles or []:
        if not isinstance(prof, dict):
            continue
        pid = str(prof.get("id") or prof.get("name") or "").strip().lower()
        disp = str(prof.get("name") or pid).strip()
        pids = {pid} if pid else set()
        nm = str(prof.get("name") or "").strip().lower()
        if nm:
            pids.add(nm)
        for alias in prof.get("aliases") or []:
            a = str(alias).strip().lower()
            if a:
                pids.add(a)
        for p in pids:
            if p and disp:
                names[f"bs:{p}"] = disp
    return names


def _account_label(card: Dict[str, Any], handle: str, profile: str, names: Dict[str, str]) -> str:
    extra = card.get("extra") if isinstance(card.get("extra"), dict) else {}
    channel = extra.get("channel") if isinstance(extra.get("channel"), dict) else {}
    if not channel and isinstance(card.get("channel"), dict):
        channel = card.get("channel") or {}
    cname = str(channel.get("channelName") or channel.get("name") or "").strip()
    mapped = (
        names.get(f"x:{handle}")
        or names.get(f"bs:{profile}")
        or names.get(f"bs:{handle}")
        or ""
    )
    author = str(card.get("author") or "").strip().lstrip("@")
    disp = cname or mapped
    ident = handle or profile
    if disp and ident and disp.lower() != ident.lower():
        return f"{disp}（{ident}）"
    if disp:
        return disp
    if author and ident and author.lower() != ident.lower():
        return f"{author}（{ident}）"
    return ident or author or "未知"


def _signal_view(card: Dict[str, Any]) -> Tuple[str, str, str, bool]:
    sm = str(card.get("source_mode") or "").strip().lower()
    handle = str(card.get("user_handle") or "").strip().lower()
    extra = card.get("extra") if isinstance(card.get("extra"), dict) else {}
    profile = str(extra.get("profile_id") or extra.get("square_profile") or handle).lower()
    modes = card.get("source_modes") or []
    is_bs = sm == "binance_square" or "binance_square" in modes or str(card.get("list_id") or "").startswith(
        "binance:"
    )
    is_x = (not is_bs) and sm in ("", "x", "twitter", "list_realtime")
    if is_x:
        label = "推特"
    elif is_bs:
        label = "币安广场"
    else:
        label = sm or "信号"
    sig = card.get("signal") if isinstance(card.get("signal"), dict) else {}
    return label, handle, profile, is_trade_signal(sig)


def collect_signals(
    db_path: Path,
    start: datetime,
    end: datetime,
    tw_imp: Set[str],
    sq_imp: Set[str],
    names: Dict[str, str],
    *,
    slot: int,
) -> List[Dict[str, Any]]:
    """每个档位一条信号汇总。筛选仍是重点账号或交易信号。"""
    window = _hm_range(start, end)
    item_id = f"sig:summary:{slot}:{_local(end).date().isoformat()}"
    ts = _local(end).isoformat(timespec="seconds")
    cards, err = dcdr.load_cards_from_db(db_path)
    if err:
        return [
            {
                "id": item_id,
                "category": "signal",
                "ts": ts,
                "title": f"信号汇总 · {window} · 读取失败",
                "body": err,
                "meta": {
                    "count": None,
                    "window_start": _local(start).isoformat(timespec="seconds"),
                    "window_end": ts,
                    "items": [],
                    "level": "error",
                    "error": err,
                },
            }
        ]

    rows: List[Tuple[datetime, Dict[str, Any]]] = []
    for card in cards:
        created = dcdr.parse_datetime(card.get("created_at"))
        updated = dcdr.card_updated_dt(card)
        if not dcdr.in_window(updated, start, end) and not dcdr.in_window(created, start, end):
            continue
        label, handle, profile, trade = _signal_view(card)
        is_x = label == "推特"
        is_bs = label == "币安广场"
        important = (is_x and handle in tw_imp) or (is_bs and profile in sq_imp)
        if not important and not trade:
            continue
        sig = card.get("signal") if isinstance(card.get("signal"), dict) else {}
        direction = direction_cn(normalize_direction(str(sig.get("direction") or "")))
        summary = _one_line(sig.get("summary") or card.get("text") or "")
        if not summary:
            summary = "（无摘要）"
        extra = card.get("extra") if isinstance(card.get("extra"), dict) else {}
        url = str(card.get("url") or extra.get("url") or "").strip()
        when = created or updated or end
        rows.append(
            (
                _local(when),
                {
                    "source": label,
                    "account": _account_label(card, handle, profile, names),
                    "direction": direction,
                    "summary": summary,
                    "url": url,
                    "ts": _local(when).isoformat(timespec="seconds"),
                },
            )
        )
    rows.sort(key=lambda pair: pair[0])
    items = [row for _, row in rows]
    if not items:
        body = "本时段无信号"
    else:
        lines: List[str] = []
        for row in items:
            lines.append(
                f"{row['ts'][11:16]} {row['source']} · {row['account']} · {row['direction']} · {row['summary']}"
            )
            if row["url"]:
                lines.append(row["url"])
        body = "\n".join(lines)
    return [
        {
            "id": item_id,
            "category": "signal",
            "ts": ts,
            "title": f"信号汇总 · {window} · {len(items)} 条",
            "body": body,
            "meta": {
                "count": len(items),
                "window_start": _local(start).isoformat(timespec="seconds"),
                "window_end": ts,
                "items": items,
            },
        }
    ]


def _publish_log_days(log_dir: Path, start: datetime, end: datetime) -> Tuple[List[Path], List[Path]]:
    present: List[Path] = []
    missing: List[Path] = []
    for day in dcdr.dates_touching_window(start, end):
        path = log_dir / f"publish_{day.isoformat()}.log"
        if path.is_file():
            present.append(path)
        else:
            missing.append(path)
    return present, missing


def _read_publish_history(
    db_path: Path, start: datetime, end: datetime
) -> Tuple[List[Dict[str, Any]], str, str]:
    if not db_path.is_file():
        return [], "missing", ""
    try:
        uri = f"file:{db_path}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM publish_history").fetchall()
    except Exception as exc:  # noqa: BLE001
        return [], "error", str(exc)
    kept: List[Dict[str, Any]] = []
    for row in rows:
        raw = dict(row)
        if str(raw.get("entry_kind") or "") == "draft":
            continue
        if str(raw.get("status") or "").strip().lower() == "draft":
            continue
        dt = dcdr.parse_datetime(raw.get("created_at"))
        if not dcdr.in_window(dt, start, end):
            continue
        raw["_dt"] = dt
        kept.append(raw)
    return kept, "ok", ""


def _loads_list(raw: Any) -> List[Any]:
    if isinstance(raw, list):
        return raw
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _blank_publish(dt: Optional[datetime], end: datetime) -> Dict[str, Any]:
    when = dt or end
    return {
        "platform": "",
        "name": "",
        "ok": False,
        "error": "",
        "title": "",
        "url": "",
        "job_id": "",
        "dt": when,
        "time": _local(when).isoformat(timespec="seconds"),
        "aggregate_success": None,
        "aggregate_fail": None,
    }


def _fill_publish(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    for key in ("platform", "name", "title", "url", "job_id"):
        if not dst.get(key) and src.get(key):
            dst[key] = src[key]
    if src.get("error") and not dst.get("error"):
        dst["error"] = src["error"]
    # 日志里的失败不要被历史库里缺 error 的成功盖掉。
    if dst.get("ok") and not src.get("ok") and src.get("error"):
        dst["ok"] = False
        dst["error"] = src.get("error") or dst.get("error")
    elif not dst.get("ok") and src.get("ok") and not dst.get("error"):
        dst["ok"] = True


def _close_publish(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    da, db = a.get("dt"), b.get("dt")
    if not isinstance(da, datetime) or not isinstance(db, datetime):
        return False
    return abs((_local(da) - _local(db)).total_seconds()) <= 180


def _same_platform(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    pa = str(a.get("platform") or "").strip().lower()
    pb = str(b.get("platform") or "").strip().lower()
    if pa and pb:
        return pa == pb
    na = str(a.get("name") or "").strip().lower()
    nb = str(b.get("name") or "").strip().lower()
    return bool(na and na == nb)


def _same_publish(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    if a.get("aggregate_success") is not None or b.get("aggregate_success") is not None:
        return False
    if not _same_platform(a, b):
        return False
    ja, jb = str(a.get("job_id") or ""), str(b.get("job_id") or "")
    if ja and jb:
        return ja == jb
    return _close_publish(a, b)


def _merge_publish_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    for row in rows:
        placed = False
        for prev in merged:
            if _same_publish(prev, row):
                _fill_publish(prev, row)
                placed = True
                break
        if not placed:
            merged.append(row)
    merged.sort(key=lambda row: _local(row["dt"]) if isinstance(row.get("dt"), datetime) else _local(datetime.now(TZ)))
    return merged


def _fail_text(rec: Dict[str, Any]) -> str:
    cat = str(rec.get("failure_category") or "").strip()
    msg = sanitize_message(rec.get("message") or rec.get("error") or "")
    if cat and msg:
        return f"{cat}: {msg}"
    return msg or cat


def _items_from_logs(records: Sequence[Dict[str, Any]], end: datetime) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    items: List[Dict[str, Any]] = []
    run_ends: List[Dict[str, Any]] = []
    for rec in records:
        ev = str(rec.get("event") or "")
        dt = dcdr.parse_datetime(rec.get("ts")) or end
        job = str(rec.get("job_id") or "")
        if ev == "platform_ok":
            row = _blank_publish(dt, end)
            row.update(
                {
                    "platform": str(rec.get("platform") or ""),
                    "name": str(rec.get("platform_name") or rec.get("platform") or "未命名平台"),
                    "ok": True,
                    "error": "",
                    "url": sanitize_url(rec.get("post_url") or rec.get("url") or ""),
                    "job_id": job,
                }
            )
            items.append(row)
        elif ev == "platform_fail":
            row = _blank_publish(dt, end)
            row.update(
                {
                    "platform": str(rec.get("platform") or ""),
                    "name": str(rec.get("platform_name") or rec.get("platform") or "未命名平台"),
                    "ok": False,
                    "error": _fail_text(rec),
                    "url": sanitize_url(rec.get("post_url") or rec.get("last_url") or ""),
                    "job_id": job,
                }
            )
            items.append(row)
        elif ev == "cdp_connect_fail":
            row = _blank_publish(dt, end)
            row.update(
                {
                    "platform": "cdp",
                    "name": "CDP 连接",
                    "ok": False,
                    "error": _fail_text(rec) or "CDP 连接失败",
                    "job_id": job,
                }
            )
            items.append(row)
        elif ev == "run_end":
            run_ends.append(rec)
    return items, run_ends


def _items_from_history(
    rows: Sequence[Dict[str, Any]],
    log_jobs: Set[str],
    log_items: List[Dict[str, Any]],
    end: datetime,
) -> List[Dict[str, Any]]:
    extra: List[Dict[str, Any]] = []
    for raw in rows:
        job = str(raw.get("job_id") or "")
        title = sanitize_message(raw.get("title") or "", max_len=120)
        dt = raw.get("_dt") if isinstance(raw.get("_dt"), datetime) else dcdr.parse_datetime(raw.get("created_at"))
        results = [r for r in _loads_list(raw.get("results_json")) if isinstance(r, dict)]
        if job and job in log_jobs:
            for item in log_items:
                if item.get("job_id") == job and title and not item.get("title"):
                    item["title"] = title
            continue
        if results:
            for result in results:
                row = _blank_publish(dt, end)
                ok = _coerce_bool(result.get("success"))
                if ok is None:
                    ok = _coerce_bool(result.get("ok"))
                row.update(
                    {
                        "platform": str(result.get("platform") or ""),
                        "name": str(
                            result.get("name")
                            or result.get("platform_name")
                            or result.get("platform")
                            or "未命名平台"
                        ),
                        "ok": bool(ok),
                        "error": "" if ok else sanitize_message(result.get("error") or result.get("message") or ""),
                        "title": title,
                        "url": sanitize_url(result.get("url") or result.get("post_url") or ""),
                        "job_id": job,
                    }
                )
                extra.append(row)
            continue
        success = _as_int(raw.get("success_count"))
        total = _as_int(raw.get("total_count"))
        if success is None and total is None:
            continue
        success = 0 if success is None else success
        total = success if total is None else total
        fail = max(0, total - success)
        if total <= 0 and success <= 0:
            continue
        platforms = [str(p) for p in _loads_list(raw.get("platforms_json")) if str(p).strip()]
        message = sanitize_message(raw.get("message") or "")
        if platforms and fail == 0:
            for pid in platforms:
                row = _blank_publish(dt, end)
                row.update(
                    {
                        "platform": pid,
                        "name": pid,
                        "ok": True,
                        "title": title,
                        "job_id": job,
                    }
                )
                extra.append(row)
            continue
        if len(platforms) == 1 and total == 1:
            row = _blank_publish(dt, end)
            row.update(
                {
                    "platform": platforms[0],
                    "name": platforms[0],
                    "ok": fail == 0 and success > 0,
                    "error": "" if fail == 0 else (message or "发布失败"),
                    "title": title,
                    "job_id": job,
                }
            )
            extra.append(row)
            continue
        name = "、".join(platforms) if platforms else "本次发布"
        row = _blank_publish(dt, end)
        detail = message or "日志没有逐平台结果"
        row.update(
            {
                "platform": "",
                "name": name,
                "ok": fail == 0 and success > 0,
                "error": "" if fail == 0 else f"失败 {fail}/{total}。{detail}",
                "title": title,
                "job_id": job,
                "aggregate_success": success,
                "aggregate_fail": fail,
            }
        )
        extra.append(row)
    return extra


def _items_from_run_ends(
    run_ends: Sequence[Dict[str, Any]],
    used_jobs: Set[str],
    end: datetime,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rec in run_ends:
        job = str(rec.get("job_id") or "")
        if job and job in used_jobs:
            continue
        success = _as_int(rec.get("success_count"))
        total = _as_int(rec.get("total"))
        if success is None or total is None or total <= 0:
            continue
        fail = max(0, total - success)
        dt = dcdr.parse_datetime(rec.get("ts")) or end
        row = _blank_publish(dt, end)
        row.update(
            {
                "name": "本轮发布",
                "ok": fail == 0 and success > 0,
                "error": "" if fail == 0 else f"失败 {fail}/{total}。日志没有逐平台结果",
                "job_id": job,
                "aggregate_success": success,
                "aggregate_fail": fail,
            }
        )
        out.append(row)
        if job:
            used_jobs.add(job)
    return out


def _publish_counts(items: Sequence[Dict[str, Any]]) -> Tuple[int, int]:
    success = 0
    fail = 0
    for item in items:
        if item.get("aggregate_success") is not None:
            success += int(item.get("aggregate_success") or 0)
            fail += int(item.get("aggregate_fail") or 0)
            continue
        if item.get("ok"):
            success += 1
        else:
            fail += 1
    return success, fail


def _publish_body_lines(items: Sequence[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for idx, item in enumerate(items, 1):
        state = "成功" if item.get("ok") and not item.get("aggregate_fail") else "失败"
        if item.get("aggregate_success") is not None and int(item.get("aggregate_fail") or 0) > 0:
            state = "失败"
        title = str(item.get("title") or "").strip() or "（日志无标题）"
        url = str(item.get("url") or "").strip()
        link = url or "（无链接）"
        reason = str(item.get("error") or "").strip()
        head = f"{idx}. {item.get('name') or '未命名平台'} · {state} · 标题「{title}」 · {link}"
        lines.append(head)
        extra = f"   时间 {_hm(item['dt']) if isinstance(item.get('dt'), datetime) else item.get('time', '')}"
        if state == "失败":
            extra += f" · 原因 {reason or '（日志未写原因）'}"
        lines.append(extra)
    return lines


def collect_publish(
    log_dir: Path,
    history_db: Path,
    start: datetime,
    end: datetime,
    *,
    slot: int,
) -> List[Dict[str, Any]]:
    """每个档位一条发布汇总。日志缺失时改查 publish_history，仍没有则明确写缺失。"""
    window = _hm_range(start, end)
    day = _local(end).date().isoformat()
    item_id = f"pub:summary:{slot}:{day}"
    ts = _local(end).isoformat(timespec="seconds")
    records, gaps, _paths = dcdr.load_publish_records(log_dir, _local(end).date(), start, end)
    present, missing = _publish_log_days(log_dir, start, end)
    log_items, run_ends = _items_from_logs(records, end)
    log_jobs = {str(it.get("job_id") or "") for it in log_items if it.get("job_id")}
    history_rows, history_status, history_error = _read_publish_history(history_db, start, end)
    hist_items = _items_from_history(history_rows, log_jobs, log_items, end)
    used_jobs = set(log_jobs) | {str(it.get("job_id") or "") for it in hist_items if it.get("job_id")}
    end_items = _items_from_run_ends(run_ends, used_jobs, end)
    items = _merge_publish_rows([*log_items, *hist_items, *end_items])
    success, fail = _publish_counts(items)
    meta_items = [
        {
            "name": str(it.get("name") or ""),
            "ok": bool(it.get("ok")) and not int(it.get("aggregate_fail") or 0),
            "error": "" if it.get("ok") and not it.get("aggregate_fail") else str(it.get("error") or ""),
            "time": str(it.get("time") or ""),
            "title": str(it.get("title") or ""),
            "url": str(it.get("url") or ""),
        }
        for it in items
    ]
    notes: List[str] = []
    bad = [g for g in gaps if "无法解析" in g]
    if bad:
        notes.append(bad[0])
    window_line = f"窗口: {_stamp(start)}–{_hm(end)}（Asia/Shanghai）"
    if items:
        title = f"发布 · 成功 {success} / 失败 {fail}"
        body_parts = [window_line, *_publish_body_lines(items)]
        if missing and history_status == "ok":
            names = "、".join(p.name for p in missing)
            body_parts.append(f"另：发布日志文件不存在（{names}），以上来自已读到的日志与 publish_history.db。")
        if history_status == "error":
            body_parts.append(f"publish_history.db 读取失败: {history_error}")
        if notes:
            body_parts.extend(notes)
        status = "records"
        body = "\n".join(body_parts)
    else:
        log_names = "、".join(p.name for p in [*present, *missing]) or "publish_YYYY-MM-DD.log"
        history_line = {
            "ok": "publish_history.db 已读，该窗口没有发布记录",
            "missing": "publish_history.db 不存在",
            "error": f"publish_history.db 读取失败: {history_error}",
        }[history_status]
        if not present and history_status != "ok":
            title = "发布 · 发布日志缺失"
            status = "log_missing"
            body = "\n".join(
                [
                    "发布日志缺失。",
                    window_line,
                    f"发布日志文件不存在: {log_names}",
                    history_line + "。",
                    "没有其他可靠发布数据源，不能判断成功或失败，不记为成功。",
                    *notes,
                ]
            )
        else:
            title = "发布 · 当日无发布记录"
            status = "none"
            if not present:
                src = f"发布日志文件不存在: {log_names}。已改查 publish_history.db，该窗口没有发布记录。"
            elif history_status == "missing":
                src = f"已读取 {log_names}，窗口内没有平台发布。publish_history.db 不存在。"
            elif history_status == "error":
                src = f"已读取 {log_names}，窗口内没有平台发布。{history_line}，因此只能确认日志里没有，历史库未能核对。"
            else:
                src = f"已读取 {log_names} 和 publish_history.db，窗口内没有平台发布。"
            body = "\n".join(["当日无发布记录。", window_line, src, *notes])
    return [
        {
            "id": item_id,
            "category": "publish",
            "ts": ts,
            "title": title,
            "body": body.strip(),
            "meta": {
                "success_count": success,
                "fail_count": fail,
                "items": meta_items,
                "window_start": _local(start).isoformat(timespec="seconds"),
                "window_end": ts,
                "status": status,
            },
        }
    ]


def _kind_of(raw: Dict[str, Any]) -> str:
    return str(_first(raw, ("event", "type", "kind", "action")) or "").strip()


def _event_ts(raw: Dict[str, Any]) -> Optional[datetime]:
    return dcdr.parse_datetime(_first(raw, ("ts", "time", "at", "timestamp", "checked_at")))


def _duration_sec(raw: Dict[str, Any]) -> Optional[float]:
    for key in ("duration_sec", "duration_s", "seconds", "elapsed_sec", "unstable_seconds"):
        num = _as_float(raw.get(key))
        if num is not None and num >= 0:
            return num
    for key in ("duration_minutes", "unstable_minutes", "unstable_min"):
        num = _as_float(raw.get(key))
        if num is not None and num >= 0 and _kind_of(raw).lower() not in _ROLLUP_KINDS:
            if _is_rollup(raw):
                return None
            return num * 60.0
    ms = _as_float(raw.get("duration_ms"))
    if ms is not None and ms >= 0:
        return ms / 1000.0
    start = dcdr.parse_datetime(_first(raw, ("down_at", "start", "from_ts")))
    finish = dcdr.parse_datetime(_first(raw, ("up_at", "end", "to_ts")))
    if start and finish and finish >= start:
        return (finish - start).total_seconds()
    return None


def _canon_site(name: str) -> Optional[str]:
    key = str(name or "").strip()
    if not key:
        return None
    if key in CANON_SITES:
        return key
    return _SITE_ALIASES.get(key.lower())


def _parse_sites(raw: Dict[str, Any]) -> Dict[str, Optional[bool]]:
    payload = raw.get("sites")
    if not isinstance(payload, dict):
        payload = raw.get("site_status")
    if not isinstance(payload, dict):
        return {}
    out: Dict[str, Optional[bool]] = {}
    for key, value in payload.items():
        canon = _canon_site(str(key))
        if not canon:
            continue
        if isinstance(value, dict):
            flag = _coerce_bool(_first(value, ("ok", "up", "success", "status")))
        else:
            flag = _coerce_bool(value)
        out[canon] = flag
    return out


def _is_rollup(raw: Dict[str, Any]) -> bool:
    kind = _kind_of(raw).lower()
    if kind in _ROLLUP_KINDS:
        return True
    if kind:
        return False
    has_counter = any(
        _as_int(raw.get(key)) is not None or _as_float(raw.get(key)) is not None
        for key in ("disconnects", "disconnect_count", "unstable_minutes", "unstable_min", "blocks", "block_count")
    )
    return has_counter and not any(k in raw for k in ("from_node", "to_node", "duration_sec", "sites"))


def _parse_rollup(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _is_rollup(raw):
        return None
    stamp = _first(raw, ("date", "day"))
    as_of = dcdr.parse_datetime(_first(raw, ("as_of", "until", "end", "ts", "time")))
    day: Optional[date] = None
    if stamp:
        text = str(stamp).strip()
        try:
            day = date.fromisoformat(text[:10])
        except ValueError:
            parsed = dcdr.parse_datetime(text)
            day = _local(parsed).date() if parsed else None
    elif as_of:
        day = _local(as_of).date()
    if day is None:
        return None
    switches = raw.get("switches")
    switch_success = _as_int(raw.get("switch_success"))
    if switch_success is None and not isinstance(switches, (list, dict)):
        switch_success = _as_int(switches)
    return {
        "date": day,
        "disconnects": _as_int(_first(raw, ("disconnects", "disconnect_count"))),
        "unstable_minutes": _as_float(_first(raw, ("unstable_minutes", "unstable_min"))),
        "blocks": _as_int(_first(raw, ("blocks", "block_count"))),
        "switch_success": switch_success,
        "switched_clash": _coerce_bool(raw.get("switched_clash")),
        "restarted_app": _coerce_bool(_first(raw, ("restarted_app", "restart_app", "app_restart"))),
        "as_of": as_of,
    }


def _disconnect_reason(raw: Dict[str, Any], kind: str) -> str:
    blob = " ".join(
        str(raw.get(key) or "")
        for key in ("reason", "cause", "failure", "error", "message")
        if not _secret_key(key)
    ).lower()
    kind_l = kind.lower()
    if kind_l in ("timeout", "超时") or "timeout" in blob or "超时" in blob:
        return "timeout"
    if kind_l in ("high_latency", "高延迟") or "latency" in blob or "高延迟" in blob or "延迟" in blob:
        return "high_latency"
    return "other"


def _parse_event(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if _is_rollup(raw):
        return None
    kind = _kind_of(raw)
    kind_l = kind.lower()
    sites = _parse_sites(raw)
    from_node = str(_first(raw, ("from_node", "from")) or "")
    to_node = str(_first(raw, ("to_node", "to")) or "")
    is_disconnect = kind_l in _DISCONNECT_KINDS
    is_switch = kind_l in _SWITCH_KINDS or bool(from_node and to_node)
    is_restart = kind_l in _RESTART_KINDS or _coerce_bool(raw.get("restarted_app")) is True
    is_site = bool(sites) or kind_l in _SITE_KINDS
    if not any((is_disconnect, is_switch, is_restart, is_site, kind_l in ("health", "status", "check", "heartbeat"))):
        if _event_ts(raw) is None and not _first(raw, ("node", "current_node", "client", "ip")):
            return None
    text_client = str(_first(raw, ("to_client", "client", "current_client", "app")) or "")
    clash = _coerce_bool(raw.get("switched_clash"))
    if clash is None:
        clash = _coerce_bool(raw.get("clash")) if isinstance(raw.get("clash"), bool) else None
    if clash is None and is_switch and "clash" in text_client.lower():
        clash = True
    ok = _coerce_bool(raw.get("ok"))
    if ok is None:
        ok = _coerce_bool(raw.get("success"))
    return {
        "ts": _event_ts(raw),
        "is_disconnect": is_disconnect,
        "reason": _disconnect_reason(raw, kind) if is_disconnect else "",
        "duration_sec": _duration_sec(raw) if is_disconnect else None,
        "is_switch": is_switch,
        "switch_ok": ok if is_switch else None,
        "switched_clash": clash if is_switch or clash is not None else None,
        "is_restart": is_restart,
        "node": str(_first(raw, ("node", "current_node", "node_name")) or ""),
        "from_node": from_node,
        "to_node": to_node,
        "client": text_client,
        "ip": str(_first(raw, ("ip", "exit_ip", "current_ip", "public_ip")) or ""),
        "sites": sites,
        "keys": sorted(str(k) for k in raw.keys() if not _secret_key(str(k))),
    }


def _walk_objects(obj: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(obj, list):
        for el in obj:
            if isinstance(el, dict):
                yield el
        return
    if not isinstance(obj, dict):
        return
    yielded = False
    for key in _EVENT_LIST_KEYS:
        val = obj.get(key)
        if isinstance(val, list):
            yielded = True
            for el in val:
                if isinstance(el, dict):
                    yield el
    daily = obj.get("daily")
    if isinstance(daily, dict):
        yielded = True
        for key, val in daily.items():
            if isinstance(val, dict):
                yield {**val, "date": val.get("date") or key}
    for key in ("days", "today"):
        val = obj.get(key)
        if isinstance(val, list):
            yielded = True
            for el in val:
                if isinstance(el, dict):
                    yield el
        elif isinstance(val, dict):
            yielded = True
            yield val
    if not yielded or any(k in obj for k in ("event", "type", "kind", "ok", "disconnects", "date")):
        yield obj


def _consume_raw(raw: Dict[str, Any], events: List[Dict[str, Any]], rollups: List[Dict[str, Any]], keys: Set[str]) -> None:
    for key in raw.keys():
        if not _secret_key(str(key)):
            keys.add(str(key))
    rollup = _parse_rollup(raw)
    if rollup:
        rollups.append(rollup)
        return
    event = _parse_event(raw)
    if event:
        events.append(event)


def _read_vpn_file(path: Path, events: List[Dict[str, Any]], rollups: List[Dict[str, Any]], keys: Set[str], notes: List[str]) -> None:
    try:
        if path.stat().st_size > 8_000_000:
            notes.append(f"{path.name} 超过 8MB，未整文件读取")
            return
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        notes.append(f"无法读取 {path.name}: {exc}")
        return
    parsed = 0
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            notes.append(f"{path.name} 不是合法 JSON")
            return
        for raw in _walk_objects(data):
            before = len(events) + len(rollups)
            _consume_raw(raw, events, rollups, keys)
            parsed += len(events) + len(rollups) - before
        if parsed == 0:
            notes.append(f"{path.name} 没有识别成断开/切换/站点/按日汇总")
        return
    for line in text.splitlines():
        piece = line.strip()
        if not piece or piece[0] not in "{[":
            continue
        try:
            data = json.loads(piece)
        except json.JSONDecodeError:
            continue
        for raw in _walk_objects(data):
            before = len(events) + len(rollups)
            _consume_raw(raw, events, rollups, keys)
            parsed += len(events) + len(rollups) - before
    if parsed == 0:
        notes.append(f"{path.name} 没有可识别的 JSON 事件")


def _load_vpn_sources(
    state: Optional[Dict[str, Any]],
    state_path: Path,
    log_dir: Optional[Path],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str], List[str], List[str]]:
    events: List[Dict[str, Any]] = []
    rollups: List[Dict[str, Any]] = []
    keys: Set[str] = set()
    notes: List[str] = []
    files: List[str] = []
    if isinstance(state, dict):
        files.append(state_path.name or "state.json")
        for raw in _walk_objects(state):
            _consume_raw(raw, events, rollups, keys)
    directory = log_dir if log_dir is not None else state_path.parent
    if not directory.is_dir():
        notes.append("日志目录不存在")
        return events, rollups, notes, sorted(keys), files
    try:
        state_resolved = state_path.resolve() if state_path.exists() else None
    except OSError:
        state_resolved = None
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".json", ".jsonl", ".log"}:
            continue
        try:
            if state_resolved is not None and path.resolve() == state_resolved:
                continue
        except OSError:
            continue
        files.append(path.name)
        _read_vpn_file(path, events, rollups, keys, notes)
    return events, rollups, notes, sorted(keys), files


def _health_view(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    health: Dict[str, Any] = {}
    if isinstance(state, dict):
        nested = state.get("last_health")
        if isinstance(nested, dict):
            health = nested
        else:
            health = state
    ok = _coerce_bool(health.get("ok")) if "ok" in health else None
    if ok is None and isinstance(state, dict) and state is not health and "ok" in state:
        ok = _coerce_bool(state.get("ok"))
    owner = str(_first(health, ("owner",)) or (state or {}).get("owner") or "").strip()
    node = str(_first(health, ("node", "current_node", "node_name")) or "")
    client = str(_first(health, ("client", "current_client", "app")) or "")
    ip = str(_first(health, ("ip", "exit_ip", "current_ip", "public_ip")) or "")
    sites = _parse_sites(health)
    fail_since = ""
    if isinstance(state, dict) and state.get("fail_since"):
        fail_since = str(state.get("fail_since"))
    report = ""
    if isinstance(state, dict):
        for key in ("report", "summary_text"):
            if isinstance(state.get(key), str) and not _secret_key(key):
                report = _one_line(state.get(key), 800)
                low = report.lower()
                if any(word in low for word in ("bearer ", "token=", "password", "api_key", "cookie=")):
                    report = ""
                break
    return {
        "ok": ok,
        "owner": owner,
        "node": node,
        "client": client,
        "ip": ip,
        "sites": sites,
        "fail_since": fail_since,
        "report": report,
        "health_keys": sorted(str(k) for k in health.keys() if not _secret_key(str(k))),
        "state_keys": sorted(str(k) for k in (state or {}).keys() if not _secret_key(str(k)))
        if isinstance(state, dict)
        else [],
    }


def _between(events: Sequence[Dict[str, Any]], start: datetime, end: datetime) -> List[Dict[str, Any]]:
    out = []
    for ev in events:
        ts = ev.get("ts")
        if isinstance(ts, datetime) and dcdr.in_window(ts, start, end):
            out.append(ev)
    return out


def _day_bounds(day: date, end: datetime) -> Tuple[datetime, datetime]:
    start = datetime.combine(day, time(0, 0), tzinfo=TZ)
    length = _local(end) - datetime.combine(_local(end).date(), time(0, 0), tzinfo=TZ)
    if length.total_seconds() <= 0:
        length = timedelta(days=1)
    return start, start + length


def _rollup_for(rollups: Sequence[Dict[str, Any]], day: date) -> Optional[Dict[str, Any]]:
    found = [row for row in rollups if row.get("date") == day]
    return found[-1] if found else None


def _window_metrics(
    events: Sequence[Dict[str, Any]],
    rollups: Sequence[Dict[str, Any]],
    start: datetime,
    end: datetime,
) -> Dict[str, Any]:
    scoped = _between(events, start, end)
    disconnects = [ev for ev in scoped if ev.get("is_disconnect")]
    site_events = [ev for ev in scoped if ev.get("sites")]
    switches = [ev for ev in scoped if ev.get("is_switch")]
    restarts = [ev for ev in scoped if ev.get("is_restart")]
    rollup = _rollup_for(rollups, _local(start).date())
    basis = "none"
    count: Optional[int] = None
    minutes: Optional[float] = None
    blocks: Optional[int] = None
    if disconnects:
        basis = "events"
        count = len(disconnects)
        known = [float(ev["duration_sec"]) for ev in disconnects if ev.get("duration_sec") is not None]
        minutes = _minutes_from_sec(sum(known)) if known else None
    elif rollup and rollup.get("disconnects") is not None:
        basis = "rollup"
        count = rollup.get("disconnects")
        if rollup.get("unstable_minutes") is not None:
            minutes = round(float(rollup["unstable_minutes"]), 1)
    if site_events:
        blocks = sum(1 for ev in site_events if any(flag is False for flag in (ev.get("sites") or {}).values()))
        if basis == "none":
            basis = "events"
    elif rollup and rollup.get("blocks") is not None:
        blocks = rollup.get("blocks")
        if basis == "none":
            basis = "rollup"
    covered = bool(scoped or rollup)
    return {
        "basis": basis if covered else "none",
        "covered": covered,
        "disconnects": count,
        "unstable_minutes": minutes,
        "blocks": blocks,
        "disconnect_events": disconnects,
        "site_events": site_events,
        "switches": switches,
        "restarts": restarts,
        "scoped": scoped,
        "rollup": rollup,
    }


def _latest_with(events: Sequence[Dict[str, Any]], end: datetime, field: str) -> str:
    best = ""
    best_ts: Optional[datetime] = None
    for ev in events:
        ts = ev.get("ts")
        if not isinstance(ts, datetime) or _local(ts) > _local(end):
            continue
        value = str(ev.get(field) or "")
        if field == "node":
            value = str(ev.get("to_node") or ev.get("node") or "")
        if not value:
            continue
        if best_ts is None or _local(ts) >= best_ts:
            best_ts = _local(ts)
            best = value
    return best


def _latest_sites(events: Sequence[Dict[str, Any]], end: datetime) -> Dict[str, Optional[bool]]:
    best: Dict[str, Optional[bool]] = {}
    best_ts: Optional[datetime] = None
    for ev in events:
        ts = ev.get("ts")
        sites = ev.get("sites") or {}
        if not sites or not isinstance(ts, datetime) or _local(ts) > _local(end):
            continue
        if best_ts is None or _local(ts) >= best_ts:
            best_ts = _local(ts)
            best = dict(sites)
    return best


def _periods(events: Sequence[Dict[str, Any]], end: datetime) -> List[Tuple[datetime, datetime, str]]:
    points: List[Tuple[datetime, str]] = []
    for ev in events:
        ts = ev.get("ts")
        if not isinstance(ts, datetime):
            continue
        node = str(ev.get("to_node") or ev.get("node") or "")
        if node:
            points.append((_local(ts), node))
    points.sort(key=lambda pair: pair[0])
    if not points:
        return []
    segments: List[Tuple[datetime, datetime, str]] = []
    cur_start, cur_node = points[0]
    for ts, node in points[1:]:
        if node != cur_node:
            segments.append((cur_start, ts, cur_node))
            cur_start, cur_node = ts, node
    segments.append((cur_start, _local(end), cur_node))
    return segments


def _block_stories(site_events: Sequence[Dict[str, Any]], switches: Sequence[Dict[str, Any]]) -> List[str]:
    ordered_sites = sorted(
        [ev for ev in site_events if isinstance(ev.get("ts"), datetime)],
        key=lambda ev: _local(ev["ts"]),
    )
    ordered_switches = sorted(
        [ev for ev in switches if isinstance(ev.get("ts"), datetime)],
        key=lambda ev: _local(ev["ts"]),
    )
    lines: List[str] = []
    for idx, ev in enumerate(ordered_sites):
        blocked = [name for name, flag in (ev.get("sites") or {}).items() if flag is False]
        if not blocked:
            continue
        node = str(ev.get("node") or ev.get("from_node") or "未知节点")
        ts = _local(ev["ts"])
        nxt = ordered_sites[idx + 1] if idx + 1 < len(ordered_sites) else None
        nxt_ts = _local(nxt["ts"]) if nxt and isinstance(nxt.get("ts"), datetime) else None
        moved = None
        for sw in ordered_switches:
            sw_ts = _local(sw["ts"])
            if sw_ts < ts:
                continue
            if nxt_ts is not None and sw_ts > nxt_ts:
                break
            moved = sw
            break
        piece = f"{_hm(ts)} 节点 {node} 挡住 {'、'.join(blocked)}"
        if moved:
            target = str(moved.get("to_node") or moved.get("node") or "未知节点")
            piece += f"；{_hm(moved['ts'])} 换到 {target}"
        else:
            piece += "；未见换节点"
        if nxt and nxt_ts is not None:
            flags = [nxt.get("sites", {}).get(name) for name in CANON_SITES]
            if flags and all(flag is True for flag in flags):
                piece += f"；{_hm(nxt_ts)} 换后四站都通"
            elif any(flag is False for flag in flags):
                still = [name for name in CANON_SITES if nxt.get("sites", {}).get(name) is False]
                piece += f"；换后仍不通: {'、'.join(still) or '见探测'}"
            else:
                piece += "；换后是否四站都通: 不可用（探测未覆盖四站）"
        else:
            piece += "；换后是否四站都通: 不可用（没有换后的探测）"
        lines.append(piece)
    return lines


def _stability_sentence(today: Dict[str, Any], yday: Dict[str, Any]) -> str:
    if today.get("basis") != "events" or yday.get("basis") != "events":
        return "今日与昨日不是同一口径的同时段统计，不能直接说更稳。"
    td, yd = today.get("disconnects"), yday.get("disconnects")
    tu, yu = today.get("unstable_minutes"), yday.get("unstable_minutes")
    tb, yb = today.get("blocks"), yday.get("blocks")
    if td is None or yd is None:
        return "断开次数不全，不能比较是否更稳。"
    fewer = td < yd
    more = td > yd
    if tu is None or yu is None:
        if fewer:
            return "断开更少，但不稳定时长缺失，不能说更稳。"
        if more:
            return "断开更多，但不稳定时长缺失，不能说更稳。"
        return "断开次数相同，不稳定时长缺失，不能说更稳。"
    shorter = tu < yu
    longer = tu > yu
    block_worse = tb is not None and yb is not None and tb > yb
    block_better = tb is not None and yb is not None and tb < yb
    if td == yd and tu == yu and not block_worse and not block_better:
        return "与昨日同时段持平。"
    core_better = (fewer or td == yd) and (shorter or tu == yu) and (fewer or shorter)
    core_worse = (more or td == yd) and (longer or tu == yu) and (more or longer)
    if core_better and block_worse:
        return "断开和不稳定时长更好，但屏蔽更多，不能简单说更稳。"
    if core_worse and block_better:
        return "断开和不稳定时长更差，但屏蔽更少，不能简单说更不稳。"
    if core_better and not block_worse:
        return "今日截至该时刻比昨日同时段更稳。"
    if core_worse and not block_better:
        return "今日截至该时刻比昨日同时段更不稳。"
    return "断开次数、不稳定时长或屏蔽次数一好一坏，不能简单说更稳。"


def _snapshot_line(client: str, node: str, ip: str) -> str:
    if not any((client, node, ip)):
        return "不可用（无客户端、节点、出口 IP）"
    return " · ".join(
        [
            client or "客户端不可用",
            node or "节点不可用",
            f"出口 IP {ip}" if ip else "出口 IP 不可用",
        ]
    )


def collect_vpn(
    state_path: Path,
    slot: int,
    end: datetime,
    log_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """12/20 点一条 VPN。能从 state.json 和同目录事件日志算出的才写数字。"""
    end_l = _local(end)
    day = end_l.date().isoformat()
    ts = end_l.isoformat(timespec="seconds")
    state: Optional[Dict[str, Any]] = None
    state_problem = ""
    if not state_path.is_file():
        state_problem = "missing"
    else:
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            state_problem = str(exc)
            loaded = None
        if isinstance(loaded, dict):
            state = loaded
        elif loaded is not None and not state_problem:
            state_problem = "state.json 不是对象"
    events, rollups, notes, seen_keys, files = _load_vpn_sources(state, state_path, log_dir)
    if state is None and not events and not rollups:
        if state_problem == "missing":
            body = "\n".join(
                [
                    f"截止: {_stamp(end_l)}（Asia/Shanghai）",
                    "VPN Guard 状态文件不存在。",
                    "断开次数、不稳定时长、当前节点、关键站点、切换记录、近几日对比: 不可用。",
                    *notes,
                ]
            )
            return [
                {
                    "id": f"vpn:missing:{slot}:{day}",
                    "category": "vpn",
                    "ts": ts,
                    "title": "VPN Guard 状态文件不存在",
                    "body": body,
                    "meta": {"level": "warn", "ok": None, "unavailable": ["状态文件"]},
                }
            ]
        return [
            {
                "id": f"vpn:parse:{slot}:{day}",
                "category": "vpn",
                "ts": ts,
                "title": "VPN 状态解析失败",
                "body": state_problem or "state.json 无法解析",
                "meta": {"level": "error"},
            }
        ]

    if state_problem == "missing":
        notes.append("state.json 不存在，以下仅来自事件日志")
    elif state_problem and state is None:
        notes.append(state_problem)
    health = _health_view(state)
    today_start, today_end = _day_bounds(end_l.date(), end_l)
    today = _window_metrics(events, rollups, today_start, today_end)
    ok = health["ok"]
    owner = health["owner"] or "?"
    client = health["client"] or _latest_with(events, end_l, "client")
    node = health["node"] or _latest_with(events, end_l, "node")
    ip = health["ip"] or _latest_with(events, end_l, "ip")
    sites = dict(health["sites"]) or _latest_sites(events, end_l)
    disconnects = today["disconnects"]
    minutes = today["unstable_minutes"]
    title_bits = ["VPN Guard", "OK" if ok is True else "FAULT" if ok is False else "UNKNOWN", owner]
    if disconnects is not None and minutes is not None:
        title_bits.append(f"断开{disconnects}次 / 不稳定{_fmt_minutes(minutes)}分钟")
    elif disconnects is not None:
        title_bits.append(f"断开{disconnects}次")
    unavailable: List[str] = []
    lines: List[str] = [f"截止: {_stamp(end_l)}（Asia/Shanghai）"]
    if ok is True:
        health_line = "健康: 正常"
    elif ok is False:
        health_line = "健康: 异常"
    else:
        health_line = "健康: 不可用（状态里没有 ok）"
        unavailable.append("健康")
    if health["fail_since"]:
        health_line += f"；fail_since: {health['fail_since']}"
    lines.append(health_line)
    lines.append(f"出口归属: {owner}" if health["owner"] else "出口归属: 不可用")
    if not health["owner"]:
        unavailable.append("出口归属")

    if disconnects is None and minutes is None:
        lines.append("断开次数与不稳定合计时长: 不可用（状态和日志里都没有可计算的断开记录）")
        unavailable.append("断开次数")
        unavailable.append("不稳定时长")
    else:
        how = "由事件计算" if today["basis"] == "events" else "采用守卫按日汇总"
        count_text = f"断开 {disconnects} 次" if disconnects is not None else "断开次数不可用"
        if minutes is not None:
            dur_text = f"不稳定合计 {_fmt_minutes(minutes)} 分钟"
        else:
            dur_text = "不稳定合计时长不可用（有断开记录但没有单次时长）"
            unavailable.append("不稳定时长")
        lines.append(f"断开次数与不稳定合计时长: {count_text}，{dur_text}（今日 00:00 至截止，{how}）")
        if disconnects is None:
            unavailable.append("断开次数")

    lines.append(f"当前客户端与节点: {_snapshot_line(client, node, ip)}")
    if not client:
        unavailable.append("当前客户端")
    if not node:
        unavailable.append("当前节点")
    if not ip:
        unavailable.append("当前出口 IP")

    if sites:
        site_bits = [f"{name} {_site_label(sites.get(name))}" for name in CANON_SITES]
        lines.append("关键站点: " + "；".join(site_bits))
        if any(name not in sites for name in CANON_SITES):
            unavailable.append("部分关键站点")
    else:
        lines.append("关键站点: 不可用（无 ChatGPT / YouTube / X / 币安广场 探测）")
        unavailable.append("关键站点")

    disc_events = today["disconnect_events"]
    if disc_events:
        buckets = {"timeout": 0, "high_latency": 0, "other": 0}
        for ev in disc_events:
            buckets[ev.get("reason") or "other"] = buckets.get(ev.get("reason") or "other", 0) + 1
        lines.append(
            "断开分布: "
            + "，".join(f"{_reason_label(key)} {buckets[key]} 次" for key in ("timeout", "high_latency", "other"))
        )
        timed = [ev for ev in disc_events if ev.get("duration_sec") is not None and isinstance(ev.get("ts"), datetime)]
        if timed:
            timed.sort(key=lambda ev: float(ev["duration_sec"]), reverse=True)
            longer = "；".join(
                f"{_hm(ev['ts'])} {_reason_label(ev.get('reason') or 'other')} {_fmt_minutes(_minutes_from_sec(float(ev['duration_sec'])))} 分钟"
                for ev in timed[:3]
            )
            lines.append(f"单次时长与较长的几次: {longer}")
        else:
            lines.append("单次时长: 不可用（断开事件没有时长）")
            unavailable.append("单次时长")
    else:
        lines.append("断开分布: 不可用")
        unavailable.append("断开分布")

    switches = today["switches"]
    restarts = today["restarts"]
    rollup = today["rollup"] if isinstance(today.get("rollup"), dict) else None
    saw_events = bool(today["scoped"])
    if switches or restarts or (rollup and rollup.get("switch_success") is not None):
        if switches:
            known_ok = [ev.get("switch_ok") for ev in switches if ev.get("switch_ok") is not None]
            success = sum(1 for flag in known_ok if flag is True)
            if known_ok and len(known_ok) == len(switches):
                success_text = f"成功 {success} 次"
            elif known_ok:
                success_text = f"标明成功 {success} 次，另有 {len(switches) - len(known_ok)} 次未写成败"
            else:
                success_text = f"记录到 {len(switches)} 次切换，未标明是否成功"
                unavailable.append("切换成败")
            clash_flags = [ev.get("switched_clash") for ev in switches]
            if any(flag is True for flag in clash_flags):
                clash_text = "是"
            elif clash_flags and all(flag is False for flag in clash_flags):
                clash_text = "否"
            else:
                clash_text = "日志未写"
                unavailable.append("是否切过 Clash")
        else:
            success_n = rollup.get("switch_success") if rollup else None
            success_text = f"成功 {success_n} 次（按日汇总，无逐次记录）" if success_n is not None else "不可用"
            clash_flag = rollup.get("switched_clash") if rollup else None
            clash_text = "是" if clash_flag is True else "否" if clash_flag is False else "日志未写"
        if restarts:
            restart_text = "是"
        elif saw_events:
            restart_text = "否"
        elif rollup and rollup.get("restarted_app") is not None:
            restart_text = "是" if rollup.get("restarted_app") else "否"
        else:
            restart_text = "不可用"
            unavailable.append("是否重启应用")
        lines.append(f"守卫轮换/切换: {success_text}；切过 Clash: {clash_text}；重启应用: {restart_text}")
        if switches and any(ev.get("switch_ok") is not None for ev in switches):
            switch_success: Optional[int] = sum(1 for ev in switches if ev.get("switch_ok") is True)
        elif switches:
            switch_success = None
        else:
            switch_success = (rollup or {}).get("switch_success")
        switch_meta = {
            "success": switch_success,
            "attempts": len(switches) if switches else None,
            "switched_clash": True
            if any(ev.get("switched_clash") is True for ev in switches)
            else False
            if switches and all(ev.get("switched_clash") is False for ev in switches)
            else (rollup or {}).get("switched_clash"),
            "restarted_app": True if restarts else False if saw_events else (rollup or {}).get("restarted_app"),
        }
    else:
        lines.append("守卫轮换/切换: 不可用（无轮换、切换或重启记录）")
        unavailable.append("守卫轮换")
        switch_meta = None

    periods = _periods(today["scoped"], end_l)
    if periods:
        bits = [f"{_hm(a)}–{_hm(b)} {name}" for a, b, name in periods]
        lines.append("主要在用时段与节点变迁: " + "；".join(bits))
    elif node:
        lines.append(f"主要在用时段与节点变迁: 不可用（只知道当前节点 {node}，没有变迁时间）")
        unavailable.append("节点变迁")
    else:
        lines.append("主要在用时段与节点变迁: 不可用")
        unavailable.append("节点变迁")

    stories = _block_stories(today["site_events"], today["switches"])
    if stories:
        shown = stories[:8]
        lines.append("站点屏蔽: " + " | ".join(shown))
        if len(stories) > 8:
            lines.append(f"其余 {len(stories) - 8} 次屏蔽未展开")
    elif today["blocks"]:
        lines.append(f"站点屏蔽: 汇总 {today['blocks']} 次，但没有哪一节点挡住哪一站的明细")
        unavailable.append("屏蔽明细")
    else:
        lines.append("站点屏蔽: 不可用")
        unavailable.append("站点屏蔽")

    compare_lines: List[str] = []
    yday_metrics: Optional[Dict[str, Any]] = None
    for offset in (3, 2, 1, 0):
        day_i = end_l.date() - timedelta(days=offset)
        start_i, end_i = _day_bounds(day_i, end_l)
        metrics = today if offset == 0 else _window_metrics(events, rollups, start_i, end_i)
        if offset == 1:
            yday_metrics = metrics
        if not metrics["covered"]:
            compare_lines.append(f"- {day_i.isoformat()} {_hm(start_i)}–{_hm(end_i)}：无记录")
            continue
        d_txt = f"断开 {metrics['disconnects']} 次" if metrics["disconnects"] is not None else "断开次数不可用"
        u_txt = (
            f"不稳定 {_fmt_minutes(metrics['unstable_minutes'])} 分钟"
            if metrics["unstable_minutes"] is not None
            else "不稳定时长不可用"
        )
        b_txt = f"屏蔽 {metrics['blocks']} 次" if metrics["blocks"] is not None else "屏蔽次数不可用"
        how = "事件" if metrics["basis"] == "events" else "按日汇总"
        compare_lines.append(f"- {day_i.isoformat()} {_hm(start_i)}–{_hm(end_i)}：{d_txt}，{u_txt}，{b_txt}（{how}）")
    if any(row["covered"] for row in (
        _window_metrics(events, rollups, *_day_bounds(end_l.date() - timedelta(days=n), end_l)) for n in (1, 2, 3)
    )) or today["covered"]:
        lines.append("近几日对比:")
        lines.extend(compare_lines)
        if yday_metrics and yday_metrics.get("covered") and today.get("covered"):
            lines.append(_stability_sentence(today, yday_metrics))
        elif yday_metrics and not yday_metrics.get("covered"):
            lines.append("昨日同时段无记录，不能比较是否更稳。")
            unavailable.append("近几日对比")
    else:
        lines.append("近几日对比: 不可用")
        unavailable.append("近几日对比")

    if seen_keys and not events and disconnects is None:
        lines.append("已读到字段但未识别成断开/切换/站点: " + "、".join(seen_keys[:24]))
    if health["report"] and len(unavailable) >= 4:
        lines.append("守卫原文（未再解析数字）: " + health["report"])
    if notes:
        lines.append("读取说明: " + "；".join(notes[:6]))
    if files:
        lines.append("数据来源: " + "、".join(dict.fromkeys(files)))

    site_status = {name: sites.get(name) if name in sites else None for name in CANON_SITES} if sites else None
    return [
        {
            "id": f"vpn:{slot}:{day}",
            "category": "vpn",
            "ts": ts,
            "title": " · ".join(title_bits),
            "body": "\n".join(lines),
            "meta": {
                "ok": ok,
                "owner": owner if health["owner"] else None,
                "disconnects": disconnects,
                "unstable_minutes": minutes,
                "current_client": client or None,
                "current_node": node or None,
                "current_ip": ip or None,
                "site_status": site_status,
                "switches": switch_meta,
                "unavailable": unavailable,
                "sources": list(dict.fromkeys(files)),
                "state_keys": health["state_keys"],
            },
        }
    ]
