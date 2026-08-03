# coding=utf-8
"""
吸引力要素分析（第二阶段占位）

对归档库中「中位数以上 / 手动精选」素材，抽取 hook / emotion / structure 等要素，
供后续结合最新热点做创作参考。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from allnews_mornitor import store
from allnews_mornitor.models import ArchiveRecord


FACTOR_PROMPT = """你是内容增长分析师。分析下列高互动帖子，提炼可复用的吸引力要素。
只输出 JSON：
{
  "hook": "开头如何抓住注意力",
  "emotion": "触发的情绪",
  "structure": "结构/节奏特点",
  "proof": "证据或案例用法",
  "cta": "互动引导方式",
  "keywords": ["关键词1", "关键词2"],
  "why_median_plus": "为何能高于平台中位互动"
}
"""


def analyze_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """对单条归档做要素分析；优先本地 Ollama。"""
    cfg = store.load_config().get("creation") or {}
    if not cfg.get("use_project_ai", True):
        return {"success": False, "error": "已关闭 AI 分析"}

    try:
        from utils.ai_client import generate_text
    except Exception as e:
        return {"success": False, "error": f"无法加载 AI 客户端: {e}"}

    body = (
        f"平台: {record.get('platform')}\n"
        f"标题: {record.get('title')}\n"
        f"点赞: {record.get('likes')} 评论: {record.get('comments')}\n"
        f"摘要: {(record.get('summary') or record.get('content') or '')[:1200]}\n"
        f"链接: {record.get('url')}\n"
    )
    result = generate_text(body, system_prompt=FACTOR_PROMPT, temperature=0.3, max_tokens=1200)
    if not result.get("success"):
        return {"success": False, "error": result.get("error") or "分析失败"}

    text = result.get("content") or ""
    factors: Dict[str, Any] = {"raw": text}
    try:
        import re

        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            factors = json.loads(m.group(0))
    except Exception:
        pass

    # 写回归档
    store.update_archive_item(str(record.get("post_id")), {"factors": factors})

    return {
        "success": True,
        "provider": result.get("provider"),
        "factors": factors,
    }


def list_material_for_creation(limit: int = 30) -> List[Dict[str, Any]]:
    """给创作侧用的素材列表：优先有 factors 的归档。"""
    items = store.load_archive()
    items.sort(
        key=lambda x: (
            1 if x.get("factors") else 0,
            float(x.get("score") or 0),
            int(x.get("likes") or 0),
        ),
        reverse=True,
    )
    return items[: max(1, limit)]
