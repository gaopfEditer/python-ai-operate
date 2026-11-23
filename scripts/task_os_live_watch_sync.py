#!/usr/bin/env python3
# coding=utf-8
"""增量同步 task-os data/live_watch.json（详见 docs/task_os_live_watch.md）。"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import daily_cdp_and_signals_report as dcdr  # noqa: E402
from signals.labels import is_trade_signal, normalize_direction  # noqa: E402

TZ = dcdr.HKT
SLOT_ORDER = [0, 8, 12, 16, 20]
CONFIG_PATH = ROOT / "config" / "task_os_live_watch.yaml"

CAT_LABEL = {
    "signal": "信号",
    "publish": "发布",
    "bitget": "自动下单",
    "vpn": "VPN",
}


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def expand_path(raw: str, base: Path) -> Path:
    text = str(raw or "").strip().replace("~", str(Path.home()))
    p = Path(text)
    if not p.is_absolute():
        p = (base / p).resolve()
    return p


def load_config() -> Dict[str, Any]:
    cfg = load_yaml(CONFIG_PATH)
    cfg.setdefault("timezone", "Asia/Shanghai")
    cfg.setdefault("slots", SLOT_ORDER)
    cfg.setdefault("vpn_slots", [12, 20])
    cfg.setdefault("task_os_repo", "../task-os")
    cfg.setdefault("feed_path", "data/live_watch.json")
    cfg.setdefault("state_path", "output/task_os_live_watch_state.json")
    cfg.setdefault("cards_db", "output/signals/cards.db")
    cfg.setdefault("publish_log_dir", "output/publish_logs")
    cfg.setdefault("publish_history_db", "output/publish_history.db")
    cfg.setdefault("collector_api_base", "http://127.0.0.1:3851")
    cfg.setdefault(
        "bitget_history_json",
        "../auto-script/discord-collector/data/bitget-order-history.json",
    )
    cfg.setdefault(
        "kolvip_autotrade_json",
        "../auto-script/discord-collector/config/kolvip-autotrade.json",
    )
    cfg.setdefault("vpn_state_json", "~/Library/Logs/vpn-guard/state.json")
    cfg.setdefault("max_items", 500)
    cfg.setdefault("git_push", False)
    return cfg


def now_local() -> datetime:
    return datetime.now(TZ)


def detect_slot(now: Optional[datetime] = None) -> int:
    now = now or now_local()
    h, m = now.hour, now.minute
    best = SLOT_ORDER[0]
    best_dist = 999
    for s in SLOT_ORDER:
        dist = (h - s) * 60 + m
        if 0 <= dist < 90 and dist < best_dist:
            best_dist = dist
            best = s
    return best


def window_for_slot(slot_h: int, ref: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    ref = ref or now_local()
    if slot_h not in SLOT_ORDER:
        raise ValueError(f"unknown slot {slot_h}")
    idx = SLOT_ORDER.index(slot_h)
    end = ref.replace(hour=slot_h, minute=0, second=0, microsecond=0)
    if idx == 0:
        start = (end - timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
    else:
        prev_h = SLOT_ORDER[idx - 1]
        start = end.replace(hour=prev_h, minute=0, second=0, microsecond=0)
    return start, end


def important_authors() -> Tuple[Set[str], Set[str], Dict[str, str]]:
    """返回 (twitter_handles, binance_profile_ids, display_names)。"""
    tw: Set[str] = set()
    sq: Set[str] = set()
    names: Dict[str, str] = {}
    ch_path = ROOT / "config" / "signals_channels.yaml"
    raw = load_yaml(ch_path)
    channels = raw.get("channels") if isinstance(raw.get("channels"), dict) else {}
    for handle, row in channels.items():
        if not isinstance(row, dict) or not row.get("important"):
            continue
        key = str(handle).strip().lower()
        disp = str(row.get("channelName") or row.get("name") or handle)
        keys = {key} if key else set()
        for alias in row.get("aliases") or []:
            a = str(alias).strip().lower()
            if a:
                keys.add(a)
        for k in keys:
            tw.add(k)
            names[f"x:{k}"] = disp
    bs_path = ROOT / "config" / "binance_square_signals.yaml"
    bs = load_yaml(bs_path)
    for prof in bs.get("profiles") or []:
        if not isinstance(prof, dict) or not prof.get("important"):
            continue
        pid = str(prof.get("id") or prof.get("name") or "").strip().lower()
        disp = str(prof.get("name") or pid)
        pids = {pid} if pid else set()
        nm = str(prof.get("name") or "").strip().lower()
        if nm:
            pids.add(nm)
        for alias in prof.get("aliases") or []:
            a = str(alias).strip().lower()
            if a:
                pids.add(a)
        for p in pids:
            sq.add(p)
            names[f"bs:{p}"] = disp
    return tw, sq, names


def http_get_json(url: str, timeout: float = 12.0) -> Tuple[Optional[Any], Optional[str]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "task-os-live-watch/1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace")), None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        return None, str(exc)


def collect_signals(
    db_path: Path,
    start: datetime,
    end: datetime,
    tw_imp: Set[str],
    sq_imp: Set[str],
    names: Dict[str, str],
) -> List[Dict[str, Any]]:
    cards, err = dcdr.load_cards_from_db(db_path)
    if err:
        return [
            {
                "id": f"meta:signal:err:{int(end.timestamp())}",
                "category": "signal",
                "ts": end.isoformat(timespec="seconds"),
                "title": "信号源读取失败",
                "body": err,
                "meta": {"level": "error"},
            }
        ]
    out: List[Dict[str, Any]] = []
    for card in cards:
        if not dcdr.in_window(dcdr.card_updated_dt(card), start, end) and not dcdr.in_window(
            dcdr.parse_datetime(card.get("created_at")), start, end
        ):
            continue
        sm = str(card.get("source_mode") or "").strip().lower()
        handle = str(card.get("user_handle") or "").strip().lower()
        extra = card.get("extra") if isinstance(card.get("extra"), dict) else {}
        profile = str(extra.get("profile_id") or extra.get("square_profile") or handle).lower()
        is_x = sm in ("", "x", "twitter")
        is_bs = sm == "binance_square" or "binance_square" in (card.get("source_modes") or [])
        important = (is_x and handle in tw_imp) or (is_bs and profile in sq_imp)
        sig = card.get("signal") if isinstance(card.get("signal"), dict) else {}
        trade = is_trade_signal(sig)
        if not important and not trade:
            continue
        src_label = "推特" if is_x else ("币安广场" if is_bs else sm or "信号")
        nick = names.get(f"x:{handle}") or names.get(f"bs:{profile}") or handle or profile or "未知"
        tid = str(card.get("tweet_id") or card.get("id") or card.get("list_id") or "")
        item_id = f"sig:{sm or 'x'}:{tid or card.get('id', '')}"
        if not tid and not card.get("id"):
            continue
        coins = [str(c) for c in (sig.get("coins") or []) if str(c).strip()]
        direction = normalize_direction(str(sig.get("direction") or ""))
        summary = str(sig.get("summary") or "").strip()
        text = str(card.get("text") or "").strip()
        title_parts = [src_label, nick]
        if important:
            title_parts.append("重点")
        if trade and coins:
            title_parts.append(f"{','.join(coins[:3])} {dcdr.DIRECTION_ALIASES.get(direction, direction)}")
        title = " · ".join(title_parts)
        body_lines = []
        if important and trade and summary:
            body_lines.append(f"**摘要** {summary}")
        elif important and summary:
            body_lines.append(f"**摘要** {summary}")
        elif trade and summary:
            body_lines.append(summary)
        if text and text != summary:
            preview = text.replace("\n", " ").strip()
            if len(preview) > 280:
                preview = preview[:277] + "…"
            body_lines.append(preview)
        url = str(card.get("url") or extra.get("url") or "").strip()
        if url:
            body_lines.append(url)
        ts = (
            dcdr.parse_datetime(card.get("created_at"))
            or dcdr.card_updated_dt(card)
            or end
        ).isoformat(timespec="seconds")
        out.append(
            {
                "id": item_id,
                "category": "signal",
                "ts": ts,
                "title": title,
                "body": "\n".join(body_lines),
                "meta": {
                    "important": important,
                    "trade": trade,
                    "handle": handle,
                    "profile": profile,
                    "source_mode": sm,
                },
            }
        )
    return out


def collect_publish(
    log_dir: Path,
    history_db: Path,
    start: datetime,
    end: datetime,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    day = end.date()
    records, gaps, _paths = dcdr.load_publish_records(log_dir, day, start, end)
    for rec in records:
        ev = str(rec.get("event") or "")
        if ev not in ("platform_ok", "platform_fail", "run_start", "run_end", "cdp_connect_fail"):
            continue
        pid = str(rec.get("platform") or rec.get("platform_name") or "?")
        ok = ev == "platform_ok"
        cref = str(rec.get("content_ref") or "")
        ts = str(rec.get("ts") or end.isoformat(timespec="seconds"))
        item_id = f"pub:{ev}:{pid}:{cref}:{ts}"
        if ev in ("run_start", "run_end"):
            title = f"CDP {ev}"
            body = json.dumps(
                {k: rec.get(k) for k in ("platforms", "success_count", "total", "message")},
                ensure_ascii=False,
            )
        else:
            title = f"{'✓' if ok else '✗'} {pid} {ev}"
            body = str(rec.get("message") or rec.get("step") or "").strip()
        items.append(
            {
                "id": item_id,
                "category": "publish",
                "ts": ts,
                "title": title,
                "body": body,
                "meta": {"event": ev, "platform": pid, "ok": ok, "source": "publish_log"},
            }
        )
    if gaps:
        items.append(
            {
                "id": f"meta:publish:gap:{int(end.timestamp())}",
                "category": "publish",
                "ts": end.isoformat(timespec="seconds"),
                "title": "发布日志提示",
                "body": "；".join(gaps[:3]),
                "meta": {"level": "info"},
            }
        )
    if history_db.is_file():
        try:
            uri = f"file:{history_db}?mode=ro"
            with sqlite3.connect(uri, uri=True) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT id, title, status, success_count, total_count, message, created_at, platforms_json
                    FROM publish_history
                    WHERE created_at >= ? AND created_at < ?
                    ORDER BY created_at DESC
                    """,
                    (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")),
                ).fetchall()
            for row in rows:
                plats = json.loads(row["platforms_json"] or "[]")
                ts = str(row["created_at"] or end.isoformat(timespec="seconds"))
                item_id = f"pub:hist:{row['id']}"
                items.append(
                    {
                        "id": item_id,
                        "category": "publish",
                        "ts": ts,
                        "title": f"控制台发布 · {row['status']} ({row['success_count']}/{row['total_count']})",
                        "body": f"{row['title'] or ''}\n{row['message'] or ''}\n平台: {', '.join(plats if isinstance(plats, list) else [])}".strip(),
                        "meta": {"source": "publish_history", "status": row["status"]},
                    }
                )
        except Exception as exc:  # noqa: BLE001
            items.append(
                {
                    "id": f"meta:publish:db:{int(end.timestamp())}",
                    "category": "publish",
                    "ts": end.isoformat(timespec="seconds"),
                    "title": "publish_history 读取失败",
                    "body": str(exc),
                    "meta": {"level": "error"},
                }
            )
    return items


