# coding=utf-8
"""解析后的增量信号 → Cards API 推送。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from signals.store import (
    is_pushed,
    mark_pushed,
    parse_dt,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHANNELS_PATH = PROJECT_ROOT / "config" / "signals_channels.yaml"


def load_channels_config() -> Dict[str, Any]:
    if not CHANNELS_PATH.exists():
        return {
            "cards_api": {
                "enabled": False,
                "base_url": "http://127.0.0.1:3851",
                "path": "/api/v1/cards",
                "api_key": "",
                "only_trade_signals": True,
                "inject_channel_message": True,
                "timeout_sec": 15,
            },
            "default_channel": {
                "channelId": "api",
                "channelName": "未映射推特源",
                "channelAvatar": "",
            },
            "channels": {},
        }
    try:
        data = yaml.safe_load(CHANNELS_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("cards_api", {})
    data.setdefault("default_channel", {})
    data.setdefault("channels", {})
    return data


def normalize_handle(author: str) -> str:
    h = (author or "").strip()
    if h.startswith("@"):
        h = h[1:]
    return h.lower()


def resolve_channel(author: str, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    cfg = cfg or load_channels_config()
    default = cfg.get("default_channel") if isinstance(cfg.get("default_channel"), dict) else {}
    channels = cfg.get("channels") if isinstance(cfg.get("channels"), dict) else {}
    handle = normalize_handle(author)
    mapped = channels.get(handle) if handle else None
    if not isinstance(mapped, dict):
        # 也允许用带 @ 的 key
        mapped = channels.get(f"@{handle}") if handle else None
    if not isinstance(mapped, dict):
        mapped = {}
    return {
        "channelId": str(mapped.get("channelId") or default.get("channelId") or "api"),
        "channelName": str(
            mapped.get("channelName") or default.get("channelName") or handle or "未映射推特源"
        ),
        "channelAvatar": str(
            mapped.get("channelAvatar") or default.get("channelAvatar") or ""
        ),
    }


def _signal_at_iso(card: Dict[str, Any]) -> str:
    raw = str(card.get("created_at") or "").strip()
    dt = parse_dt(raw)
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _image_urls(card: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for im in card.get("images") or []:
        if not isinstance(im, dict):
            continue
        # 推送用公网/原图 URL（本机 media 外部 API 访问不到）
        u = str(im.get("url") or "").strip()
        if u and u not in out:
            out.append(u)
    return out[:12]


def build_cards_payload(
    card: Dict[str, Any],
    *,
    cfg: Optional[Dict[str, Any]] = None,
    inject_channel_message: Optional[bool] = None,
) -> Dict[str, Any]:
    cfg = cfg or load_channels_config()
    api = cfg.get("cards_api") if isinstance(cfg.get("cards_api"), dict) else {}
    ch = resolve_channel(str(card.get("author") or ""), cfg)
    sig = card.get("signal") if isinstance(card.get("signal"), dict) else {}

    coins = [str(c).upper() for c in (sig.get("coins") or []) if c]
    symbol = coins[0] if coins else ""
    entries = [str(x) for x in (sig.get("entries") or []) if x]
    targets = [str(x) for x in (sig.get("take_profits") or []) if x]
    stop = str(sig.get("stop_loss") or "")
    direction = str(sig.get("direction") or "").lower()
    if direction not in ("long", "short", "flat", "watch", "unknown"):
        direction = ""

    body = str(card.get("text") or "").strip()
    if not body and sig.get("summary"):
        body = str(sig.get("summary") or "").strip()

    note_parts = []
    if card.get("url"):
        note_parts.append(str(card["url"]))
    if direction and direction not in ("unknown", ""):
        note_parts.append(f"direction={direction}")
    if sig.get("summary") and sig.get("summary") != body:
        note_parts.append(str(sig["summary"])[:120])
    if sig.get("leverage"):
        note_parts.append(f"lev={sig['leverage']}")
    if sig.get("timeframe"):
        note_parts.append(f"tf={sig['timeframe']}")

    payload: Dict[str, Any] = {
        "channelId": ch["channelId"],
        "channelName": ch["channelName"],
        "channelAvatar": ch["channelAvatar"],
        "body": body,
        "images": _image_urls(card),
        "symbol": symbol,
        "entry": entries[0] if entries else "",
        "targets": targets,
        "stopLoss": stop,
        "signalAt": _signal_at_iso(card),
        "note": " · ".join(note_parts) if note_parts else "TrendRadar list signal",
    }
    if direction in ("long", "short"):
        payload["direction"] = direction

    inject = (
        bool(inject_channel_message)
        if inject_channel_message is not None
        else bool(api.get("inject_channel_message", True))
    )
    payload["injectChannelMessage"] = inject
    return payload


def post_card(
    payload: Dict[str, Any],
    *,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = cfg or load_channels_config()
    api = cfg.get("cards_api") if isinstance(cfg.get("cards_api"), dict) else {}
    base = str(api.get("base_url") or "http://127.0.0.1:3851").rstrip("/")
    path = str(api.get("path") or "/api/v1/cards")
    if not path.startswith("/"):
        path = "/" + path
    url = f"{base}{path}"
    key = str(api.get("api_key") or "").strip()
    timeout = float(api.get("timeout_sec") or 15)

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if key:
        headers["X-Cards-Api-Key"] = key

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", 200) or 200
            try:
                body = json.loads(raw) if raw else {}
            except Exception:
                body = {"raw": raw}
            ok = status in (200, 201) and (
                body.get("ok") is True or body.get("success") is True or status == 201
            )
            return {
                "success": ok,
                "status": status,
                "response": body,
                "url": url,
            }
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try:
            parsed = json.loads(err_body) if err_body else {}
        except Exception:
            parsed = {"raw": err_body}
        return {
            "success": False,
            "status": e.code,
            "error": str(e),
            "response": parsed,
            "url": url,
        }
    except Exception as e:
        return {"success": False, "status": 0, "error": str(e), "url": url}


def push_card_if_needed(
    card: Dict[str, Any],
    *,
    force: bool = False,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    增量推送：已推送过的 tweet_id 跳过；可按 only_trade_signals 过滤。
    """
    cfg = cfg or load_channels_config()
    api = cfg.get("cards_api") if isinstance(cfg.get("cards_api"), dict) else {}
    if not api.get("enabled", True):
        return {"success": True, "skipped": True, "reason": "push_disabled"}

    tid = str(card.get("tweet_id") or "").strip()
    if tid and is_pushed(tid) and not force:
        return {"success": True, "skipped": True, "reason": "already_pushed", "tweet_id": tid}

    sig = card.get("signal") if isinstance(card.get("signal"), dict) else {}
    if api.get("only_trade_signals", True) and not sig.get("has_trade_signal"):
        if tid:
            # 非交易也记已处理推送队列，避免反复尝试
            mark_pushed([tid], status="skipped_non_trade")
        return {"success": True, "skipped": True, "reason": "non_trade", "tweet_id": tid}

    payload = build_cards_payload(card, cfg=cfg)
    result = post_card(payload, cfg=cfg)
    if result.get("success") and tid:
        mark_pushed([tid], status="ok")
    result["tweet_id"] = tid
    result["payload"] = payload
    return result


