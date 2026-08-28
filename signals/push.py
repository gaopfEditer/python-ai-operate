# coding=utf-8
"""解析后的增量信号 → Cards API 推送。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from signals.labels import (
    direction_cn,
    direction_for_cards,
    is_trade_signal,
    normalize_direction,
    provider_cn,
)
from signals.store import (
    is_pushed,
    mark_pushed,
    parse_dt,
)
from signals.tweet_log import (
    fmt_beijing_iso,
    resolve_display_time,
    strip_time_prefix,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHANNELS_PATH = PROJECT_ROOT / "config" / "signals_channels.yaml"
CARDS_SOURCE_APP = "python-ai-operate"
DEFAULT_CARDS_API_KEY = "Gpf123456"


def signal_ready_for_cards(sig: Dict[str, Any]) -> bool:
    """Cards API 仅推送：有币种 + 明确做多/做空。"""
    return is_trade_signal(sig)


def format_cards_source(origin: str = "", *, cfg: Optional[Dict[str, Any]] = None) -> str:
    """
    Cards API source 统一为 python-ai-operate:<来源>，例如 python-ai-operate:x。
    配置里 source / source_origin 填来源后缀即可（如 x）。
    """
    api = {}
    if cfg and isinstance(cfg.get("cards_api"), dict):
        api = cfg["cards_api"]
    raw = str(origin or api.get("source_origin") or api.get("source") or "x").strip()
    if raw.startswith(f"{CARDS_SOURCE_APP}:"):
        return raw
    if raw == CARDS_SOURCE_APP:
        raw = "x"
    suffix = raw.lstrip(":").strip() or "x"
    return f"{CARDS_SOURCE_APP}:{suffix}"


def cards_api_source_platform(*, cfg: Optional[Dict[str, Any]] = None) -> str:
    """开放 API POST /api/v1/cards 的 source 字段（见 cards-api.md：x / telegram …）。"""
    api = {}
    if cfg and isinstance(cfg.get("cards_api"), dict):
        api = cfg["cards_api"]
    raw = str(api.get("source_origin") or api.get("source") or "x").strip()
    if raw.startswith(f"{CARDS_SOURCE_APP}:"):
        raw = raw.split(":", 1)[-1].strip()
    return raw or "x"


def resolve_cards_api_key(cfg: Optional[Dict[str, Any]] = None) -> str:
    """环境变量 CARDS_API_KEY 优先，其次 signals_channels.yaml 的 api_key。"""
    env = os.environ.get("CARDS_API_KEY", "").strip()
    if env:
        return env
    cfg = cfg or load_channels_config()
    api = cfg.get("cards_api") if isinstance(cfg.get("cards_api"), dict) else {}
    return str(api.get("api_key") or DEFAULT_CARDS_API_KEY).strip()


def load_channels_config() -> Dict[str, Any]:
    if not CHANNELS_PATH.exists():
        return {
            "cards_api": {
                "enabled": False,
                "base_url": "http://127.0.0.1:3851",
                "path": "/api/v1/cards",
                "api_key": DEFAULT_CARDS_API_KEY,
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
    # 兼容旧版独立 bloggers：合并进 channels（不覆盖已有字段）
    legacy = data.get("bloggers") if isinstance(data.get("bloggers"), dict) else {}
    channels = data["channels"] if isinstance(data["channels"], dict) else {}
    for key, val in legacy.items():
        if not isinstance(val, dict):
            continue
        bid = normalize_handle(str(val.get("id") or key))
        if not bid:
            continue
        existing = channels.get(bid) if isinstance(channels.get(bid), dict) else None
        if existing is None:
            for ck, cv in list(channels.items()):
                if normalize_handle(str(ck)) == bid and isinstance(cv, dict):
                    existing = cv
                    bid = normalize_handle(str(ck))
                    break
        if existing is None:
            channels[bid] = dict(val)
            continue
        for field in ("name", "aliases", "enabled", "profile_url", "url", "notes"):
            if field in val and field not in existing:
                existing[field] = val[field]
        if val.get("name") and not existing.get("channelName"):
            existing["channelName"] = val["name"]
    data["channels"] = channels
    return data


def list_bloggers(cfg: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    从 channels 合一配置读取博主回溯名单。
    id = X handle；默认 profile_url = https://x.com/{id}；enabled=false 跳过。
    """
    cfg = cfg or load_channels_config()
    raw = cfg.get("channels") if isinstance(cfg.get("channels"), dict) else {}
    rows: List[Dict[str, Any]] = []
    for key, val in raw.items():
        if not isinstance(val, dict):
            continue
        if val.get("enabled") is False:
            continue
        bid = normalize_handle(str(val.get("id") or key))
        if not bid:
            continue
        profile = str(val.get("profile_url") or val.get("url") or "").strip()
        if not profile:
            profile = f"https://x.com/{bid}"
        aliases = val.get("aliases") if isinstance(val.get("aliases"), list) else []
        name = str(val.get("name") or val.get("channelName") or bid)
        rows.append(
            {
                "id": bid,
                "handle": bid,
                "name": name,
                "aliases": [str(a).strip() for a in aliases if str(a).strip()],
                "profile_url": profile,
                "channelId": str(val.get("channelId") or ""),
                "channelName": str(val.get("channelName") or name),
                "notes": str(val.get("notes") or ""),
            }
        )
    rows.sort(key=lambda x: (x.get("name") or x.get("id") or "").lower())
    return rows


