# coding=utf-8
"""过滤与规则。"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from realtime_info.config import module_cfg
from realtime_info.filters.debounce import debounce_key, pass_debounce  # noqa: F401


def rule_tv(payload: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    cfg = cfg or module_cfg("tv")
    allowed = {str(x).upper() for x in (cfg.get("allowed_tfs") or [])}
    tf = str(payload.get("timeframe") or payload.get("interval") or payload.get("tf") or "").strip()
    tf_u = tf.upper().replace(" ", "")
    aliases = {"60": "1H", "240": "4H", "1H": "1H", "4H": "4H"}
    norm = aliases.get(tf_u, tf_u)
    ok_set = set()
    for a in allowed:
        ok_set.add(aliases.get(a, a))
        ok_set.add(a)
    if norm not in ok_set and tf_u not in ok_set:
        return False, f"timeframe not allowed: {tf}"
    symbol = str(payload.get("symbol") or payload.get("ticker") or "").strip()
    if not symbol:
        return False, "missing symbol"
    return True, ""


def rule_oi_funding_oi_surge(payload: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    cfg = cfg or module_cfg("oi_funding")
    oi_pct = float(payload.get("oi_change_pct") or 0)
    price_pct = abs(float(payload.get("price_change_pct") or 0))
    need_oi = float(cfg.get("oi_surge_pct") or 8)
    need_px = float(cfg.get("price_range_pct") or 1)
    if oi_pct < need_oi:
        return False, f"oi_change_pct {oi_pct} < {need_oi}"
    if price_pct > need_px:
        return False, f"price_change_pct {price_pct} > {need_px}"
    return True, ""


def rule_oi_funding_squeeze(payload: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    cfg = cfg or module_cfg("oi_funding")
    rates = payload.get("funding_rates") or []
    if not isinstance(rates, list) or len(rates) < int(cfg.get("funding_periods") or 2):
        return False, "not enough funding periods"
    thr = float(cfg.get("funding_extreme") or -0.0005)
    n = int(cfg.get("funding_periods") or 2)
    recent = [float(x) for x in rates[:n]]
    if not all(r <= thr for r in recent):
        return False, f"funding not extreme: {recent}"
    if payload.get("broke_24h_low"):
        return False, "spot broke 24h low"
    return True, ""


def rule_onchain(payload: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    cfg = cfg or module_cfg("onchain")
    if payload.get("blacklisted"):
        return False, "cex internal blacklist"
    usd = float(payload.get("usd_value") or 0)
    majors = {str(x).upper() for x in (cfg.get("major_symbols") or [])}
    sym = str(payload.get("symbol") or "").upper()
    min_usd = float(cfg.get("min_usd_major") or 5_000_000)
    if sym in majors:
        if usd < min_usd:
            return False, f"usd {usd} < {min_usd}"
        return True, ""
    circ = float(payload.get("circulating_pct") or 0)
    need = float(cfg.get("min_circulating_pct") or 0.5)
    if circ >= need:
        return True, ""
    if usd >= min_usd:
        return True, ""
    return False, f"alt circulating_pct {circ} < {need} and usd < major threshold"


def rule_liq(payload: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    cfg = cfg or module_cfg("liq")
    liq_15 = float(payload.get("liq_15m_usd") or 0)
    liq_1h = float(payload.get("liq_1h_usd") or 0)
    prox = float(payload.get("heatmap_proximity_pct") or 999)
    if liq_15 >= float(cfg.get("window_15m_usd") or 50_000_000):
        return True, ""
    if liq_1h >= float(cfg.get("window_1h_usd") or 200_000_000):
        return True, ""
    if prox <= float(cfg.get("heatmap_proximity_pct") or 1.2):
        return True, ""
    return False, "liq thresholds not met"


def rule_unlock(payload: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    cfg = cfg or module_cfg("unlock")
    usd = float(payload.get("unlock_usd") or 0)
    circ = float(payload.get("circulating_pct") or 0)
    if usd < float(cfg.get("min_usd") or 5_000_000):
        return False, "unlock_usd too small"
    if circ < float(cfg.get("min_circulating_pct") or 2.5):
        return False, "circulating_pct too small"
    return True, ""


def rule_kol_prefilter(text: str) -> bool:
    import re

    t = text or ""
    if not t.strip():
        return False
    verbs = re.search(
        r"(做多|做空|开多|开空|多单|空单|买入|卖出|long|short|buy|sell|\bTP\b|\bSL\b|突破|跌破|止损|止盈)",
        t,
        re.I,
    )
    coin = re.search(r"(\$[A-Za-z]{2,10}\b|\b(BTC|ETH|SOL|BNB|XRP|DOGE|PEPE)\b)", t, re.I)
    return bool(verbs and coin)
