#!/usr/bin/env python3
# coding=utf-8
"""每日 CDP 发布统计 + 推特 / 币安广场实时卡片统计。

用法::

    .venv/bin/python scripts/daily_cdp_and_signals_report.py
    .venv/bin/python scripts/daily_cdp_and_signals_report.py --date 2026-11-12
    .venv/bin/python scripts/daily_cdp_and_signals_report.py --date 2026-11-12 \\
        --api-base http://127.0.0.1:8787
    .venv/bin/python scripts/daily_cdp_and_signals_report.py --hours 12

默认时区 Asia/Hong_Kong（UTC+8）。不传 --date / --hours 时取该时区的今天。
--hours N 统计最近 N 小时（[现在-N小时, 现在)），可跨自然日；与 --date 互斥。
只读本地日志 / SQLite，以及可选的本机 HTTP GET；不写业务数据、不重启服务。

过滤规则（与 signals.labels.is_trade_signal 一致，以卡片已解析的
signal.coins + signal.direction 为准，不做额外 NLP）：

  保留：至少一个币种 / 交易对，且方向为做多或做空。
        方向认可 long / short，以及中文 做多 / 做空 / 看多 / 看空 / 买入 / 卖出。
        一张卡提及多个币种时，只要「有币种 + 明确方向」即计 1 次。
  剔除：无币种、无明确多空（unknown / flat / watch / 中性 / 观望），或仅有其中一项。

示例：
  保留  coins=["BTC"], direction="long"     明确点名 BTC 做多
  剔除  coins=["BTC"], direction="unknown"  只提到币、没有明确方向（如行情分析）
  剔除  coins=[],      direction="long"     提到多单但未点名币种
  剔除  coins=[],      direction="unknown"  闲聊、无关帖

时间窗口：
  主统计 signals.{twitter,binance}.{raw,kept,dropped} 按贴文发布时间
  created_at_ts（与项目「卡片使用发布时间、非抓取时刻」一致）。
  同时给出 fetched 窗口：updated_at（缺则 parsed_at）落在当日的入库 / 更新数，
  对应「当天获取到的卡片」。
  无时区时间戳按 Asia/Hong_Kong 解释；带 Z 或显式偏移的按原时区转换后再比较。

CDP 发布：
  读取 output/publish_logs/publish_YYYY-MM-DD.log，并扫描相邻日文件，
  按记录 ts 是否落在当日窗口统计各平台 platform_ok / platform_fail 及失败原因。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def rel_to_root(path: Path, root: Path) -> str:
    """报告里只用仓库相对路径，避免写出本机用户目录名。"""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name

TZ_NAME = "Asia/Hong_Kong"
HKT = ZoneInfo(TZ_NAME)

# 与 signals.labels.DIRECTION_ALIASES / is_trade_signal 保持一致，
# 脚本本身不强制 import signals 包（避免无依赖环境拖入 yaml）。
DIRECTION_ALIASES = {
    "long": "long",
    "short": "short",
    "flat": "flat",
    "watch": "watch",
    "unknown": "unknown",
    "做多": "long",
    "做空": "short",
    "看多": "long",
    "看空": "short",
    "买入": "long",
    "卖出": "short",
    "中性": "flat",
    "观望": "watch",
}

FILTER_RULE = (
    "保留同时满足「signal.coins 至少一个币种/交易对」且"
    "「signal.direction 为做多或做空（long/short，或做多/做空/看多/看空/买入/卖出）」的卡片；"
    "多币种只要任一币种存在且方向明确即计 1 次。"
    "剔除无币种、无明确多空（unknown/flat/watch/中性/观望），或只具备其中一项的卡片。"
    "以已解析 signal 字段为准，不做额外 NLP。与 signals.labels.is_trade_signal 一致。"
)

FILTER_EXAMPLES = {
    "kept": [
        {"coins": ["BTC"], "direction": "long", "why": "点名 BTC 且明确做多"},
        {"coins": ["ETH", "SOL"], "direction": "做空", "why": "多币种 + 中文做空，计 1 次"},
    ],
    "dropped": [
        {"coins": ["BTC"], "direction": "unknown", "why": "只提到币、无明确方向"},
        {"coins": [], "direction": "long", "why": "有方向但未点名币种"},
        {"coins": [], "direction": "unknown", "why": "闲聊或无关帖"},
        {"coins": ["DOGE"], "direction": "watch", "why": "观望不算做多/做空"},
    ],
}


def today_hkt() -> date:
    return datetime.now(HKT).date()


def parse_date(raw: str) -> date:
    text = str(raw or "").strip()
    return date.fromisoformat(text)


def day_window(day: date) -> Tuple[datetime, datetime, int, int]:
    """返回 [start, end) 的 HKT 日窗及对应 unix 秒。"""
    start = datetime(day.year, day.month, day.day, tzinfo=HKT)
    end = start + timedelta(days=1)
    return start, end, int(start.timestamp()), int(end.timestamp())


def hours_window(hours: int, *, end: Optional[datetime] = None) -> Tuple[datetime, datetime, int, int]:
    """返回最近 N 小时的 [start, end) HKT 窗及对应 unix 秒。"""
    if hours <= 0:
        raise ValueError("hours 必须为正整数")
    finish = end.astimezone(HKT) if end is not None else datetime.now(HKT)
    start = finish - timedelta(hours=int(hours))
    return start, finish, int(start.timestamp()), int(finish.timestamp())


def dates_touching_window(start: datetime, end: datetime) -> List[date]:
    """窗口 [start, end) 覆盖到的 HKT 日历日。"""
    start_h = start.astimezone(HKT)
    end_h = end.astimezone(HKT)
    first = start_h.date()
    last = (end_h - timedelta(microseconds=1)).date() if end_h > start_h else first
    days: List[date] = []
    cur = first
    while cur <= last:
        days.append(cur)
        cur += timedelta(days=1)
    return days


def parse_datetime(raw: Any, *, naive_tz: ZoneInfo = HKT) -> Optional[datetime]:
    """解析时间。带 Z / 偏移按原时区；naive 按 naive_tz（默认 HKT）。"""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        dt = raw
        if dt.tzinfo is None:
            return dt.replace(tzinfo=naive_tz)
        return dt
    if isinstance(raw, (int, float)):
        ts = float(raw)
        # 毫秒时间戳
        if ts > 1e12:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=HKT)
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=naive_tz)
    return dt


def in_window(dt: Optional[datetime], start: datetime, end: datetime) -> bool:
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=HKT)
    return start <= dt.astimezone(HKT) < end


def normalize_direction(direction: str) -> str:
    raw = str(direction or "").strip()
    if not raw:
        return "unknown"
    if raw in DIRECTION_ALIASES:
        return DIRECTION_ALIASES[raw]
    key = raw.lower()
    if key in DIRECTION_ALIASES:
        return DIRECTION_ALIASES[key]
    return "unknown"


def is_directional_coin_signal(sig: Any) -> bool:
    """有币种 + 明确做多/做空。与 signals.labels.is_trade_signal 对齐。"""
    if not isinstance(sig, dict):
        return False
    coins = [str(c).strip() for c in (sig.get("coins") or []) if str(c).strip()]
    direction = normalize_direction(str(sig.get("direction") or ""))
    return bool(coins) and direction in ("long", "short")


def card_platform(card: Dict[str, Any]) -> str:
    lid = str(card.get("list_id") or "").strip()
    if lid.startswith("binance:") or lid == "binance:square":
        return "binance"
    mode = str(card.get("source_mode") or "").strip()
    modes = card.get("source_modes") if isinstance(card.get("source_modes"), list) else []
    if mode == "binance_square" or "binance_square" in modes:
        return "binance"
    return "twitter"


def _loads(raw: Any, default: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    text = str(raw or "").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def _handle(card: Dict[str, Any]) -> str:
    return str(card.get("user_handle") or card.get("author") or "").lstrip("@") or "?"


def empty_platform_stats() -> Dict[str, Any]:
    return {
        "raw": 0,
        "kept": 0,
        "dropped": 0,
        "by_handle": {},
        "kept_by_handle": {},
        "by_source": {},
        "examples_kept": [],
        "examples_dropped": [],
    }


def _bump(counter: Dict[str, int], key: str) -> None:
    k = key or "?"
    counter[k] = int(counter.get(k) or 0) + 1


def summarize_cards(cards: Sequence[Dict[str, Any]], *, example_limit: int = 5) -> Dict[str, Any]:
    out = {"twitter": empty_platform_stats(), "binance": empty_platform_stats()}
    for card in cards:
        plat = card_platform(card)
        if plat not in out:
            plat = "twitter"
        bucket = out[plat]
        sig = card.get("signal")
        if not isinstance(sig, dict):
            sig = _loads(card.get("signal_json"), {})
            if not isinstance(sig, dict):
                sig = {}
        handle = _handle(card)
        extra = card.get("extra") if isinstance(card.get("extra"), dict) else _loads(card.get("extra_json"), {})
        source = str(
            card.get("source_mode")
            or (extra.get("source_mode") if isinstance(extra, dict) else "")
            or ""
        )
        bucket["raw"] += 1
        _bump(bucket["by_handle"], handle)
        _bump(bucket["by_source"], source or "unknown")
        kept = is_directional_coin_signal(sig)
        sample = {
            "handle": handle,
            "coins": [str(c).strip() for c in (sig.get("coins") or []) if str(c).strip()],
            "direction": normalize_direction(str(sig.get("direction") or "")),
            "text": str(card.get("text") or "")[:160].replace("\n", " / "),
            "created_at": str(card.get("created_at") or ""),
            "updated_at": str(card.get("updated_at") or ""),
        }
        if kept:
            bucket["kept"] += 1
            _bump(bucket["kept_by_handle"], handle)
            if len(bucket["examples_kept"]) < example_limit:
                bucket["examples_kept"].append(sample)
        else:
            bucket["dropped"] += 1
            if len(bucket["examples_dropped"]) < example_limit:
                bucket["examples_dropped"].append(sample)
    return out


def card_updated_dt(card: Dict[str, Any]) -> Optional[datetime]:
    return parse_datetime(card.get("updated_at")) or parse_datetime(card.get("parsed_at"))


def load_cards_from_db(db_path: Path) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if not db_path.is_file():
        return [], f"cards.db 不存在: {db_path}"
    cards: List[Dict[str, Any]] = []
    try:
        uri = f"file:{db_path}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM signal_cards").fetchall()
        for row in rows:
            d = dict(row)
            d["signal"] = _loads(d.get("signal_json"), {})
            extra = _loads(d.get("extra_json"), {})
            d["extra"] = extra if isinstance(extra, dict) else {}
            if not d.get("source_mode"):
                d["source_mode"] = str((d["extra"] or {}).get("source_mode") or "")
            if not d.get("source_modes"):
                d["source_modes"] = (d["extra"] or {}).get("source_modes") or []
            cards.append(d)
    except Exception as exc:  # noqa: BLE001 — 只读统计，失败记入 data_gaps
        return [], f"读取 cards.db 失败: {exc}"
    return cards, None


def filter_published(cards: Iterable[Dict[str, Any]], start_ts: int, end_ts: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for card in cards:
        try:
            ts = int(card.get("created_at_ts") or 0)
        except (TypeError, ValueError):
            ts = 0
        if ts <= 0:
            dt = parse_datetime(card.get("created_at"))
            if dt is None or not in_window(dt, datetime.fromtimestamp(start_ts, tz=HKT), datetime.fromtimestamp(end_ts, tz=HKT)):
                continue
            out.append(card)
            continue
        if start_ts <= ts < end_ts:
            out.append(card)
    return out


def filter_fetched(cards: Iterable[Dict[str, Any]], start: datetime, end: datetime) -> List[Dict[str, Any]]:
    return [c for c in cards if in_window(card_updated_dt(c), start, end)]


def publish_log_paths(
    log_dir: Path,
    day: Optional[date] = None,
    *,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> List[Path]:
    """覆盖窗口（或当日）涉及的日志，并各向外扩一天，避免跨日写入漏记。"""
    if start is not None and end is not None:
        core = dates_touching_window(start, end)
    elif day is not None:
        core = [day]
    else:
        raise ValueError("publish_log_paths 需要 day 或 start/end")
    first = core[0] - timedelta(days=1)
    last = core[-1] + timedelta(days=1)
    days: List[date] = []
    cur = first
    while cur <= last:
        days.append(cur)
        cur += timedelta(days=1)
    paths: List[Path] = []
    for d in days:
        p = log_dir / f"publish_{d.isoformat()}.log"
        if p.is_file():
            paths.append(p)
    return paths


def load_publish_records(
    log_dir: Path,
    day: date,
    start: datetime,
    end: datetime,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    gaps: List[str] = []
    bad_lines: List[str] = []
    records: List[Dict[str, Any]] = []
    paths = publish_log_paths(log_dir, day, start=start, end=end)
    need_days = dates_touching_window(start, end) if start is not None and end is not None else ([day] if day else [])
    missing = [d.isoformat() for d in need_days if not (log_dir / f"publish_{d.isoformat()}.log").is_file()]
    if missing:
        if len(need_days) == 1:
            gaps.append(f"当日发布日志不存在: {log_dir / f'publish_{need_days[0].isoformat()}.log'}")
        else:
            gaps.append("窗口内发布日志缺失: " + ", ".join(f"publish_{d}.log" for d in missing))
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            gaps.append(f"无法读取 {path}: {exc}")
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad_lines.append(f"{path.name}:{i}")
                continue
            if not isinstance(rec, dict):
                continue
            ts = parse_datetime(rec.get("ts"))
            if not in_window(ts, start, end):
                continue
            rec["_source_file"] = path.name
            records.append(rec)
    if bad_lines:
        gaps.append(f"发布日志有 {len(bad_lines)} 行无法解析 JSON: {', '.join(bad_lines[:8])}")
    return records, gaps, [p.name for p in paths]


def summarize_cdp(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    by_platform: Dict[str, Dict[str, Any]] = {}
    attempts: List[Dict[str, Any]] = []
    events = Counter()
    runs: List[Dict[str, Any]] = []

    def plat_bucket(pid: str) -> Dict[str, Any]:
        if pid not in by_platform:
            by_platform[pid] = {
                "success": 0,
                "fail": 0,
                "fail_reasons": {},
                "platform_name": "",
            }
        return by_platform[pid]

    for rec in records:
        ev = str(rec.get("event") or "")
        events[ev] += 1
        pid = str(rec.get("platform") or "").strip()
        pname = str(rec.get("platform_name") or "").strip()
        if ev in ("platform_ok", "platform_fail"):
            if not pid:
                pid = pname or "?"
            bucket = plat_bucket(pid)
            if pname:
                bucket["platform_name"] = pname
            short = {
                "ts": rec.get("ts"),
                "event": ev,
                "platform": pid,
                "platform_name": pname,
                "step": rec.get("step") or "",
                "elapsed_ms": rec.get("elapsed_ms") or 0,
                "message": rec.get("message") or "",
                "content_ref": rec.get("content_ref") or "",
            }
            if ev == "platform_ok":
                bucket["success"] += 1
                short["success"] = True
            else:
                bucket["fail"] += 1
                cat = str(rec.get("failure_category") or "error")
                msg = str(rec.get("message") or "发布失败").strip()
                reason = f"{cat}: {msg}" if msg else cat
                _bump(bucket["fail_reasons"], reason)
                short["success"] = False
                short["failure_category"] = cat
                short["fail_reason"] = reason
                short["last_url"] = rec.get("last_url") or ""
            attempts.append(short)
        elif ev == "run_start":
            runs.append(
                {
                    "ts": rec.get("ts"),
                    "event": ev,
                    "platforms": rec.get("platforms") or [],
                    "content_ref": rec.get("content_ref") or "",
                    "media_count": rec.get("media_count") or 0,
                    "debugger_url": rec.get("debugger_url") or "",
                }
            )
        elif ev == "run_end":
            runs.append(
                {
                    "ts": rec.get("ts"),
                    "event": ev,
                    "success_count": rec.get("success_count"),
                    "total": rec.get("total"),
                    "aborted": rec.get("aborted"),
                    "elapsed_ms": rec.get("elapsed_ms"),
                    "content_ref": rec.get("content_ref") or "",
                }
            )
        elif ev == "cdp_connect_fail":
            attempts.append(
                {
                    "ts": rec.get("ts"),
                    "event": ev,
                    "platform": "cdp",
                    "success": False,
                    "step": rec.get("step") or "connect_cdp",
                    "failure_category": rec.get("failure_category") or "network",
                    "fail_reason": f"{rec.get('failure_category') or 'network'}: {rec.get('message') or 'CDP 连接失败'}",
                    "message": rec.get("message") or "",
                }
            )

    success_total = sum(int(v["success"]) for v in by_platform.values())
    fail_total = sum(int(v["fail"]) for v in by_platform.values())
    return {
        "total": success_total + fail_total,
        "success": success_total,
        "fail": fail_total,
        "runs": events.get("run_start", 0),
        "runs_ended": events.get("run_end", 0),
        "cdp_connect_ok": events.get("cdp_connect_ok", 0),
        "cdp_connect_fail": events.get("cdp_connect_fail", 0),
        "by_platform": by_platform,
        "events": dict(events),
        "attempts": attempts,
        "run_timeline": runs,
    }


def _http_get_json(url: str, timeout: float = 5.0) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        if isinstance(data, dict):
            return data, None
        return None, f"{url} 返回非对象 JSON"
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code} {url}"
    except urllib.error.URLError as exc:
        return None, f"无法连接 {url}: {exc.reason}"
    except Exception as exc:  # noqa: BLE001
        return None, f"请求 {url} 失败: {exc}"


def maybe_fetch_api(
    api_base: str,
    day: date,
    start: datetime,
    end: datetime,
) -> Tuple[Dict[str, Any], List[str]]:
    gaps: List[str] = []
    live: Dict[str, Any] = {"ok": False}
    if not api_base:
        return live, gaps
    base = api_base.rstrip("/")
    kol, err = _http_get_json(f"{base}/api/signals/kol-realtime")
    if err:
        gaps.append(f"API kol-realtime: {err}")
    else:
        live["kol_realtime"] = (kol or {}).get("kol_realtime") if kol else None
        live["ok"] = True
    q = urllib.parse.urlencode(
        {
            "from": start.isoformat(timespec="seconds"),
            "to": end.isoformat(timespec="seconds"),
            "limit": "500",
            "merge": "1",
        }
    )
    cards, err = _http_get_json(f"{base}/api/signals/cards?{q}")
    if err:
        gaps.append(f"API /api/signals/cards: {err}")
    elif cards:
        items = cards.get("items") if isinstance(cards.get("items"), list) else []
        api_summary = summarize_cards(items)
        live["cards_api"] = {
            "item_count": len(items),
            "twitter_raw": api_summary["twitter"]["raw"],
            "binance_raw": api_summary["binance"]["raw"],
            "twitter_kept": api_summary["twitter"]["kept"],
            "binance_kept": api_summary["binance"]["kept"],
        }
        live["ok"] = True
    bs, err = _http_get_json(f"{base}/api/signals/binance-square/cycle")
    if err:
        gaps.append(f"API binance-square/cycle: {err}")
    elif bs:
        live["binance_square_cycle"] = {
            k: bs.get(k)
            for k in ("success", "cycle", "enabled", "alive", "last_run_at", "last_status", "last_message")
            if k in bs or (isinstance(bs.get("cycle"), dict) and k in (bs.get("cycle") or {}))
        }
        if isinstance(bs.get("cycle"), dict):
            live["binance_square_cycle"] = bs.get("cycle")
        live["ok"] = True
    return live, gaps


def compact_platform(stats: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "raw": stats["raw"],
        "kept": stats["kept"],
        "dropped": stats["dropped"],
        "by_handle": stats["by_handle"],
        "kept_by_handle": stats["kept_by_handle"],
        "by_source": stats["by_source"],
        "examples_kept": stats["examples_kept"],
        "examples_dropped": stats["examples_dropped"],
    }


def _fmt_handles(d: Dict[str, int], limit: int = 8) -> str:
    if not d:
        return "无"
    items = sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return "、".join(f"{k} {v}" for k, v in items)


def _fmt_fail_reasons(reasons: Dict[str, int]) -> str:
    if not reasons:
        return "无"
    items = sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))
    return "；".join(f"{k} ×{v}" for k, v in items)


def _cn_sec(n: int) -> str:
    names = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七"}
    return names.get(n, str(n))


def format_chinese_summary(report: Dict[str, Any]) -> str:
    day = report["date"]
    tz = report["timezone"]
    cdp = report["cdp"]
    sig = report["signals"]
    fetched = report.get("signals_fetched") or {}
    gaps = report.get("data_gaps") or []
    win = report.get("window") or {}
    rolling = str(win.get("mode") or "") == "rolling_hours"
    scope = "本窗口" if rolling else "当日"
    lines: List[str] = []
    if rolling:
        hours = win.get("hours")
        hours_txt = f"，最近 {hours} 小时" if hours else ""
        lines.append(
            f"窗口 {win.get('start') or ''} → {win.get('end') or ''}（{tz}{hours_txt}）"
        )
    else:
        lines.append(f"日期 {day}（{tz}）")
    lines.append("")
    lines.append("一、CDP 发布")
    lines.append(
        f"  发布轮次 {cdp.get('runs', 0)} 轮，平台尝试 {cdp.get('total', 0)} 次："
        f"成功 {cdp.get('success', 0)}，失败 {cdp.get('fail', 0)}。"
        f" CDP 连接成功 {cdp.get('cdp_connect_ok', 0)}，失败 {cdp.get('cdp_connect_fail', 0)}。"
    )
    by_p = cdp.get("by_platform") or {}
    if not by_p:
        lines.append(f"  {scope}无平台发布记录。")
    else:
        for pid, row in sorted(by_p.items(), key=lambda kv: kv[0]):
            name = row.get("platform_name") or pid
            line = (
                f"  - {name}（{pid}）：成功 {row.get('success', 0)}，"
                f"失败 {row.get('fail', 0)}"
            )
            if row.get("fail"):
                line += f"；失败原因：{_fmt_fail_reasons(row.get('fail_reasons') or {})}"
            lines.append(line)
    lines.append("")
    lines.append(f"二、实时贴文（按贴文发布时间落在{scope}，主计数）")
    for key, title in (("twitter", "推特 / X"), ("binance", "币安广场")):
        s = (sig.get(key) or empty_platform_stats())
        lines.append(
            f"  {title}：{scope}发布 {s.get('raw', 0)} 张，"
            f"过滤后保留 {s.get('kept', 0)}，剔除 {s.get('dropped', 0)}。"
        )
        lines.append(f"    账号（全部）：{_fmt_handles(s.get('by_handle') or {})}")
        if s.get("kept"):
            lines.append(f"    账号（保留）：{_fmt_handles(s.get('kept_by_handle') or {})}")
        src = s.get("by_source") or {}
        if src:
            lines.append(f"    来源：{_fmt_handles(src)}")
    lines.append("")
    lines.append(f"三、{scope}抓取 / 更新（updated_at / parsed_at，含窗口外发布的帖）")
    for key, title in (("twitter", "推特 / X"), ("binance", "币安广场")):
        s = (fetched.get(key) or empty_platform_stats())
        posted_other = s.get("posted_other_day", 0)
        lines.append(
            f"  {title}：抓取/更新 {s.get('raw', 0)} 张，"
            f"过滤后保留 {s.get('kept', 0)}，剔除 {s.get('dropped', 0)}"
            + (f"，其中 {posted_other} 张发布时间不在{scope}。" if posted_other else "。")
        )
        if s.get("by_handle"):
            lines.append(f"    账号：{_fmt_handles(s.get('by_handle') or {})}")
        if s.get("kept"):
            lines.append(f"    保留账号：{_fmt_handles(s.get('kept_by_handle') or {})}")
    lines.append("")
    lines.append("四、过滤规则")
    lines.append(f"  {FILTER_RULE}")
    lines.append("  保留例：coins=['BTC'] + direction='long'。")
    lines.append("  剔除例：只提 BTC 无方向；只说「还有个多单」未点名币种；闲聊。")
    sec = 5
    if gaps:
        lines.append("")
        lines.append(f"{_cn_sec(sec)}、数据缺口")
        sec += 1
        for g in gaps:
            lines.append(f"  - {g}")
    live = report.get("live") or {}
    kol = live.get("kol_realtime") if isinstance(live.get("kol_realtime"), dict) else None
    if kol:
        lines.append("")
        lines.append(f"{_cn_sec(sec)}、实时服务状态（本机 API，非计数依据）")
        sec += 1
        handles = kol.get("handles") or []
        htxt = "、".join(str(h) for h in handles) if handles else "未知"
        lines.append(
            f"  KOL 实时：enabled={kol.get('enabled')} alive={kol.get('alive')} "
            f"last={kol.get('last_run_at') or ''} {kol.get('last_message') or ''}；"
            f"账号 {htxt}"
        )
    bsc = live.get("binance_square_cycle") if isinstance(live.get("binance_square_cycle"), dict) else None
    if bsc:
        lines.append(
            f"  币安广场周期：last={bsc.get('last_run_at') or ''} "
            f"{bsc.get('last_status') or ''} {bsc.get('last_message') or bsc.get('last_error') or ''}"
        )
    out_file = report.get("output_file") or ""
    if out_file:
        lines.append("")
        lines.append(f"JSON：{out_file}")
    return "\n".join(lines) + "\n"


def _posted_other_count(fetched_cards: Sequence[Dict[str, Any]], start_ts: int, end_ts: int) -> Dict[str, int]:
    counts = {"twitter": 0, "binance": 0}
    for card in fetched_cards:
        plat = card_platform(card)
        try:
            ts = int(card.get("created_at_ts") or 0)
        except (TypeError, ValueError):
            ts = 0
        if not (start_ts <= ts < end_ts):
            counts[plat if plat in counts else "twitter"] += 1
    return counts


def build_report(
    *,
    root: Path,
    day: Optional[date] = None,
    hours: Optional[int] = None,
    end: Optional[datetime] = None,
    api_base: str = "",
    db_path: Optional[Path] = None,
    log_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    if hours:
        start, end, start_ts, end_ts = hours_window(int(hours), end=end)
        day = end.astimezone(HKT).date()
        window_mode = "rolling_hours"
    else:
        if day is None:
            raise ValueError("build_report 需要 day 或 hours")
        start, end, start_ts, end_ts = day_window(day)
        window_mode = "calendar_day"
    gaps: List[str] = []
    log_dir = log_dir or (root / "output" / "publish_logs")
    db_path = db_path or (root / "output" / "signals" / "cards.db")

    records, log_gaps, log_files = load_publish_records(log_dir, day, start, end)
    gaps.extend(log_gaps)
    cdp = summarize_cdp(records)
    cdp["log_files"] = log_files
    cdp["log_dir"] = rel_to_root(log_dir, root)

    cards, db_gap = load_cards_from_db(db_path)
    if db_gap:
        gaps.append(db_gap)
    published = filter_published(cards, start_ts, end_ts)
    fetched = filter_fetched(cards, start, end)
    sig = summarize_cards(published)
    sig_f = summarize_cards(fetched)
    other = _posted_other_count(fetched, start_ts, end_ts)
    for plat in ("twitter", "binance"):
        sig_f[plat]["posted_other_day"] = other.get(plat, 0)

    live: Dict[str, Any] = {}
    if api_base:
        live, api_gaps = maybe_fetch_api(api_base, day, start, end)
        gaps.extend(api_gaps)
        api_cards = (live.get("cards_api") or {}) if live else {}
        if api_cards:
            if api_cards.get("twitter_raw") != sig["twitter"]["raw"] or api_cards.get("binance_raw") != sig["binance"]["raw"]:
                gaps.append(
                    "API /api/signals/cards 与 cards.db 当日发布计数不一致："
                    f"API 推特 {api_cards.get('twitter_raw')} / 币安 {api_cards.get('binance_raw')}，"
                    f"DB 推特 {sig['twitter']['raw']} / 币安 {sig['binance']['raw']}。"
                    "主计数以 cards.db 为准（API 默认 limit 500 且可能隐藏过期卡）。"
                )

    report: Dict[str, Any] = {
        "date": day.isoformat(),
        "timezone": TZ_NAME,
        "window": {
            "mode": window_mode,
            "hours": int(hours) if hours else None,
            "start": start.isoformat(timespec="seconds"),
            "end": end.isoformat(timespec="seconds"),
            "start_ts": start_ts,
            "end_ts": end_ts,
            "published_field": "created_at_ts（贴文发布时间）",
            "fetched_field": "updated_at，缺则 parsed_at（入库/更新时间；naive 视为 HKT）",
        },
        "filter_rule": FILTER_RULE,
        "filter_examples": FILTER_EXAMPLES,
        "cdp": cdp,
        "signals": {
            "twitter": compact_platform(sig["twitter"]),
            "binance": compact_platform(sig["binance"]),
            "window": "published",
            "db_path": rel_to_root(db_path, root),
            "db_card_total": len(cards),
            "published_total": len(published),
        },
        "signals_fetched": {
            "twitter": compact_platform(sig_f["twitter"]) | {"posted_other_day": sig_f["twitter"].get("posted_other_day", 0)},
            "binance": compact_platform(sig_f["binance"]) | {"posted_other_day": sig_f["binance"].get("posted_other_day", 0)},
            "window": "fetched",
            "fetched_total": len(fetched),
        },
        "live": live,
        "data_gaps": gaps,
    }
    return report


def write_outputs(report: Dict[str, Any], out_json: Path, *, root: Path) -> Tuple[Path, Path, str, str, str]:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    report = dict(report)
    rel_json = rel_to_root(out_json, root)
    out_txt = out_json.with_suffix(".txt")
    rel_txt = rel_to_root(out_txt, root)
    report["output_file"] = rel_json
    report["output_txt"] = rel_txt
    summary = format_chinese_summary(report)
    report["summary_text"] = summary
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_txt.write_text(summary, encoding="utf-8")
    return out_json, out_txt, summary, rel_json, rel_txt


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="daily_cdp_and_signals_report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="统计指定香港日历日或最近 N 小时的 CDP 发布结果，以及推特 / 币安广场实时卡片数量（含做多做空+币种过滤）。",
        epilog=(
            "过滤规则：\n"
            f"  {FILTER_RULE}\n"
            "  保留例：coins=['BTC'] direction='long'\n"
            "  剔除例：coins=['BTC'] direction='unknown'（只提币无方向）；"
            "coins=[] direction='long'（有方向无币种）；闲聊。\n"
            "\n"
            "时间：默认今天（Asia/Hong_Kong）。--hours N 为最近 N 小时滚动窗，与 --date 互斥。"
            "主计数按贴文发布时间；同时输出窗口内抓取/更新。naive 时间戳按 HKT 解释。\n"
        ),
    )
    parser.add_argument(
        "--date",
        default="",
        help="统计日期 YYYY-MM-DD，默认 Asia/Hong_Kong 今天；与 --hours 互斥",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=0,
        help="统计最近 N 小时（[现在-N小时, 现在)），与 --date 互斥",
    )
    parser.add_argument(
        "--api-base",
        default="http://127.0.0.1:8787",
        help="本机 console API，仅 GET；默认 http://127.0.0.1:8787；传空字符串可跳过",
    )
    parser.add_argument(
        "--no-api",
        action="store_true",
        help="不请求本机 API，只读日志和 cards.db",
    )
    parser.add_argument(
        "--root",
        default="",
        help="项目根目录，默认脚本所在仓库根",
    )
    parser.add_argument(
        "--output",
        default="",
        help="JSON 输出路径，默认 output/reports/daily_cdp_signals_YYYY-MM-DD.json；滚动窗为 cdp_signals_起止时间.json",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).expanduser().resolve() if args.root else ROOT
    hours = int(args.hours or 0)
    if hours and args.date:
        print("--hours 与 --date 不能同时使用", file=sys.stderr)
        return 2
    if hours < 0:
        print("--hours 必须为正整数", file=sys.stderr)
        return 2
    day: Optional[date] = None
    if not hours:
        try:
            day = parse_date(args.date) if args.date else today_hkt()
        except ValueError:
            print(f"无效日期: {args.date}，请用 YYYY-MM-DD", file=sys.stderr)
            return 2
    api_base = "" if args.no_api else str(args.api_base or "").strip()
    report = build_report(root=root, day=day, hours=hours or None, api_base=api_base)
    if args.output:
        out_json = Path(args.output).expanduser()
        if not out_json.is_absolute():
            out_json = root / out_json
    else:
        if hours:
            win = report["window"]
            start_tag = datetime.fromisoformat(win["start"]).strftime("%Y%m%d-%H%M")
            end_tag = datetime.fromisoformat(win["end"]).strftime("%Y%m%d-%H%M")
            out_json = root / "output" / "reports" / f"cdp_signals_{start_tag}_{end_tag}.json"
        else:
            out_json = root / "output" / "reports" / f"daily_cdp_signals_{day.isoformat()}.json"
    _out, _txt, summary, rel_json, rel_txt = write_outputs(report, out_json, root=root)
    sys.stdout.write(summary)
    sys.stdout.write(f"TXT：{rel_txt}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
