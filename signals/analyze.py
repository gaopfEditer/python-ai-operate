# coding=utf-8
"""AI 解析推文中的交易信号（币种、方向、止盈止损等）。"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

SYSTEM = """你是加密货币/合约交易信号解析器。根据推文正文与配图说明，提取结构化交易信息。
只输出 JSON，不要 Markdown。字段：
{
  "has_trade_signal": true/false,
  "coins": ["BTC","ETH"],
  "direction": "long|short|flat|watch|unknown",
  "entries": ["入场价或区间"],
  "take_profits": ["TP1","TP2"],
  "stop_loss": "止损价或条件",
  "leverage": "杠杆如有",
  "timeframe": "周期如 15m/4h/日线",
  "invalidation": "失效条件",
  "confidence": 0.0到1.0,
  "summary": "一两句中文摘要，保留关键价位",
  "image_notes": "从图里读到的价位/箭头/标注（没有则空字符串）"
}
规则：
- has_trade_signal=true 必须同时满足：① 明确币种代码 coins 非空；② 明确做多/做空 direction 为 long 或 short。仅有「做多/做空」口语但无币种 → false。
- 无明确交易意图则 has_trade_signal=false，其余尽量填空。
- coins 用常见代码大写（BTC/ETH/SOL…），中文名也映射成代码。
- 若正文出现 EVM 合约地址（0x 开头十六进制）且没有明确 ticker：把该地址原样写入 coins，direction 默认 long（做多）。
- direction：做多/long/买入/点火/拉满/跟了/冲→long；做空/short/卖出→short；观望→watch；震荡/中性→flat。
- 口语里提到「多了xxx」「跟了xxx」时，xxx 常为币种代码（如 zama→ZAMA）。
- 价位原样保留，不要臆造没有的数字。
"""


# EVM 地址：完整 40 hex，也兼容推文里较短的 0x… 片段（≥6）
_ETH_ADDR_RE = re.compile(r"(?<![a-zA-Z0-9])(0x[a-fA-F0-9]{6,40})(?![a-fA-F0-9])")


def _norm_coin_token(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"0x[a-fA-F0-9]{6,40}", s):
        return s  # 保留地址大小写（常见为小写）
    return s.upper()


def _extract_contract_addresses(text: str) -> List[str]:
    seen = set()
    out: List[str] = []
    for m in _ETH_ADDR_RE.finditer(text or ""):
        addr = m.group(1)
        key = addr.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(addr)
    return out


def _extract_json(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


from signals.labels import normalize_direction


def _normalize_trade_signal(data: Dict[str, Any], *, text: str = "") -> Dict[str, Any]:
    """推送/入库判定：必须同时有币种 + 做多/做空方向。

    无 ticker 但有 0x 合约地址时：地址写入 coins，方向缺省为 long。
    """
    coins: List[str] = []
    for c in data.get("coins") or []:
        n = _norm_coin_token(str(c))
        if n and n not in coins and n.lower() not in {x.lower() for x in coins}:
            coins.append(n)
    coins = coins[:8]

    direction = normalize_direction(str(data.get("direction") or "unknown"))
    addr_filled = False
    if not coins:
        for addr in _extract_contract_addresses(text or str(data.get("summary") or "")):
            coins.append(addr)
            addr_filled = True
            if len(coins) >= 8:
                break
    if addr_filled and direction not in ("long", "short"):
        direction = "long"

    ready = bool(coins) and direction in ("long", "short")
    data["coins"] = coins
    data["direction"] = direction
    data["has_trade_signal"] = ready
    return data


def _heuristic(text: str) -> Dict[str, Any]:
    """AI 失败时的弱规则兜底。"""
    t = text or ""
    coins: List[str] = []
    for m in re.finditer(
        r"\b(BTC|ETH|SOL|BNB|XRP|DOGE|ADA|AVAX|LINK|OP|ARB|SUI|PEPE|WIF|ORDI|TON|APT|NEAR|MATIC|DOT)\b",
        t,
        re.I,
    ):
        c = _norm_coin_token(m.group(1))
        if c and c not in coins:
            coins.append(c)
    for m in re.finditer(r"\$([A-Za-z]{2,10})\b", t):
        c = _norm_coin_token(m.group(1))
        if c and c.isalpha() and c not in coins:
            coins.append(c)
    for m in re.finditer(r"多了\s*([A-Za-z]{2,12})", t, re.I):
        c = _norm_coin_token(m.group(1))
        if c and c not in coins:
            coins.append(c)
    for m in re.finditer(r"#([A-Za-z]{2,12})\b", t):
        c = _norm_coin_token(m.group(1))
        if c and c not in coins:
            coins.append(c)
    for addr in _extract_contract_addresses(t):
        if addr not in coins and addr.lower() not in {x.lower() for x in coins}:
            coins.append(addr)

    direction = "unknown"
    low = t.lower()
    if re.search(r"做多|long|看多|买入|多单|点火|拉满|跟了|冲了|上了", low, re.I):
        direction = "long"
    elif re.search(r"做空|short|看空|卖出|空单", low, re.I):
        direction = "short"
    elif re.search(r"观望|wait", low, re.I):
        direction = "watch"
    # 仅有合约地址作币种时，默认做多
    if coins and any(str(c).lower().startswith("0x") for c in coins) and direction not in (
        "long",
        "short",
    ):
        direction = "long"

    tps = re.findall(r"(?:TP|止盈)\s*[1-3]?\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)", t, re.I)
    sl_m = re.search(r"(?:SL|止损)\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)", t, re.I)
    has = bool(coins) and (
        direction in ("long", "short")
        or bool(tps)
        or bool(sl_m)
        or bool(re.search(r"止盈|止损|入场|开多|开空", t))
    )
    return _normalize_trade_signal(
        {
            "has_trade_signal": has,
            "coins": coins[:8],
            "direction": direction,
            "entries": [],
            "take_profits": tps[:5],
            "stop_loss": sl_m.group(1) if sl_m else "",
            "leverage": "",
            "timeframe": "",
            "invalidation": "",
            "confidence": 0.35 if has else 0.1,
            "summary": (t[:120] + ("…" if len(t) > 120 else "")),
            "image_notes": "",
            "provider": "heuristic",
        },
        text=t,
    )


def analyze_tweet_signal(
    *,
    text: str,
    author: str = "",
    image_alts: Optional[List[str]] = None,
    image_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    image_alts = [str(x) for x in (image_alts or []) if str(x).strip()]
    image_urls = [str(x) for x in (image_urls or []) if str(x).strip()]
    body = (text or "").strip()
    prompt = (
        f"作者：{author or '(未知)'}\n"
        f"正文：\n{body[:4000]}\n\n"
    )
    if image_alts or image_urls:
        prompt += "配图信息（请结合推断价位/标注）：\n"
        for i, alt in enumerate(image_alts[:6], 1):
            prompt += f"- 图{i} alt: {alt}\n"
        for i, u in enumerate(image_urls[:6], 1):
            prompt += f"- 图{i} url: {u}\n"
        prompt += "\n"
    prompt += "请输出 JSON。"

    provider = ""
    try:
        from utils.ai_client import generate_text

        result = generate_text(
            prompt,
            system_prompt=SYSTEM,
            temperature=0.2,
            max_tokens=900,
        )
        provider = str(result.get("provider") or "")
        if result.get("success"):
            data = _extract_json(str(result.get("content") or ""))
            if data:
                out = {
                    "has_trade_signal": bool(data.get("has_trade_signal")),
                    "coins": [
                        _norm_coin_token(str(c)) for c in (data.get("coins") or []) if str(c).strip()
                    ][:8],
                    "direction": normalize_direction(str(data.get("direction") or "unknown")),
                    "entries": [str(x) for x in (data.get("entries") or []) if x][:6],
                    "take_profits": [str(x) for x in (data.get("take_profits") or []) if x][:6],
                    "stop_loss": str(data.get("stop_loss") or ""),
                    "leverage": str(data.get("leverage") or ""),
                    "timeframe": str(data.get("timeframe") or ""),
                    "invalidation": str(data.get("invalidation") or ""),
                    "confidence": float(data.get("confidence") or 0),
                    "summary": str(data.get("summary") or ""),
                    "image_notes": str(data.get("image_notes") or ""),
                    "provider": provider or "ai",
                }
                return _normalize_trade_signal(out, text=body)
    except Exception as e:
        provider = f"error:{e}"

    h = _heuristic(body)
    h["provider"] = provider or h.get("provider") or "heuristic"
    return h
