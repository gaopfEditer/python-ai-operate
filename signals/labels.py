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

PROVIDER_CN = {
    "heuristic": "规则解析",
    "openai": "AI 解析",
    "qwen": "AI 解析",
    "dashscope": "AI 解析",
}


def direction_cn(direction: str) -> str:
    key = str(direction or "").lower().strip()
    return DIRECTION_CN.get(key, key if key in DIRECTION_CN.values() else "未知")


def direction_for_cards(direction: str) -> str:
    """Cards API direction 字段：对外只发中文。"""
    cn = direction_cn(direction)
    return "" if cn == "未知" else cn


def provider_cn(provider: str) -> str:
    key = str(provider or "").lower().strip()
    if not key:
        return "AI 解析"
    return PROVIDER_CN.get(key, "AI 解析")
