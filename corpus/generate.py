# coding=utf-8
"""基于语料模板 + 新话题，再生成平台风味帖子。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from corpus.db import create_generation, get_template, update_template

REGENERATE_SYSTEM = """你是短内容创作者。根据「梗骨架模板」和「新话题」，写出一条可直接发的爆款风帖子。
要求：
1. 保留模板的句式节奏、情绪与冲突逻辑，但内容换成新话题。
2. 语气贴合目标平台；默认偏口语、有钩子。
3. 不要解释，不要标题前缀，只输出帖子正文。
4. 控制在 80~280 字（中文）或 40~120 词（英文），除非用户另有要求。
"""


def regenerate_from_template(
    *,
    template_id: int,
    topic: str,
    platform_style: str = "通用",
    extra_prompt: str = "",
    bump_weight: bool = False,
) -> Dict[str, Any]:
    """用模板再生成内容，并记录取材路径。"""
    topic = (topic or "").strip()
    if not topic:
        return {"success": False, "error": "请填写新话题"}
    tmpl = get_template(int(template_id))
    if not tmpl:
        return {"success": False, "error": "模板不存在"}

    user_prompt = (
        f"目标平台风格：{platform_style or '通用'}\n"
        f"新话题：{topic}\n"
        f"句式模板(pattern)：{tmpl.get('pattern') or ''}\n"
        f"情绪(emotion)：{tmpl.get('emotion') or ''}\n"
        f"冲突(tension)：{tmpl.get('tension') or ''}\n"
        f"触发词(keywords)：{', '.join(tmpl.get('keywords') or [])}\n"
        f"开头手法(hooks)：{tmpl.get('hooks') or ''}\n"
    )
    if extra_prompt:
        user_prompt += f"补充要求：{extra_prompt.strip()}\n"

    try:
        from utils.ai_client import generate_text

        result = generate_text(
            user_prompt,
            system_prompt=REGENERATE_SYSTEM,
            temperature=0.75,
            max_tokens=1200,
        )
    except Exception as e:
        return {"success": False, "error": f"AI 调用失败: {e}"}

    if not result.get("success"):
        return {"success": False, "error": result.get("error") or "生成失败"}

    content = (result.get("content") or "").strip()
    now = datetime.now().isoformat(timespec="seconds")
    path = {
        "steps": [
            *list((tmpl.get("provenance") or {}).get("steps") or []),
            {
                "layer": "generate",
                "template_id": tmpl.get("id"),
                "topic": topic,
                "platform_style": platform_style,
                "provider": result.get("provider"),
                "at": now,
            },
        ]
    }
    gen = create_generation(
        template_id=int(tmpl["id"]),
        topic=topic,
        content=content,
        platform_style=platform_style or "",
        path=path,
        meta={"provider": result.get("provider"), "extra_prompt": extra_prompt},
    )

    if bump_weight:
        try:
            w = float(tmpl.get("weight") or 1.0) + 0.2
            update_template(int(tmpl["id"]), {"weight": round(w, 2), "quality": "good"})
        except Exception:
            pass

    return {
        "success": True,
        "content": content,
        "generation": gen,
        "template": get_template(int(tmpl["id"])),
        "path": path,
        "provider": result.get("provider"),
    }
