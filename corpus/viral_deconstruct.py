# coding=utf-8
"""爆款帖四要素拆解：标签化 + 结构化，写入语料库。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from corpus.db import create_template, init_db, update_template
from corpus.taxonomy import (
    normalize_tags,
    tags_as_list,
    taxonomy_prompt_block,
)

VIRAL_DECONSTRUCT_SYSTEM = f"""你是爆款内容拆解专家。把热门帖子炼成可被 AI 重组的「语料要素」：抽象化（标签）+ 模版化（结构）。
只输出一个 JSON 对象，不要 markdown，不要解释。

输出 Schema：
{{
  "domain": "Web3交易 或 泛娱乐",
  "tags": {{"primary": "一级标签", "secondary": "二级标签"}},
  "elements": {{
    "format": "Long-form / Short-form / Long-form Thread 等",
    "hook_type": "Hook 模式，如反直觉/制造焦虑/利益诱惑/打脸反转…",
    "hook_content": "抽象后的开头模版，具体人名公司用【】占位",
    "emotional_trigger": "核心情绪触发，如 FOMO/避坑/共鸣吐槽/吃瓜反转",
    "core_narrative": "一句话核心叙事（可复用逻辑，去时效细节）",
    "cta_type": "转化动作类型"
  }},
  "viral_reason": "用 2~4 句说明为何流量高（机制：信息差/情绪/争议/视觉/身份共鸣等）",
  "reason_tags": ["短标签1", "短标签2", "短标签3"],
  "pattern": "可复用句式模板，用【占位】",
  "emotion": "主情绪短词",
  "tension": "冲突逻辑一句话",
  "keywords": ["触发词1", "触发词2", "触发词3"],
  "hooks": "开头抓手法一句话"
}}

{taxonomy_prompt_block()}

规则：
1. primary/secondary 必须尽量落在上述标签树；reason_tags 3~6 个，偏「流量机制」可检索短词。
2. hook_content / pattern / core_narrative 必须抽象，禁止保留具体人名、公司名、日期（用【人物】【公司】【事件】）。
3. viral_reason 要解释「为什么现在传得快」，不要复述全文。
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


def _fallback(title: str, raw: str, velocity: int = 0) -> Dict[str, Any]:
    text = (raw or title or "").strip()
    cut = text[:80] + ("…" if len(text) > 80 else "")
    return {
        "domain": "泛娱乐",
        "tags": {"primary": "人际/情感吐槽", "secondary": "奇葩见闻/吃瓜"},
        "elements": {
            "format": "Short-form" if len(text) < 180 else "Long-form",
            "hook_type": "共鸣痛点",
            "hook_content": cut or "关于【话题】有个反转",
            "emotional_trigger": "共鸣",
            "core_narrative": "用具体场景引发群体共鸣并带动转发评论",
            "cta_type": "引导评论区吵架/打字",
        },
        "viral_reason": f"高流速内容（约 {velocity}/小时）；以共鸣/话题性带动传播（AI 拆解失败兜底）。",
        "reason_tags": ["高流速", "共鸣", "话题传播"],
        "pattern": f"关于【话题】：{cut}" if cut else "【话题】有个反转",
        "emotion": "共鸣",
        "tension": "预期违背",
        "keywords": ["热点", "共鸣"],
        "hooks": "用具体场景开场",
    }


