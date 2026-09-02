# coding=utf-8
"""LLM 价值评估：Ollama 优先，DeepSeek 备用。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

WEIGHT_DEPTH = 0.30
WEIGHT_STRUCTURE = 0.30
WEIGHT_ACTION = 0.40

SYSTEM = """你是内容价值评审。根据贴文（及可选相似摘要）打分，只输出 JSON：
{
  "depth": 0-10,
  "structure": 0-10,
  "actionability": 0-10,
  "category": "insight|playbook|news|opinion|noise|other",
  "format": "thread|single|list|case|other",
  "incremental_value": "一句话增量价值",
  "is_recommended": true/false,
  "reason": "简短理由",
  "key_takeaways": ["要点1", "要点2"]
}
维度：
- depth 思想深度
- structure 结构化程度
- actionability 可落实性/实操价值
不要输出 Markdown。"""


def _clamp(n: float, lo: float = 0.0, hi: float = 10.0) -> float:
    try:
        v = float(n)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, v))


def weighted_score(depth: float, structure: float, actionability: float) -> float:
    s = (
        WEIGHT_DEPTH * _clamp(depth)
        + WEIGHT_STRUCTURE * _clamp(structure)
        + WEIGHT_ACTION * _clamp(actionability)
    )
    return round(s, 2)


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


def _heuristic(tweet: Dict[str, Any]) -> Dict[str, Any]:
    text = str(tweet.get("text") or "")
    n = len(re.sub(r"\s+", "", text))
    has_list = bool(re.search(r"(^|\n)\s*([-*•]|\d+[\.\)])\s+", text))
    has_link = bool(re.search(r"https?://", text, re.I))
    depth = 4.0 + (2.0 if n > 200 else 0) + (1.0 if "因为" in text or "所以" in text else 0)
    structure = 6.0 if has_list else (4.0 + (1.5 if n > 150 else 0))
    action = 5.0 + (2.0 if has_list else 0) + (1.0 if has_link else 0)
    depth, structure, action = _clamp(depth), _clamp(structure), _clamp(action)
    score = weighted_score(depth, structure, action)
    return {
        "depth": depth,
        "structure": structure,
        "actionability": action,
        "score": score,
        "category": "insight" if score >= 6 else "opinion",
        "format": "list" if has_list else "single",
        "incremental_value": "启发式粗评（LLM 不可用）",
        "is_recommended": score >= 7.0,
        "reason": "fallback heuristic",
        "key_takeaways": [text[:80]] if text else [],
        "provider": "heuristic",
    }


def _call_llm(prompt: str, system: str) -> Dict[str, Any]:
    """强制 Ollama → DeepSeek，不改全局 prefer。"""
    from utils.ai_client import get_deepseek_client, get_ollama_client

    try:
        r = get_ollama_client().generate(
            prompt, system_prompt=system, temperature=0.2, max_tokens=900
        )
        if r.get("success"):
            r = dict(r)
            r.setdefault("provider", "ollama")
            return r
        logger.warning("value evaluator ollama fail: %s", r.get("error"))
    except Exception as e:
        logger.warning("value evaluator ollama exc: %s", e)
        r = {"success": False, "error": str(e)}

    try:
        r2 = get_deepseek_client().generate(
            prompt, system_prompt=system, temperature=0.2, max_tokens=900
        )
        if r2.get("success"):
            r2 = dict(r2)
            r2.setdefault("provider", "deepseek")
            return r2
        return r2
    except Exception as e:
        return {"success": False, "error": str(e)}


def evaluate_tweet(
    tweet: Dict[str, Any],
    *,
    similar_summaries: Optional[List[str]] = None,
) -> Dict[str, Any]:
    text = str(tweet.get("text") or "").strip()
    author = str(tweet.get("author") or "")
    sims = [str(s).strip() for s in (similar_summaries or []) if str(s).strip()][:3]
    user = f"作者: {author}\n正文:\n{text[:3500]}\n"
    if sims:
        user += "\n历史相似摘要:\n" + "\n".join(f"- {s[:200]}" for s in sims)

    result = _call_llm(user, SYSTEM)
    if not result.get("success"):
        out = _heuristic(tweet)
        out["ai_error"] = str(result.get("error") or "LLM 失败")
        return out

    payload = _extract_json(str(result.get("content") or ""))
    if not payload:
        out = _heuristic(tweet)
        out["provider"] = str(result.get("provider") or "")
        out["ai_error"] = "JSON 解析失败"
        return out

    depth = _clamp(payload.get("depth", 5))
    structure = _clamp(payload.get("structure", 5))
    action = _clamp(payload.get("actionability", 5))
    score = weighted_score(depth, structure, action)
    takeaways = payload.get("key_takeaways")
    if not isinstance(takeaways, list):
        takeaways = []
    takeaways = [str(x).strip() for x in takeaways if str(x).strip()][:6]
    is_rec = payload.get("is_recommended")
    if is_rec is None:
        is_rec = score >= 7.0

    return {
        "depth": depth,
        "structure": structure,
        "actionability": action,
        "score": score,
        "category": str(payload.get("category") or "other")[:40],
        "format": str(payload.get("format") or "other")[:40],
        "incremental_value": str(payload.get("incremental_value") or "")[:200],
        "is_recommended": bool(is_rec),
        "reason": str(payload.get("reason") or "")[:300],
        "key_takeaways": takeaways,
        "provider": str(result.get("provider") or ""),
    }
