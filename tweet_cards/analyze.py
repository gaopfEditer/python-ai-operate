# coding=utf-8
"""LLM：一句话摘要 / 核心论点 / 情绪与分类 Tag。"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

SYSTEM = """你是推文结构化分析器。根据推文正文，提取简洁结构化信息。
只输出 JSON：
{
  "summary": "一句话中文摘要（≤40字）",
  "core_points": ["核心论点1", "核心论点2"],
  "emotion": "情绪短词，如：兴奋/警惕/讽刺/共鸣/中立",
  "tags": ["标签1", "标签2", "标签3"],
  "category": "分类，如：行情观点/交易信号/宏观/产品/段子/其他"
}
规则：不要编造正文没有的事实；tags 2~5 个；core_points 1~3 条。
"""


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


def _fallback(text: str) -> Dict[str, Any]:
    t = (text or "").strip()
    summary = t.replace("\n", " ")[:40] + ("…" if len(t) > 40 else "")
    tags: List[str] = []
    for m in re.finditer(r"#([\w\u4e00-\u9fff]+)", t):
        tag = m.group(1)
        if tag and tag not in tags:
            tags.append(tag)
    for m in re.finditer(
        r"\b(BTC|ETH|SOL|BNB|XRP|AI|Web3)\b", t, re.I
    ):
        c = m.group(1).upper()
        if c not in tags:
            tags.append(c)
    return {
        "summary": summary or "（无正文）",
        "core_points": [summary] if summary else [],
        "emotion": "中立",
        "tags": tags[:5] or ["推文"],
        "category": "其他",
        "provider": "fallback",
    }


def analyze_tweet_text(
    text: str,
    *,
    author: str = "",
) -> Dict[str, Any]:
    prompt = f"作者：{author or '(未知)'}\n正文：\n{(text or '').strip()[:3500]}\n"
    try:
        from utils.ai_client import generate_text

        result = generate_text(
            prompt,
            system_prompt=SYSTEM,
            temperature=0.25,
            max_tokens=700,
        )
        if result.get("success"):
            data = _extract_json(str(result.get("content") or ""))
            if data.get("summary") or data.get("tags"):
                return {
                    "summary": str(data.get("summary") or "")[:80],
                    "core_points": [
                        str(x) for x in (data.get("core_points") or []) if x
                    ][:5],
                    "emotion": str(data.get("emotion") or "中立")[:20],
                    "tags": [str(x) for x in (data.get("tags") or []) if x][:8],
                    "category": str(data.get("category") or "其他")[:30],
                    "provider": str(result.get("provider") or "ai"),
                }
    except Exception:
        pass
    return _fallback(text)
