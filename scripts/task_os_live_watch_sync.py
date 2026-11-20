#!/usr/bin/env python3
# coding=utf-8
"""增量同步 task-os data/live_watch.json（详见 docs/task_os_live_watch.md）。"""
from __future__ import annotations

import argparse
import json
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
from scripts.task_os_live_watch_digest import (  # noqa: E402
    collect_publish,
    collect_signals,
    collect_vpn,
    index_display_names,
)

TZ = dcdr.HKT
SLOT_ORDER = [0, 8, 12, 16, 20]
CONFIG_PATH = ROOT / "config" / "task_os_live_watch.yaml"

CAT_LABEL = {
    "signal": "信号",
    "publish": "发布",
    "bitget": "Bitget",
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
    cfg.setdefault("vpn_state_json", "~/Library/Logs/vpn-guard/state.json")
    cfg.setdefault("vpn_log_dir", "")
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
    """返回 (twitter_handles, binance_profile_ids, display_names)。

    重点集合仍只含 important: true。展示名覆盖全部已配置账号，汇总里才能写出名字。
    """
    tw: Set[str] = set()
    sq: Set[str] = set()
    ch_path = ROOT / "config" / "signals_channels.yaml"
    raw = load_yaml(ch_path)
    channels = raw.get("channels") if isinstance(raw.get("channels"), dict) else {}
    for handle, row in channels.items():
        if not isinstance(row, dict) or not row.get("important"):
            continue
        key = str(handle).strip().lower()
        keys = {key} if key else set()
        for alias in row.get("aliases") or []:
            a = str(alias).strip().lower()
            if a:
                keys.add(a)
        tw.update(k for k in keys if k)
    bs_path = ROOT / "config" / "binance_square_signals.yaml"
    bs = load_yaml(bs_path)
    profiles = bs.get("profiles") if isinstance(bs.get("profiles"), list) else []
    for prof in profiles:
        if not isinstance(prof, dict) or not prof.get("important"):
            continue
        pid = str(prof.get("id") or prof.get("name") or "").strip().lower()
        pids = {pid} if pid else set()
        nm = str(prof.get("name") or "").strip().lower()
        if nm:
            pids.add(nm)
        for alias in prof.get("aliases") or []:
            a = str(alias).strip().lower()
            if a:
                pids.add(a)
        sq.update(p for p in pids if p)
    names = index_display_names(channels, profiles)
    return tw, sq, names


def http_get_json(url: str, timeout: float = 12.0) -> Tuple[Optional[Any], Optional[str]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "task-os-live-watch/1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace")), None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        return None, str(exc)


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
            title = f"Bitget 自动 · {sym} · {status}"
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
                            "title": f"Bitget {row.get('source')} · {row.get('symbol')} · {row.get('status')}",
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


def merge_feed(
    existing: Dict[str, Any],
    new_items: Iterable[Dict[str, Any]],
    max_items: int,
    slot_label: str,
) -> Dict[str, Any]:
    seen = {str(it.get("id")) for it in existing.get("items") or [] if isinstance(it, dict)}
    merged = list(existing.get("items") or [])
    added = 0
    for it in new_items:
        if not isinstance(it, dict):
            continue
        iid = str(it.get("id") or "")
        if not iid or iid in seen:
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
            slot=slot,
        )
    )
    new_items.extend(
        collect_publish(
            expand_path(str(cfg["publish_log_dir"]), ROOT),
            expand_path(str(cfg["publish_history_db"]), ROOT),
            start,
            end,
            slot=slot,
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
    vpn_slots = [int(x) for x in (cfg.get("vpn_slots") or [12, 20])]
    if slot in vpn_slots:
        state_path = expand_path(str(cfg["vpn_state_json"]), ROOT)
        raw_log_dir = str(cfg.get("vpn_log_dir") or "").strip()
        log_dir = expand_path(raw_log_dir, ROOT) if raw_log_dir else state_path.parent
        new_items.extend(collect_vpn(state_path, slot, end, log_dir=log_dir))

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