def deconstruct_viral_post(
    *,
    title: str = "",
    raw_text: str = "",
    platform: str = "x",
    url: str = "",
    source_key: str = "",
    collect_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """热帖专项拆解 → SQLite templates。"""
    init_db()
    title = (title or "").strip()
    raw = (raw_text or title).strip()
    if not raw:
        return {"success": False, "error": "缺少原文"}

    meta = dict(collect_meta or {})
    velocity = int(meta.get("velocity_per_hour") or 0)
    body = (
        f"平台：{platform or 'x'}\n"
        f"链接：{url or '(无)'}\n"
        f"作者：{meta.get('author') or meta.get('handle') or ''}\n"
        f"榜单桶：{meta.get('bucket') or ''}\n"
        f"浏览流速：{velocity} /小时\n"
        f"浏览量：{meta.get('views') or ''}\n"
        f"点赞：{meta.get('likes') or ''} 评论：{meta.get('replies') or ''} 转发：{meta.get('reposts') or ''}\n"
        f"标题/摘要：{title or '(无)'}\n"
        f"正文：{raw[:3500]}\n"
    )

    factors: Dict[str, Any] = {}
    provider = ""
    try:
        from utils.ai_client import generate_text

        result = generate_text(
            body,
            system_prompt=VIRAL_DECONSTRUCT_SYSTEM,
            temperature=0.3,
            max_tokens=1400,
        )
        provider = str(result.get("provider") or "")
        if result.get("success"):
            factors = _extract_json(str(result.get("content") or ""))
        else:
            factors = {}
    except Exception as e:
        factors = {}
        provider = f"error:{e}"

    if not factors.get("elements") and not factors.get("pattern"):
        factors = _fallback(title, raw, velocity)
        if not provider:
            provider = "fallback"

    norm = normalize_tags(factors)
    elements = factors.get("elements") if isinstance(factors.get("elements"), dict) else {}
    reason_tags = factors.get("reason_tags") or []
    if isinstance(reason_tags, str):
        reason_tags = [x.strip() for x in re.split(r"[,，、\s]+", reason_tags) if x.strip()]
    if not isinstance(reason_tags, list):
        reason_tags = []

    keywords = factors.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [x.strip() for x in re.split(r"[,，、\s]+", keywords) if x.strip()]
    if not isinstance(keywords, list):
        keywords = []

    tag_list = tags_as_list(
        norm["domain"],
        norm["primary"],
        norm["secondary"],
        [str(x) for x in reason_tags][:8],
    )
    # 便于前端筛选
    if velocity:
        tag_list.append(f"流速:{velocity}+")

    factors_out = {
        **factors,
        "domain": norm["domain"],
        "tags": {"primary": norm["primary"], "secondary": norm["secondary"]},
        "elements": {
            "format": str(elements.get("format") or factors.get("format") or ""),
            "hook_type": str(elements.get("hook_type") or ""),
            "hook_content": str(elements.get("hook_content") or factors.get("hooks") or ""),
            "emotional_trigger": str(elements.get("emotional_trigger") or factors.get("emotion") or ""),
            "core_narrative": str(elements.get("core_narrative") or ""),
            "cta_type": str(elements.get("cta_type") or ""),
        },
        "viral_reason": str(factors.get("viral_reason") or ""),
        "reason_tags": [str(x) for x in reason_tags][:8],
        "metrics": {
            "velocity_per_hour": velocity,
            "views": meta.get("views"),
            "likes": meta.get("likes"),
            "replies": meta.get("replies"),
            "reposts": meta.get("reposts"),
            "bucket": meta.get("bucket"),
            "source": meta.get("via") or "xgrowth.tools",
        },
    }

    now = datetime.now().isoformat(timespec="seconds")
    provenance = {
        "steps": [
            {
                "layer": "collect",
                "via": meta.get("via") or "xgrowth.tools/viral-tweets",
                "url": url,
                "title": title,
                "velocity_per_hour": velocity,
                "at": meta.get("fetched_at") or now,
                **{
                    k: v
                    for k, v in meta.items()
                    if k not in {"via", "fetched_at"} and k not in {"raw_text"}
                },
            },
            {
                "layer": "deconstruct",
                "provider": provider,
                "prompt": "corpus.viral_deconstruct.VIRAL_DECONSTRUCT_SYSTEM",
                "at": now,
            },
            {
                "layer": "store",
                "store": "sqlite",
                "db": "output/corpus.db",
                "at": now,
            },
        ]
    }

    pattern = str(factors.get("pattern") or elements.get("hook_content") or title or "")[:240]
    emotion = str(factors.get("emotion") or elements.get("emotional_trigger") or "")[:40]
    hooks = str(factors.get("hooks") or elements.get("hook_content") or "")[:240]

    # weight 随流速略加权，便于后续选用排序
    weight = 1.0
    if velocity >= 50000:
        weight = 2.0
    elif velocity >= 20000:
        weight = 1.6
    elif velocity >= 8000:
        weight = 1.3

    template = create_template(
        source_platform=platform or "x",
        source_url=url or "",
        source_key=source_key or url or title or now,
        source_title=title or (raw[:40] + ("…" if len(raw) > 40 else "")),
        raw_text=raw,
        pattern=pattern,
        emotion=emotion,
        tension=str(factors.get("tension") or "")[:120],
        keywords=[str(x) for x in keywords][:12],
        hooks=hooks,
        tags=tag_list,
        provenance=provenance,
        factors=factors_out,
        status="active",
        quality="unrated",
        weight=weight,
    )
    prov = dict(template.get("provenance") or provenance)
    for step in list(prov.get("steps") or []):
        if step.get("layer") == "store":
            step["template_id"] = template.get("id")
    template = update_template(int(template["id"]), {"provenance": prov}) or template

    return {
        "success": True,
        "template": template,
        "factors": factors_out,
        "provider": provider,
    }
