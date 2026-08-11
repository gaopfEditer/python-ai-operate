# coding=utf-8
"""帖子中文摘要：英文原文也会总结成中文。"""

from __future__ import annotations

import re
from typing import Dict

_SUMMARY_CACHE: Dict[str, str] = {}


def looks_mostly_english(text: str) -> bool:
    """粗判文本是否以英文为主。"""
    s = (text or "").strip()
    if not s:
        return False
    letters = re.findall(r"[A-Za-z]", s)
    cjk = re.findall(r"[\u4e00-\u9fff]", s)
    if not letters and not cjk:
        return False
    if not cjk:
        return len(letters) >= 8
    return len(letters) >= max(12, len(cjk) * 2)


def looks_mostly_chinese(text: str, min_cjk: int = 2) -> bool:
    """
    粗判文本是否含足够中文（资讯「仅中文」过滤用）。
    - 至少 min_cjk 个汉字
    - 且不是 looks_mostly_english（避免中英混排以英为主被误收）
    """
    s = (text or "").strip()
    if not s:
        return False
    cjk = re.findall(r"[\u4e00-\u9fff]", s)
    if len(cjk) < max(1, int(min_cjk)):
        return False
    if looks_mostly_english(s):
        return False
    return True


def _fallback_summary(text: str) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return ""
    if looks_mostly_english(s):
        # 无模型时至少截断展示，并标注需中文摘要
        cut = s[:120] + ("…" if len(s) > 120 else "")
        return f"（英文原文摘录）{cut}"
    return s[:120] + ("…" if len(s) > 120 else "")


def generate_zh_summary(title: str = "", raw: str = "", max_chars: int = 100) -> str:
    """
    生成中文内容摘要。
    - 中文原文：压缩成短摘要
    - 英文原文：翻译并总结成中文
    """
    title = (title or "").strip()
    raw = (raw or "").strip()
    source = raw if raw else title
    if not source:
        return ""

    cache_key = f"{title}\n{raw}"[:2000]
    if cache_key in _SUMMARY_CACHE:
        return _SUMMARY_CACHE[cache_key]

    is_en = looks_mostly_english(source)
    prompt = (
        "请将下列内容写成一句或两句中文摘要，不超过"
        f"{max_chars}字。只输出摘要正文，不要前缀标签。\n"
    )
    if is_en:
        prompt += "原文为英文，必须翻译并总结成中文。\n"
    else:
        prompt += "请用中文概括核心信息。\n"
    prompt += f"\n标题：{title or '(无)'}\n正文：{source[:1800]}"

    summary = ""
    try:
        from utils.ai_client import get_qwen_client

        client = get_qwen_client()
        if client.enable:
            result = client.generate(
                prompt=prompt,
                system_prompt="你是资讯编辑，擅长把社交帖子提炼成准确简洁的中文摘要。",
                temperature=0.3,
                max_tokens=220,
            )
            if result.get("success"):
                summary = re.sub(r"\s+", " ", (result.get("content") or "").strip())
                # 去掉可能的引号包裹
                if len(summary) >= 2 and summary[0] in "\"'“”" and summary[-1] in "\"'“”":
                    summary = summary[1:-1].strip()
    except Exception:
        summary = ""

    if not summary:
        summary = _fallback_summary(source)
    elif looks_mostly_english(summary) and is_en:
        # 模型偶发仍输出英文时再兜底提示
        summary = _fallback_summary(source)

    if len(summary) > max_chars + 40:
        summary = summary[: max_chars + 40].rstrip() + "…"

    _SUMMARY_CACHE[cache_key] = summary
    return summary
