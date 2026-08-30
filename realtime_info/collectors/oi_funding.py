# coding=utf-8
"""C · Binance 公开 REST：OI 暴增 + 资金费率极值。"""

from __future__ import annotations

import logging
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from realtime_info.collectors.base import Collector
from realtime_info.config import module_cfg, module_enabled
from realtime_info.filters import rule_oi_funding_oi_surge, rule_oi_funding_squeeze
from realtime_info.pipeline import ingest_event

logger = logging.getLogger(__name__)

FAPI = "https://fapi.binance.com"


def _get_json(url: str, timeout: float = 15.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "realtime_info/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        import json

        return json.loads(resp.read().decode("utf-8"))


def fetch_oi_change_pct(symbol: str, period: str = "4h") -> Dict[str, Any]:
    """openInterestHist：对比窗口首尾估算涨跌幅。"""
    q = urllib.parse.urlencode(
        {"symbol": symbol, "period": period, "limit": 2}
    )
    data = _get_json(f"{FAPI}/futures/data/openInterestHist?{q}")
    if not isinstance(data, list) or len(data) < 2:
        return {"oi_change_pct": 0.0, "raw": data}
    a = float(data[0].get("sumOpenInterest") or data[0].get("sumOpenInterestValue") or 0)
    b = float(data[-1].get("sumOpenInterest") or data[-1].get("sumOpenInterestValue") or 0)
    pct = ((b - a) / a * 100.0) if a else 0.0
    return {"oi_change_pct": pct, "oi_start": a, "oi_end": b, "raw": data}


def fetch_price_change_pct_4h(symbol: str) -> Dict[str, Any]:
    q = urllib.parse.urlencode({"symbol": symbol, "interval": "1h", "limit": 5})
    data = _get_json(f"{FAPI}/fapi/v1/klines?{q}")
    if not isinstance(data, list) or len(data) < 5:
        return {"price_change_pct": 0.0, "raw": data}
    # 近 4 根 1h：开盘到收盘振幅相对中点
    o = float(data[1][1])
    c = float(data[-1][4])
    pct = ((c - o) / o * 100.0) if o else 0.0
    return {"price_change_pct": pct, "open": o, "close": c, "raw": data}


def fetch_funding_rates(symbol: str, limit: int = 4) -> Dict[str, Any]:
    q = urllib.parse.urlencode({"symbol": symbol, "limit": limit})
    data = _get_json(f"{FAPI}/fapi/v1/fundingRate?{q}")
    rates: List[float] = []
    if isinstance(data, list):
        # API 返回旧→新；我们要最近在前
        for row in reversed(data):
            rates.append(float(row.get("fundingRate") or 0))
    return {"funding_rates": rates, "raw": data}


def fetch_broke_24h_low(symbol: str) -> bool:
    q = urllib.parse.urlencode({"symbol": symbol})
    data = _get_json(f"{FAPI}/fapi/v1/ticker/24hr?{q}")
    if not isinstance(data, dict):
        return False
    last = float(data.get("lastPrice") or 0)
    low = float(data.get("lowPrice") or 0)
    if not last or not low:
        return False
    return last <= low * 1.001  # 贴近或破低


class OiFundingCollector(Collector):
    module = "oi_funding"

    def collect(self) -> List[Dict[str, Any]]:
        if not module_enabled("oi_funding"):
            logger.info("oi_funding disabled")
            return []
        cfg = module_cfg("oi_funding")
        symbols = list(cfg.get("symbols") or ["BTCUSDT", "ETHUSDT"])
        out: List[Dict[str, Any]] = []
        for sym in symbols:
            try:
                oi = fetch_oi_change_pct(sym)
                px = fetch_price_change_pct_4h(sym)
                fund = fetch_funding_rates(sym)
                broke = fetch_broke_24h_low(sym)
                payload = {
                    "symbol": sym,
                    "oi_change_pct": oi["oi_change_pct"],
                    "price_change_pct": px["price_change_pct"],
                    "funding_rates": fund["funding_rates"],
                    "broke_24h_low": broke,
                    "oi": oi,
                    "price": px,
                    "funding": fund,
                }
                out.append(payload)
            except Exception as e:
                logger.warning("oi_funding fetch %s failed: %s", sym, e)
        return out

    def run_and_ingest(self, *, skip_llm: bool = True, db_path=None) -> List[Dict[str, Any]]:
        results = []
        for payload in self.collect():
            sym = payload["symbol"]
            # 两种规则独立触发
            for kind, rule_fn, title_s in (
                (
                    "oi_surge",
                    rule_oi_funding_oi_surge,
                    "OI 蓄力对峙",
                ),
                (
                    "funding_squeeze",
                    rule_oi_funding_squeeze,
                    "资金费率逼空观察",
                ),
            ):
                ok, reason = rule_fn(payload)
                if not ok:
                    results.append({"symbol": sym, "kind": kind, "ok": False, "reason": reason})
                    continue
                fp = f"{sym}:{kind}".lower()
                draft = (
                    f"{sym} · {title_s}\n"
                    f"OI 4h 变动 {payload['oi_change_pct']:.2f}% · "
                    f"价格 {payload['price_change_pct']:.2f}%\n"
                    f"Funding 近端: {payload.get('funding_rates')}\n"
                    f"非投资建议。"
                )
                r = ingest_event(
                    module="oi_funding",
                    fingerprint=fp,
                    raw={**payload, "kind": kind},
                    title=f"[{sym}] {title_s}",
                    draft_text=draft,
                    severity="warn",
                    skip_llm=skip_llm,
                    db_path=db_path,
                )
                results.append({"symbol": sym, "kind": kind, **{k: r.get(k) for k in ("ok", "skipped")}, "event_id": getattr(r.get("event"), "id", None)})
        return results


def run_oi_funding_once(*, skip_llm: bool = True, db_path=None) -> List[Dict[str, Any]]:
    return OiFundingCollector().run_and_ingest(skip_llm=skip_llm, db_path=db_path)