def push_cards_batch(
    cards: List[Dict[str, Any]],
    *,
    force: bool = False,
    progress=None,
) -> Dict[str, Any]:
    cfg = load_channels_config()
    api = cfg.get("cards_api") if isinstance(cfg.get("cards_api"), dict) else {}
    if not api.get("enabled", True):
        return {
            "success": True,
            "pushed": 0,
            "skipped": len(cards),
            "failed": 0,
            "reason": "push_disabled",
            "items": [],
        }

    pushed = 0
    skipped = 0
    failed = 0
    items: List[Dict[str, Any]] = []
    for card in cards:
        r = push_card_if_needed(card, force=force, cfg=cfg)
        items.append(
            {
                "tweet_id": r.get("tweet_id"),
                "success": r.get("success"),
                "skipped": r.get("skipped"),
                "reason": r.get("reason"),
                "status": r.get("status"),
                "error": r.get("error"),
            }
        )
        if r.get("skipped"):
            skipped += 1
        elif r.get("success"):
            pushed += 1
            if progress:
                try:
                    progress(f"已推送卡片 {r.get('tweet_id')} → Cards API")
                except Exception:
                    pass
        else:
            failed += 1
            if progress:
                try:
                    progress(f"推送失败 {r.get('tweet_id')}: {r.get('error') or r.get('status')}")
                except Exception:
                    pass

    return {
        "success": failed == 0,
        "pushed": pushed,
        "skipped": skipped,
        "failed": failed,
        "items": items,
    }


def channels_summary() -> Dict[str, Any]:
    cfg = load_channels_config()
    channels = cfg.get("channels") if isinstance(cfg.get("channels"), dict) else {}
    api = cfg.get("cards_api") if isinstance(cfg.get("cards_api"), dict) else {}
    return {
        "path": str(CHANNELS_PATH).replace("\\", "/"),
        "enabled": bool(api.get("enabled", True)),
        "base_url": api.get("base_url"),
        "mapped_count": len(channels),
        "handles": sorted(str(k) for k in channels.keys()),
        "default_channel": cfg.get("default_channel") or {},
        "only_trade_signals": bool(api.get("only_trade_signals", True)),
    }
