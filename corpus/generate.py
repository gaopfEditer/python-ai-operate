# coding=utf-8
"""基于语料模板 + 新话题，再生成平台风味帖子。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Sequence

from corpus.db import create_generation, get_templates_by_ids, update_template

REGENERATE_SYSTEM = """你是短内容创作者。根据「梗骨架模板」和「新话题」，写出一条可直接发的爆款风帖子。
要求：
1. 保留模板的句式节奏、情绪与冲突逻辑，但内容换成新话题。
2. 语气贴合目标平台；默认偏口语、有钩子。
3. 不要解释，不要标题前缀，只输出帖子正文。
4. 控制在 80~280 字（中文）或 40~120 词（英文），除非用户另有要求。
"""

COMPOSE_SYSTEM = """你是短内容创作者。用户会给出「热点主题」以及若干语料卡片（句式/情绪/冲突/关键词/钩子）。
请组合这些卡片的要素与结构，写出一条贴合热点主题、可直接发布的爆款风帖子。
要求：
1. 可融合多卡：用一张卡的句式节奏 + 另一张的情绪/冲突 + 共享触发词。
2. 内容必须围绕热点主题，不要复述旧事件细节。
3. 不要解释，不要标题前缀，只输出帖子正文。
4. 默认 80~280 字（中文）。
"""


def regenerate_from_template(
    *,
    template_id: int,
    topic: str,
    platform_style: str = "通用",
    extra_prompt: str = "",
    bump_weight: bool = False,
) -> Dict[str, Any]:
    """用单模板再生成内容，并记录取材路径。"""
    return compose_from_templates(
        template_ids=[int(template_id)],
        topic=topic,
        platform_style=platform_style,
        extra_prompt=extra_prompt,
        bump_weight=bump_weight,
    )


def compose_from_templates(
    *,
    template_ids: Sequence[int],
    topic: str,
    platform_style: str = "通用",
    extra_prompt: str = "",
    bump_weight: bool = False,
) -> Dict[str, Any]:
    """用一张或多张语料卡片 + 热点主题组合生成。"""
    topic = (topic or "").strip()
    if not topic:
        return {"success": False, "error": "请填写热点主题"}
    ids = [int(x) for x in template_ids if x is not None]
    if not ids:
        return {"success": False, "error": "请至少选择一张语料卡片"}
    tmpls = get_templates_by_ids(ids)
    if not tmpls:
        return {"success": False, "error": "模板不存在"}

    cards: List[str] = []
    for i, tmpl in enumerate(tmpls, 1):
        cards.append(
            f"卡片{i}(#{tmpl.get('id')}):\n"
            f"- pattern: {tmpl.get('pattern') or ''}\n"
            f"- emotion: {tmpl.get('emotion') or ''}\n"
            f"- tension: {tmpl.get('tension') or ''}\n"
            f"- keywords: {', '.join(tmpl.get('keywords') or [])}\n"
            f"- hooks: {tmpl.get('hooks') or ''}\n"
        )
    user_prompt = (
        f"目标平台风格：{platform_style or '通用'}\n"
        f"热点主题：{topic}\n\n" + "\n".join(cards)
    )
    if extra_prompt:
        user_prompt += f"\n补充要求：{extra_prompt.strip()}\n"

    system = COMPOSE_SYSTEM if len(tmpls) > 1 else REGENERATE_SYSTEM
    try:
        from utils.ai_client import generate_text

        result = generate_text(
            user_prompt,
            system_prompt=system,
            temperature=0.75,
            max_tokens=1200,
        )
    except Exception as e:
        return {"success": False, "error": f"AI 调用失败: {e}"}

    if not result.get("success"):
        return {"success": False, "error": result.get("error") or "生成失败"}

    content = (result.get("content") or "").strip()
    now = datetime.now().isoformat(timespec="seconds")
    path_steps: List[Dict[str, Any]] = []
    for tmpl in tmpls:
        path_steps.extend(list((tmpl.get("provenance") or {}).get("steps") or []))
    path_steps.append(
        {
            "layer": "generate",
            "template_ids": [t.get("id") for t in tmpls],
            "topic": topic,
            "platform_style": platform_style,
            "provider": result.get("provider"),
            "mode": "compose" if len(tmpls) > 1 else "single",
            "at": now,
        }
    )
    path = {"steps": path_steps}
    primary_id = int(tmpls[0]["id"])
    gen = create_generation(
        template_id=primary_id,
        topic=topic,
        content=content,
        platform_style=platform_style or "",
        path=path,
        meta={
            "provider": result.get("provider"),
            "extra_prompt": extra_prompt,
            "template_ids": [t.get("id") for t in tmpls],
            "mode": "compose" if len(tmpls) > 1 else "single",
        },
    )

    if bump_weight:
        for tmpl in tmpls:
            try:
                w = float(tmpl.get("weight") or 1.0) + (0.15 if len(tmpls) > 1 else 0.2)
                update_template(
                    int(tmpl["id"]),
                    {"weight": round(w, 2), "quality": "good"},
                    keep_history=True,
                    history_reason="used_in_generate",
                )
            except Exception:
                pass

    return {
        "success": True,
        "content": content,
        "generation": gen,
        "templates": tmpls,
        "template": tmpls[0],
        "path": path,
        "provider": result.get("provider"),
    }