def bloggers_summary() -> Dict[str, Any]:
    rows = list_bloggers()
    return {
        "path": str(CHANNELS_PATH).replace("\\", "/"),
        "count": len(rows),
        "items": rows,
        "ids": [r["id"] for r in rows],
    }


def resolve_blogger_targets(
    *,
    handles: Optional[List[Any]] = None,
    profile_url: str = "",
    user_handle: str = "",
    cfg: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """将请求中的 handles / 链接 解析为去重后的 [{id, profile_url, name}]。"""
    from signals.store import parse_user_handle, user_profile_url

    cfg = cfg or load_channels_config()
    catalog = {b["id"]: b for b in list_bloggers(cfg)}
    out: List[Dict[str, str]] = []
    seen: set = set()

    def _add(raw: str, name: str = "") -> None:
        h = normalize_handle(parse_user_handle(raw) or raw)
        if not h or h in seen:
            return
        seen.add(h)
        meta = catalog.get(h) or {}
        out.append(
            {
                "id": h,
                "handle": h,
                "name": str(name or meta.get("name") or h),
                "profile_url": str(meta.get("profile_url") or user_profile_url(h)),
            }
        )

    for item in handles or []:
        if isinstance(item, dict):
            _add(
                str(item.get("id") or item.get("handle") or item.get("profile_url") or ""),
                str(item.get("name") or ""),
            )
        else:
            _add(str(item or ""))

    if profile_url or user_handle:
        _add(str(profile_url or user_handle))

    return out


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
    mapped: Any = None
    if handle:
        mapped = channels.get(handle)
        if not isinstance(mapped, dict):
            mapped = channels.get(f"@{handle}")
        if not isinstance(mapped, dict):
            for k, v in channels.items():
                if normalize_handle(str(k)) == handle and isinstance(v, dict):
                    mapped = v
                    break
    if not isinstance(mapped, dict):
        mapped = {}
    channel_name = str(
        mapped.get("channelName")
        or mapped.get("name")
        or default.get("channelName")
        or handle
        or "未映射推特源"
    )
    return {
        "handle": handle,
        "channelId": str(mapped.get("channelId") or default.get("channelId") or "api"),
        "channelName": channel_name,
        "channelAvatar": str(
            mapped.get("channelAvatar") or default.get("channelAvatar") or ""
        ),
        "mapped": bool(mapped.get("channelId")),
    }


def _signal_at_iso(card: Dict[str, Any]) -> str:
    """Cards API signalAt：UTC ISO（与 cards-api.md 示例一致）。"""
    raw = str(card.get("created_at") or "").strip()
    dt = parse_dt(raw)
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    ms = int(dt.microsecond / 1000)
    return dt.strftime(f"%Y-%m-%dT%H:%M:%S.{ms:03d}Z")


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
    body = strip_time_prefix(body)

    time_s = resolve_display_time(
        str(card.get("created_at") or ""),
        str(card.get("time_label") or ""),
        str(card.get("parsed_at") or ""),
    )

    note_parts = [f"发帖时间={time_s}（北京时间）"]
    if card.get("url"):
        note_parts.append(str(card["url"]))
    dir_cn = direction_cn(direction)
    if dir_cn and dir_cn != "未知":
        note_parts.append(f"方向={dir_cn}")
    if sig.get("summary") and sig.get("summary") != body:
        note_parts.append(str(sig["summary"])[:120])
    if sig.get("leverage"):
        note_parts.append(f"杠杆={sig['leverage']}")
    if sig.get("timeframe"):
        note_parts.append(f"周期={sig['timeframe']}")
    if (sig.get("entries") or [])[:1]:
        note_parts.append(f"入场={sig['entries'][0]}")
    if (sig.get("take_profits") or [])[:2]:
        note_parts.append(f"止盈={' / '.join(str(x) for x in sig['take_profits'][:2])}")
    if sig.get("stop_loss"):
        note_parts.append(f"止损={sig['stop_loss']}")

    payload: Dict[str, Any] = {
        "channelId": ch["channelId"],
        "channelName": ch["channelName"],
        "channelAvatar": ch["channelAvatar"],
        "source": cards_api_source_platform(cfg=cfg),
        "body": body,
        "images": _image_urls(card),
        "symbol": symbol,
        "entry": entries[0] if entries else "",
        "targets": targets,
        "stopLoss": stop,
        "signalAt": _signal_at_iso(card),
        "note": " · ".join(note_parts) if note_parts else "列表交易信号",
    }
    if direction in ("long", "short"):
        payload["direction"] = direction

    inject = (
        bool(inject_channel_message)
        if inject_channel_message is not None
        else bool(api.get("inject_channel_message", True))
    )
    payload["injectChannelMessage"] = inject
    tid = str(card.get("tweet_id") or "").strip()
    if tid:
        payload["messageId"] = f"x-{tid}"
        payload["sourceRef"] = tid
    return payload


def _mask_secret(value: str, show: int = 4) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    if len(s) <= show * 2:
        return "***"
    return f"{s[:show]}...{s[-show:]}"


def _error_detail(status: Any, error: Any, response: Any) -> str:
    parts: List[str] = []
    if status:
        parts.append(f"HTTP {status}")
    if error:
        parts.append(str(error))
    if isinstance(response, dict):
        for key in ("error", "message", "detail", "msg", "reason", "hint"):
            val = response.get(key)
            if val not in (None, ""):
                parts.append(f"{key}={val}")
        raw = response.get("raw")
        if raw and not any(k in response for k in ("error", "message", "detail", "msg")):
            parts.append(f"raw={str(raw)[:800]}")
    return " · ".join(parts) if parts else "未知错误"


def _friendly_cards_api_error(status: Any, error: Any, response: Any) -> str:
    blob = _error_detail(status, error, response)
    low = blob.lower()
    if "cards_by_style" in low or "signalcardtoclient" in low:
        return (
            "Cards API 已连通，但 discord-collector 未写入 MySQL（collect:ui 离线模式）。"
            " POST /api/v1/cards 需要 MySQL 持久化；请启动 MySQL 并重启 pnpm run collect:ui。"
            f" 原始错误：{blob}"
        )
    if status == 503 or "mysql" in low or "离线" in blob:
        return (
            "Cards API MySQL 不可用，无法建卡。请检查 discord-collector 的 MYSQL_* 配置并启动 MySQL。"
            f" 详情：{blob}"
        )
    return blob


def build_request_meta(
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
    key = resolve_cards_api_key(cfg)
    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if key:
        headers["X-Cards-Api-Key"] = _mask_secret(key)
    return {
        "method": "POST",
        "url": url,
        "headers": headers,
        "body": payload,
    }


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
    key = resolve_cards_api_key(cfg)
    timeout = float(api.get("timeout_sec") or 15)
    request_meta = build_request_meta(payload, cfg=cfg)

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
            out = {
                "success": ok,
                "status": status,
                "response": body,
                "url": url,
                "request": request_meta,
                "payload": payload,
            }
            if not ok:
                out["error"] = _error_detail(status, None, body)
                out["error_detail"] = _friendly_cards_api_error(status, None, body)
            return out
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try:
            parsed = json.loads(err_body) if err_body else {}
        except Exception:
            parsed = {"raw": err_body}
        detail = _friendly_cards_api_error(e.code, str(e), parsed)
        return {
            "success": False,
            "status": e.code,
            "error": str(e),
            "error_detail": detail,
            "response": parsed,
            "url": url,
            "request": request_meta,
            "payload": payload,
        }
    except Exception as e:
        detail = _error_detail(0, str(e), None)
        return {
            "success": False,
            "status": 0,
            "error": str(e),
            "error_detail": detail,
            "url": url,
            "request": request_meta,
            "payload": payload,
        }


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
    if api.get("only_trade_signals", True) and not is_trade_signal(sig):
        if tid:
            # 非交易也记已处理推送队列，避免反复尝试
            mark_pushed([tid], status="skipped_non_trade")
        return {"success": True, "skipped": True, "reason": "non_trade", "tweet_id": tid}

    if not signal_ready_for_cards(sig):
        if tid:
            mark_pushed([tid], status="skipped_incomplete")
        return {
            "success": True,
            "skipped": True,
            "reason": "missing_coin_or_direction",
            "tweet_id": tid,
        }

    payload = build_cards_payload(card, cfg=cfg)
    result = post_card(payload, cfg=cfg)
    resp = result.get("response") if isinstance(result.get("response"), dict) else {}
    card_obj = resp.get("card") if isinstance(resp.get("card"), dict) else {}
    remote_id = card_obj.get("id")
    if remote_id is not None:
        try:
            result["cards_api_id"] = int(remote_id)
        except (TypeError, ValueError):
            pass
    if result.get("success") and tid:
        mark_pushed([tid], status="ok")
        remote_id = result.get("cards_api_id")
        if remote_id:
            try:
                from signals.store import save_card_remote_id

                save_card_remote_id(tid, int(remote_id))
            except Exception:
                pass
    result["tweet_id"] = tid
    result["payload"] = payload
    result["channel"] = {
        "channelId": payload.get("channelId"),
        "channelName": payload.get("channelName"),
        "handle": normalize_handle(str(card.get("author") or "")),
    }
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
        ch = r.get("channel") or {}
        items.append(
            {
                "tweet_id": r.get("tweet_id"),
                "author": card.get("author"),
                "success": r.get("success"),
                "skipped": r.get("skipped"),
                "reason": r.get("reason"),
                "status": r.get("status"),
                "error": r.get("error"),
                "channelId": ch.get("channelId") or (r.get("payload") or {}).get("channelId"),
                "channelName": ch.get("channelName")
                or (r.get("payload") or {}).get("channelName"),
            }
        )
        if r.get("skipped"):
            skipped += 1
            if progress and r.get("reason") == "non_trade":
                try:
                    progress(
                        f"跳过非交易 {card.get('author') or r.get('tweet_id')}"
                    )
                except Exception:
                    pass
            elif progress and r.get("reason") == "missing_coin_or_direction":
                try:
                    sig = card.get("signal") if isinstance(card.get("signal"), dict) else {}
                    coins = ",".join(sig.get("coins") or []) or "无币种"
                    direction = str(sig.get("direction") or "unknown")
                    progress(
                        f"跳过推送（缺币种或方向） @{card.get('author') or r.get('tweet_id')} "
                        f"· 币种={coins} · 方向={direction}"
                    )
                except Exception:
                    pass
        elif r.get("success"):
            pushed += 1
            if progress:
                try:
                    progress(
                        f"已推送交易信号 → 频道 {ch.get('channelName') or '?'} "
                        f"({ch.get('channelId') or '?'}) · @{ch.get('handle') or card.get('author')}"
                    )
                except Exception:
                    pass
        else:
            failed += 1
            if progress:
                try:
                    progress(
                        f"推送失败 @{card.get('author') or r.get('tweet_id')}: "
                        f"{r.get('error') or r.get('status')}"
                    )
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
    rows = []
    for k, v in channels.items():
        if not isinstance(v, dict):
            continue
        rows.append(
            {
                "handle": normalize_handle(str(k)),
                "channelId": str(v.get("channelId") or ""),
                "channelName": str(v.get("channelName") or v.get("name") or ""),
            }
        )
    rows.sort(key=lambda x: x["handle"])
    return {
        "path": str(CHANNELS_PATH).replace("\\", "/"),
        "enabled": bool(api.get("enabled", True)),
        "base_url": api.get("base_url"),
        "mapped_count": len(rows),
        "handles": [r["handle"] for r in rows],
        "mappings": rows,
        "default_channel": cfg.get("default_channel") or {},
        "only_trade_signals": bool(api.get("only_trade_signals", True)),
    }


def enrich_card_channel(card: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """给卡片附上频道映射，供前端 sig-author 展示。"""
    out = dict(card)
    ch = resolve_channel(str(card.get("author") or ""), cfg)
    out["channel"] = ch
    out["display_time"] = resolve_display_time(
        str(card.get("created_at") or ""),
        str(card.get("time_label") or ""),
        str(card.get("parsed_at") or ""),
        fallback_now=True,
    )
    return out


def build_test_payload(
    *,
    handle: str = "",
    channel_id: str = "",
    channel_name: str = "",
    body: str = "",
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    测试推送：仅正文 → AI 解析交易信号 → 组装 Cards API 请求体。
    返回 {"payload": ..., "signal": ...}
    """
    from signals.analyze import analyze_tweet_signal

    cfg = cfg or load_channels_config()
    text = (body or "").strip()
    if not text:
        raise ValueError("请填写测试正文")

    handle_norm = normalize_handle(handle)
    author = f"@{handle_norm}" if handle_norm else ""
    signal = analyze_tweet_signal(text=text, author=author)
    now = datetime.now(timezone.utc)

    card: Dict[str, Any] = {
        "author": author,
        "text": text,
        "created_at": now.isoformat(),
        "parsed_at": now.astimezone().isoformat(timespec="seconds"),
        "signal": signal,
        "url": "",
        "images": [],
    }
    payload = build_cards_payload(card, cfg=cfg)

    ch = resolve_channel(handle, cfg) if handle else {}
    if str(channel_id or "").strip():
        payload["channelId"] = str(channel_id).strip()
    elif ch.get("channelId"):
        payload["channelId"] = ch["channelId"]
    if str(channel_name or "").strip():
        payload["channelName"] = str(channel_name).strip()
    elif ch.get("channelName"):
        payload["channelName"] = ch["channelName"]

    time_s = resolve_display_time(
        str(card.get("created_at") or ""),
        "",
        str(card.get("parsed_at") or ""),
    )
    coins = ",".join(str(c) for c in (signal.get("coins") or [])[:6]) or "-"
    dir_s = direction_cn(str(signal.get("direction") or "unknown"))
    sig_flag = "有交易信号" if signal.get("has_trade_signal") else "无交易信号"
    payload["note"] = (
        f"测试推送 · @{handle_norm or '手动'} · "
        f"{sig_flag} · 币种={coins} · 方向={dir_s} · "
        f"{provider_cn(str(signal.get('provider') or ''))} · 发帖时间={time_s}"
    )
    return {"payload": payload, "signal": signal}


def push_test_message(
    *,
    handle: str = "",
    channel_id: str = "",
    channel_name: str = "",
    body: str = "",
    dry_run: bool = False,
    all_mapped: bool = False,
) -> Dict[str, Any]:
    """
    测试推送：按映射表解析频道后 POST Cards API。
    dry_run=True 只返回 payload，不请求。
    all_mapped=True 时对 yaml 里每个映射各发一条（忽略 handle）。
    """
    cfg = load_channels_config()
    api = cfg.get("cards_api") if isinstance(cfg.get("cards_api"), dict) else {}
    if not api.get("enabled", True) and not dry_run:
        return {"success": False, "error": "cards_api.enabled=false，请先在 signals_channels.yaml 开启"}

    jobs: List[Dict[str, str]] = []
    if all_mapped:
        channels = cfg.get("channels") if isinstance(cfg.get("channels"), dict) else {}
        for k, v in channels.items():
            if not isinstance(v, dict):
                continue
            jobs.append(
                {
                    "handle": normalize_handle(str(k)),
                    "channel_id": str(v.get("channelId") or ""),
                    "channel_name": str(v.get("channelName") or v.get("name") or ""),
                }
            )
        if not jobs:
            return {"success": False, "error": "映射表为空，请先在 signals_channels.yaml 配置 channels"}
    else:
        jobs.append(
            {
                "handle": normalize_handle(handle),
                "channel_id": channel_id,
                "channel_name": channel_name,
            }
        )

    results: List[Dict[str, Any]] = []
    ok_n = 0
    fail_n = 0
    for job in jobs:
        try:
            built = build_test_payload(
                handle=job.get("handle") or "",
                channel_id=job.get("channel_id") or "",
                channel_name=job.get("channel_name") or "",
                body=body,
                cfg=cfg,
            )
        except ValueError as e:
            return {"success": False, "error": str(e), "items": []}
        payload = built["payload"]
        signal = built.get("signal") or {}
        item: Dict[str, Any] = {
            "handle": job.get("handle") or "",
            "channelId": payload.get("channelId"),
            "channelName": payload.get("channelName"),
            "payload": payload,
            "signal": signal,
            "dry_run": dry_run,
        }
        if dry_run:
            item["success"] = True
            item["skipped"] = True
            item["reason"] = "dry_run"
            ok_n += 1
        else:
            posted = post_card(payload, cfg=cfg)
            item.update(posted)
            if not posted.get("success"):
                item["error_detail"] = posted.get("error_detail") or posted.get("error")
            if posted.get("success"):
                ok_n += 1
            else:
                fail_n += 1
        results.append(item)

    return {
        "success": fail_n == 0,
        "dry_run": dry_run,
        "sent": ok_n if not dry_run else 0,
        "previewed": ok_n if dry_run else 0,
        "failed": fail_n,
        "items": results,
        "api": {
            "base_url": api.get("base_url"),
            "path": api.get("path"),
            "enabled": bool(api.get("enabled", True)),
        },
    }