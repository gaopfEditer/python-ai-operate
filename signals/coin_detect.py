# coding=utf-8
"""严格币种检测：产出卡片门槛（至少一个可识别 ticker / 合约地址）。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from signals.analyze import _extract_contract_addresses, _norm_coin_token

# 常见交易对后缀（正文里 BTCUSDT、ETH/USDT 等）
_PAIR_RE = re.compile(
    r"\b([A-Za-z]{2,12})(?:USDT|USDC|BUSD|FDUSD|USD)\b",
    re.I,
)
_TICKER_RE = re.compile(
    r"\b(BTC|ETH|SOL|BNB|XRP|DOGE|ADA|AVAX|LINK|OP|ARB|SUI|PEPE|WIF|ORDI|TON|APT|NEAR|MATIC|DOT|TRX|LTC|BCH|FIL|ATOM|INJ|SEI|TIA|WLD|JUP|STRK|ZEC|ZAMA)\b",
    re.I,
)
_DOLLAR_RE = re.compile(r"\$([A-Za-z]{2,10})\b")
_HASH_RE = re.compile(r"#([A-Za-z]{2,12})\b")

# 明显非币种（避免 $USD、#news 等）
_STOP = frozenset(
    {
        "USD",
        "USDT",
        "USDC",
        "BUSD",
        "FDUSD",
        "CNY",
        "EUR",
        "API",
        "NFT",
        "CEO",
        "ETF",
        "SEC",
        "FOMC",
        "CPI",
        "GDP",
        "AI",
        "OK",
        "GM",
        "KOL",
    }
)


def _dedupe_coins(coins: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for c in coins:
        n = _norm_coin_token(str(c or ""))
        if not n:
            continue
        key = n.lower()
        if key in seen:
            continue
        if n.upper() in _STOP and not n.lower().startswith("0x"):
            continue
        seen.add(key)
        out.append(n if n.lower().startswith("0x") else n.upper())
    return out[:12]


def extract_coins_strict(text: str, signal: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    从正文与已有 signal 中提取币种；无则返回空列表。
    不要求交易方向，仅要求可识别 ticker / $TAG / 交易对 / 合约地址。
    """
    t = str(text or "")
    found: List[str] = []

    sig = signal if isinstance(signal, dict) else {}
    for c in sig.get("coins") or []:
        n = _norm_coin_token(str(c))
        if n:
            found.append(n)

    for m in _TICKER_RE.finditer(t):
        found.append(m.group(1))
    for m in _DOLLAR_RE.finditer(t):
        found.append(m.group(1))
    for m in _HASH_RE.finditer(t):
        found.append(m.group(1))
    for m in _PAIR_RE.finditer(t):
        found.append(m.group(1))
    for m in re.finditer(r"多了\s*([A-Za-z]{2,12})", t, re.I):
        found.append(m.group(1))
    for m in re.finditer(r"跟了\s*([A-Za-z]{2,12})", t, re.I):
        found.append(m.group(1))
    for addr in _extract_contract_addresses(t):
        found.append(addr)

    return _dedupe_coins(found)


def has_listed_coin(text: str, signal: Optional[Dict[str, Any]] = None) -> bool:
    return bool(extract_coins_strict(text, signal))


def coin_gate_reason(text: str, signal: Optional[Dict[str, Any]] = None) -> str:
    if has_listed_coin(text, signal):
        return ""
    return "未检测到币种符号（需 $BTC、BTCUSDT、明确 ticker 或合约地址）"