def collect_bitget(
    api_base: str,
    history_path: Path,
    start: datetime,
    end: datetime,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    q = urllib.parse.urlencode(
        {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "limit": "200",
        }
    )
    url = f"{api_base.rstrip('/')}/api/discord/signal-cards?{q}"
    data, err = http_get_json(url)
    if data and isinstance(data, dict) and data.get("ok") and isinstance(data.get("cards"), list):
        for card in data["cards"]:
            parsed = card.get("parsed") or card.get("parsedJson")
            if isinstance(parsed, str):
                try:
                    parsed = json.loads(parsed)
                except json.JSONDecodeError:
                    parsed = {}
            if not isinstance(parsed, dict):
                continue
            bo = parsed.get("bitgetOrder")
            if not isinstance(bo, dict):
                continue
            at = bo.get("at") or card.get("updatedAt") or card.get("updated_at")
            dt = dcdr.parse_datetime(at) if at else None
            if dt and not dcdr.in_window(dt, start, end):
                continue
            cid = card.get("id") or card.get("cardId")
            item_id = f"bitget:card:{cid}:{bo.get('orderId') or bo.get('status')}"
            sym = bo.get("symbol") or parsed.get("symbol") or "?"
            status = str(bo.get("status") or "?")
            title = f"自动下单 · {sym} · {status}"
            body = json.dumps(
                {k: bo.get(k) for k in ("holdSide", "orderType", "size", "stopLossPrice", "error", "reason")},
                ensure_ascii=False,
            )
            ts = (dt or end).isoformat(timespec="seconds")
            items.append(
                {
                    "id": item_id,
                    "category": "bitget",
                    "ts": ts,
                    "title": title,
                    "body": body,
                    "meta": {"card_id": cid, "source": "collector_api"},
                }
            )
    elif err:
        items.append(
            {
                "id": f"meta:bitget:api:{int(end.timestamp())}",
                "category": "bitget",
                "ts": end.isoformat(timespec="seconds"),
                "title": "Collector API 不可用",
                "body": f"{url}\n{err}",
                "meta": {"level": "info"},
            }
        )
    if history_path.is_file():
        try:
            rows = json.loads(history_path.read_text(encoding="utf-8"))
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    if str(row.get("source") or "").lower() == "manual":
                        continue
                    dt = dcdr.parse_datetime(row.get("at"))
                    if dt is None or not dcdr.in_window(dt, start, end):
                        continue
                    item_id = f"bitget:hist:{row.get('id') or row.get('orderId')}"
                    items.append(
                        {
                            "id": item_id,
                            "category": "bitget",
                            "ts": dt.isoformat(timespec="seconds"),
                            "title": f"自动下单 · {row.get('source')} · {row.get('symbol')} · {row.get('status')}",
                            "body": str(row.get("error") or row.get("orderId") or ""),
                            "meta": {"source": "history_json"},
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            items.append(
                {
                    "id": f"meta:bitget:json:{int(end.timestamp())}",
                    "category": "bitget",
                    "ts": end.isoformat(timespec="seconds"),
                    "title": "bitget-order-history 读取失败",
                    "body": str(exc),
                    "meta": {"level": "error"},
                }
            )
    return items


def _channel_name_map(autotrade_path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not autotrade_path.is_file():
        return out
    try:
        raw = json.loads(autotrade_path.read_text(encoding="utf-8"))
        for ch in raw.get("channels") or []:
            if not isinstance(ch, dict):
                continue
            name = str(ch.get("name") or ch.get("key") or "").strip()
            for cid in ch.get("channelIds") or []:
                out[str(cid).strip()] = name or str(cid)
    except Exception:
        pass
    return out


def collect_autotrade_daily_summary(
    history_path: Path,
    autotrade_path: Path,
    day_start: datetime,
    end: datetime,
) -> List[Dict[str, Any]]:
    """当日 0 点至今：按跟单频道汇总自动下单笔数（含熬鹰 5U）。"""
    names = _channel_name_map(autotrade_path)
    buckets: Dict[str, Dict[str, Any]] = {}

    def bump(row: Dict[str, Any]) -> None:
        cid = str(row.get("channelId") or row.get("channel_id") or "").strip()
        cname = str(row.get("channelName") or row.get("channel_name") or "").strip()
        label = names.get(cid) or cname or cid or "未知频道"
        key = cid or label
        st = buckets.setdefault(
            key,
            {"channel": label, "channel_id": cid, "orders": 0, "ok": 0, "fail": 0, "margin_u": None},
        )
        st["orders"] += 1
        status = str(row.get("status") or "").lower()
        if status in ("filled", "success", "ok", "placed", "dry_run"):
            st["ok"] += 1
        elif status in ("error", "failed", "fail", "rejected", "skipped"):
            st["fail"] += 1
        else:
            st["ok"] += 1
        mu = row.get("orderSizeUsdt") or row.get("margin_u")
        if mu is not None:
            try:
                st["margin_u"] = float(mu)
            except (TypeError, ValueError):
                pass

    if history_path.is_file():
        try:
            rows = json.loads(history_path.read_text(encoding="utf-8"))
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    if str(row.get("source") or "").lower() == "manual":
                        continue
                    dt = dcdr.parse_datetime(row.get("at"))
                    if dt is None or not dcdr.in_window(dt, day_start, end):
                        continue
                    bump(row)
        except Exception:
            pass

    if not buckets:
        return []
    items = sorted(buckets.values(), key=lambda x: (-int(x["orders"]), str(x["channel"])))
    total = sum(int(x["orders"]) for x in items)
    return [
        {
            "id": f"bitget:daily:{end.date().isoformat()}",
            "category": "bitget",
            "ts": end.isoformat(timespec="seconds"),
            "title": f"自动下单 · 今日汇总 · {len(items)} 频道 · {total} 笔",
            "body": "",
            "meta": {
                "kind": "autotrade_daily",
                "window_start": day_start.isoformat(timespec="seconds"),
                "window_end": end.isoformat(timespec="seconds"),
                "items": items,
                "count": len(items),
                "total_orders": total,
            },
        }
    ]


def collect_vpn(state_path: Path, slot: int, end: datetime) -> List[Dict[str, Any]]:
    if not state_path.is_file():
        return [
            {
                "id": f"vpn:missing:{slot}:{end.date().isoformat()}",
                "category": "vpn",
                "ts": end.isoformat(timespec="seconds"),
                "title": "VPN Guard 状态文件不存在",
                "body": str(state_path),
                "meta": {"level": "warn"},
            }
        ]
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [
            {
                "id": f"vpn:parse:{slot}:{end.date().isoformat()}",
                "category": "vpn",
                "ts": end.isoformat(timespec="seconds"),
                "title": "VPN 状态解析失败",
                "body": str(exc),
                "meta": {"level": "error"},
            }
        ]
    health = state.get("last_health") if isinstance(state.get("last_health"), dict) else {}
    ok = bool(health.get("ok"))
    owner = str(health.get("owner") or state.get("owner") or "?")
    node = str(health.get("node") or health.get("current_node") or "")
    lines = [
        f"健康: {'正常' if ok else '异常'}",
        f"出口归属: {owner}",
    ]
    if node:
        lines.append(f"节点: {node}")
    if state.get("fail_since"):
        lines.append(f"fail_since: {state.get('fail_since')}")
    item_id = f"vpn:{slot}:{end.date().isoformat()}"
    return [
        {
            "id": item_id,
            "category": "vpn",
            "ts": end.isoformat(timespec="seconds"),
            "title": f"VPN Guard · {'OK' if ok else 'FAULT'} · {owner}",
            "body": "\n".join(lines),
            "meta": {"ok": ok, "owner": owner},
        }
    ]


def merge_feed(
    existing: Dict[str, Any],
    new_items: Iterable[Dict[str, Any]],
    max_items: int,
    slot_label: str,
) -> Dict[str, Any]:
    seen = {str(it.get("id")) for it in existing.get("items") or [] if isinstance(it, dict)}
    merged = list(existing.get("items") or [])
    added = 0
    upsert_prefixes = ("bitget:daily:",)
    for it in new_items:
        if not isinstance(it, dict):
            continue
        iid = str(it.get("id") or "")
        if not iid:
            continue
        if any(iid.startswith(p) for p in upsert_prefixes):
            merged = [x for x in merged if not (isinstance(x, dict) and str(x.get("id") or "") == iid)]
            if iid not in seen:
                seen.add(iid)
            merged.insert(0, it)
            added += 1
            continue
        if iid in seen:
            continue
        seen.add(iid)
        merged.insert(0, it)
        added += 1
    merged = merged[: max(50, int(max_items))]
    return {
        "version": 1,
        "updated_at": now_local().isoformat(timespec="seconds"),
        "last_slot": slot_label,
        "items": merged,
        "_added": added,
    }


def git_push_feed(repo: Path, feed_rel: Path, message: str) -> Tuple[bool, str]:
    try:
        subprocess.run(["git", "-C", str(repo), "add", str(feed_rel)], check=True, capture_output=True, text=True)
        st = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain", str(feed_rel)],
            capture_output=True,
            text=True,
            check=True,
        )
        if not st.stdout.strip():
            return True, "无变更，跳过提交"
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", message],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(["git", "-C", str(repo), "push", "origin", "HEAD"], check=True, capture_output=True, text=True)
        return True, "已 push"
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        return False, err


def run_sync(
    *,
    slot: Optional[int] = None,
    dry_run: bool = False,
    push: bool = False,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = cfg or load_config()
    slot = slot if slot is not None else detect_slot()
    start, end = window_for_slot(slot)
    slot_label = f"{end.date().isoformat()}T{slot:02d}:00+08:00"
    tw, sq, names = important_authors()

    repo = expand_path(str(cfg["task_os_repo"]), ROOT)
    feed_path = repo / str(cfg["feed_path"])
    feed_path.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[str, Any] = {"version": 1, "items": []}
    if feed_path.is_file():
        try:
            existing = json.loads(feed_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {"version": 1, "items": []}

    new_items: List[Dict[str, Any]] = []
    new_items.extend(
        collect_signals(
            expand_path(str(cfg["cards_db"]), ROOT),
            start,
            end,
            tw,
            sq,
            names,
        )
    )
    new_items.extend(
        collect_publish(
            expand_path(str(cfg["publish_log_dir"]), ROOT),
            expand_path(str(cfg["publish_history_db"]), ROOT),
            start,
            end,
        )
    )
    new_items.extend(
        collect_bitget(
            str(cfg["collector_api_base"]),
            expand_path(str(cfg["bitget_history_json"]), ROOT),
            start,
            end,
        )
    )
    day_start = end.replace(hour=0, minute=0, second=0, microsecond=0)
    new_items.extend(
        collect_autotrade_daily_summary(
            expand_path(str(cfg["bitget_history_json"]), ROOT),
            expand_path(str(cfg["kolvip_autotrade_json"]), ROOT),
            day_start,
            end,
        )
    )
    vpn_slots = [int(x) for x in (cfg.get("vpn_slots") or [12, 20])]
    if slot in vpn_slots:
        new_items.extend(
            collect_vpn(expand_path(str(cfg["vpn_state_json"]), ROOT), slot, end)
        )

    merged = merge_feed(existing, new_items, int(cfg.get("max_items") or 500), slot_label)
    added = merged.pop("_added", 0)
    report = {
        "slot": slot,
        "window": {"start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds")},
        "added": added,
        "feed": str(feed_path),
        "dry_run": dry_run,
    }
    if dry_run:
        report["preview"] = new_items[:20]
        return report

    feed_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state_path = expand_path(str(cfg["state_path"]), ROOT)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {"last_slot": slot_label, "last_run": merged["updated_at"], "added": added},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    do_push = push or bool(cfg.get("git_push"))
    if do_push:
        ok, msg = git_push_feed(repo, Path(cfg["feed_path"]), f"chore(live_watch): sync {slot_label}")
        report["git_push"] = {"ok": ok, "message": msg}
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="同步 task-os 实时关注 feed")
    ap.add_argument("--slot", type=int, choices=SLOT_ORDER, help="指定档位小时 (0/8/12/16/20)")
    ap.add_argument("--dry-run", action="store_true", help="只统计，不写文件")
    ap.add_argument("--push", action="store_true", help="写入后 git commit + push task-os")
    args = ap.parse_args(list(argv) if argv is not None else None)
    rep = run_sync(slot=args.slot, dry_run=args.dry_run, push=args.push)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())