# coding=utf-8
"""Cards API 客户端：列表查询、验证任务、WebSocket 配置。"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from signals.push import load_channels_config, resolve_cards_api_key


def _api_base(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = cfg or load_channels_config()
    api = cfg.get("cards_api") if isinstance(cfg.get("cards_api"), dict) else {}
    base = str(api.get("base_url") or "http://127.0.0.1:3851").rstrip("/")
    timeout = float(api.get("timeout_sec") or 20)
    key = resolve_cards_api_key(cfg)
    return {"base": base, "timeout": timeout, "key": key, "api": api}


def _headers(key: str) -> Dict[str, str]:
    h = {"Accept": "application/json"}
    if key:
        h["X-Cards-Api-Key"] = key
        h["Authorization"] = f"Bearer {key}"
    return h


def _upstream_error_message(res: Dict[str, Any]) -> str:
    data = res.get("data") if isinstance(res.get("data"), dict) else {}
    for key in ("error", "message", "detail"):
        val = data.get(key)
        if val:
            return str(val)
    if res.get("error"):
        return str(res.get("error"))
    status = res.get("status")
    if status:
        return f"HTTP {status}"
    return "Cards API 请求失败"


def _request_json(
    method: str,
    path: str,
    *,
    query: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    meta = _api_base(cfg)
    base = meta["base"]
    if not path.startswith("/"):
        path = "/" + path
    url = base + path
    if query:
        q = urllib.parse.urlencode(
            {k: v for k, v in query.items() if v is not None and str(v) != ""}
        )
        if q:
            url = f"{url}?{q}"
    data = None
    headers = _headers(meta["key"])
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=meta["timeout"]) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", 200) or 200
            try:
                parsed = json.loads(raw) if raw else {}
            except Exception:
                parsed = {"raw": raw}
            ok = status in (200, 201, 202) and (
                parsed.get("ok") is True
                or parsed.get("success") is True
                or status in (200, 201, 202)
            )
            return {"success": ok, "status": status, "data": parsed, "url": url}
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
            "data": parsed,
            "url": url,
        }
    except Exception as e:
        return {"success": False, "status": 0, "error": str(e), "url": url}


def ws_config(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    meta = _api_base(cfg)
    base = meta["base"]
    ws_url = base.replace("https://", "wss://").replace("http://", "ws://") + "/ws"
    return {
        "ws_url": ws_url,
        "channel": "meta",
        "events": [
            "card_validate_started",
            "card_validate_progress",
            "card_validate_item",
            "card_validate_done",
            "card_validate_error",
        ],
    }


def fetch_cards(
    *,
    days: Optional[int] = None,
    channel_id: str = "",
    symbol: str = "",
    sources: str = "",
    limit: int = 200,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    q: Dict[str, Any] = {"limit": max(1, min(int(limit or 200), 500))}
    if days is not None:
        q["days"] = max(1, int(days))
    if channel_id:
        q["channelId"] = channel_id
    if symbol:
        q["symbol"] = symbol
    if sources:
        q["sources"] = sources
    res = _request_json("GET", "/api/v1/cards", query=q, cfg=cfg)
    data = res.get("data") if isinstance(res.get("data"), dict) else {}
    cards = data.get("cards") if isinstance(data.get("cards"), list) else []
    err = _upstream_error_message(res) if not res.get("success") else ""
    hint = ""
    if res.get("status") == 503 and "CARDS_API_KEY" in err:
        hint = (
            "请在 discord-collector 启动环境中设置 CARDS_API_KEY，"
            "并与 config/signals_channels.yaml 的 api_key 一致"
        )
    return {
        "success": bool(res.get("success")),
        "cards": cards,
        "total": data.get("total"),
        "filters": data.get("filters"),
        "maxId": data.get("maxId"),
        "error": err,
        "hint": hint,
        "status": res.get("status"),
        "upstream_url": res.get("url"),
    }


def fetch_channels(
    *,
    days: Optional[int] = None,
    sources: str = "",
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    q: Dict[str, Any] = {}
    if days is not None:
        q["days"] = max(1, int(days))
    if sources:
        q["sources"] = sources
    res = _request_json("GET", "/api/v1/cards/channels", query=q, cfg=cfg)
    data = res.get("data") if isinstance(res.get("data"), dict) else {}
    channels = data.get("channels") if isinstance(data.get("channels"), list) else []
    return {"success": bool(res.get("success")), "channels": channels, "error": res.get("error")}


def fetch_validate_mock_sample(*, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """静态 Mock 验证样例（立刻返回，不跑任务）。"""
    res = _request_json("GET", "/api/v1/cards/validate/mock/sample", cfg=cfg)
    data = res.get("data") if isinstance(res.get("data"), dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    err = _upstream_error_message(res) if not res.get("success") else ""
    return {
        "success": bool(res.get("success")),
        "items": items,
        "mock": True,
        "total": data.get("total") or len(items),
        "error": err,
        "status": res.get("status"),
        "upstream_url": res.get("url"),
        "raw": data,
    }


def start_validate(
    *,
    signals: Optional[List[Dict[str, Any]]] = None,
    days: Optional[int] = None,
    channel_id: str = "",
    symbol: str = "",
    sources: str = "",
    limit: int = 200,
    card_ids: Optional[List[int]] = None,
    mock: bool = False,
    mock_count: int = 8,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """POST /api/v1/cards/validate — 传入 signals 列表回测（不读写 MySQL）。"""
    if mock:
        body: Dict[str, Any] = {
            "mock": True,
            "mockCount": max(1, min(int(mock_count or 8), 20)),
        }
    elif signals:
        body = {"signals": signals[:500]}
    else:
        body = {"mockCount": max(1, min(int(mock_count or 8), 20))}
    res = _request_json("POST", "/api/v1/cards/validate", body=body, cfg=cfg)
    data = res.get("data") if isinstance(res.get("data"), dict) else {}
    job_id = str(data.get("jobId") or "")
    upstream_err = _upstream_error_message(res) if not res.get("success") else ""
    hint = str(data.get("hint") or "").strip()
    err = upstream_err or data.get("error") or res.get("error")
    if hint and hint not in str(err):
        err = f"{err} · {hint}" if err else hint
    return {
        "success": bool(res.get("success")) and bool(job_id),
        "job_id": job_id,
        "status": data.get("status"),
        "mode": data.get("mode"),
        "mock": bool(mock or data.get("mock")),
        "read_only": data.get("readOnly"),
        "window_days": data.get("windowDays"),
        "signal_count": data.get("signalCount"),
        "note": data.get("note"),
        "filters": data.get("filters"),
        "ws": data.get("ws") or ws_config(cfg),
        "poll": data.get("poll") or (f"/api/v1/cards/validate/{job_id}" if job_id else ""),
        "error": err,
        "hint": hint,
        "status_code": res.get("status"),
        "raw": data,
    }


def start_local_backtest(
    *,
    signals: Optional[List[Dict[str, Any]]] = None,
    handle: str = "",
    list_id: str = "",
    days: Optional[int] = None,
    sources: str = "x",
    symbol: str = "",
    limit: int = 200,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """按 cards-api.md 传入 signals 启动 POST /api/v1/cards/validate（回测，不建卡）。"""
    sigs = signals if isinstance(signals, list) else []
    if not sigs:
        return {
            "success": False,
            "error": "无有效回测信号（需 symbol · direction · signalAt）",
            "hint": "请确保本地卡片含交易信号（币种 + 做多/做空）",
        }
    result = start_validate(signals=sigs, cfg=cfg)
    meta = {"signal_count": len(sigs), "handle": str(handle or "").strip().lstrip("@")}
    if not result.get("success"):
        return {**result, "filters": meta}
    return {**result, "filters": result.get("filters") or meta}


def poll_validate(job_id: str, *, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    jid = str(job_id or "").strip()
    if not jid:
        return {"success": False, "error": "缺少 jobId"}
    res = _request_json("GET", f"/api/v1/cards/validate/{urllib.parse.quote(jid)}", cfg=cfg)
    data = res.get("data") if isinstance(res.get("data"), dict) else {}
    return {
        "success": bool(res.get("success")),
        "job_id": jid,
        "status": data.get("status"),
        "items": data.get("items") if isinstance(data.get("items"), list) else [],
        "errors": data.get("errors") if isinstance(data.get("errors"), list) else [],
        "error": res.get("error") or data.get("error"),
        "raw": data,
    }
