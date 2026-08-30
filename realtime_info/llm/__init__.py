# coding=utf-8
"""LLM 结构化提取（可选；失败则规则草稿）。"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from realtime_info.config import load_settings


SYSTEM = (
    "你是加密货币交易资讯编辑。根据原始事件输出严格 JSON，"
    "字段：title, draft_text, severity(info|warn|high), summary。"
    "draft_text 为可发 X 短帖中文草稿，禁止保证收益，用概率语言。"
    "只输出 JSON 对象，不要 markdown。"
)


def _parse_json(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else {}
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return {}
    try:
        out = json.loads(m.group(0))
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def enrich_with_llm(
    *,
    module: str,
    raw: Dict[str, Any],
    fallback_title: str,
    fallback_draft: str,
) -> Dict[str, Any]:
    cfg = load_settings()
    llm_cfg = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    if not llm_cfg.get("enabled", True):
        return {
            "title": fallback_title,
            "draft_text": fallback_draft,
            "severity": "info",
            "extracted": {"source": "rule_fallback"},
        }
    try:
        from utils.ai_client import QwenClient

        client = QwenClient()
        prompt = (
            f"模块: {module}\n"
            f"原始事件 JSON:\n{json.dumps(raw, ensure_ascii=False)[:4000]}\n"
            f"参考标题: {fallback_title}\n"
            f"参考草稿: {fallback_draft}\n"
        )
        result = client.generate(
            prompt,
            system_prompt=SYSTEM,
            temperature=0.3,
            max_tokens=800,
        )
        if not result.get("success"):
            raise RuntimeError(result.get("error") or "llm failed")
        parsed = _parse_json(str(result.get("content") or ""))
        title = str(parsed.get("title") or fallback_title).strip() or fallback_title
        draft = str(parsed.get("draft_text") or fallback_draft).strip() or fallback_draft
        severity = str(parsed.get("severity") or "info").strip() or "info"
        if severity not in ("info", "warn", "high"):
            severity = "info"
        return {
            "title": title,
            "draft_text": draft,
            "severity": severity,
            "extracted": {**parsed, "source": "llm"},
        }
    except Exception as e:
        if not llm_cfg.get("fallback_draft", True):
            raise
        return {
            "title": fallback_title,
            "draft_text": fallback_draft,
            "severity": "info",
            "extracted": {"source": "rule_fallback", "error": str(e)[:200]},
        }
