# coding=utf-8
"""交易信号展示文案（中文）。"""

from __future__ import annotations

DIRECTION_CN = {
    "long": "做多",
    "short": "做空",
    "flat": "中性",
    "watch": "观望",
    "unknown": "未知",
}

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


def normalize_direction(direction: str) -> str:
    """统一方向为 long/short/flat/watch/unknown（兼容中文）。"""
    raw = str(direction or "").strip()
    if not raw:
        return "unknown"
    if raw in DIRECTION_ALIASES:
        return DIRECTION_ALIASES[raw]
    key = raw.lower()
    if key in DIRECTION_ALIASES:
        return DIRECTION_ALIASES[key]
    if key in ("long", "short", "flat", "watch", "unknown"):
        return key
    return "unknown"


def is_trade_signal(sig: dict) -> bool:
    """有币种 + 明确做多/做空即视为交易信号（与筛选/推送一致）。"""
    if not isinstance(sig, dict):
        return False
    coins = [str(c).strip() for c in (sig.get("coins") or []) if str(c).strip()]
    direction = normalize_direction(str(sig.get("direction") or ""))
    return bool(coins) and direction in ("long", "short")

PROVIDER_CN = {
    "heuristic": "规则解析",
    "openai": "AI 解析",
    "qwen": "AI 解析",
    "dashscope": "AI 解析",
}


def direction_cn(direction: str) -> str:
    key = normalize_direction(direction)
    return DIRECTION_CN.get(key, "未知")


def direction_for_cards(direction: str) -> str:
    """Cards API direction 字段：对外只发中文。"""
    cn = direction_cn(direction)
    return "" if cn == "未知" else cn


def provider_cn(provider: str) -> str:
    key = str(provider or "").lower().strip()
    if not key:
        return "AI 解析"
    return PROVIDER_CN.get(key, "AI 解析")
