# coding=utf-8
"""Post Lab：叙事配方、多版本生成、CoT 步骤、局部微调。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from corpus.db import (
    create_generation,
    create_template,
    get_generation,
    get_templates_by_ids,
    init_db,
    update_generation,
    update_template,
)

FORMULA_PRESETS: Dict[str, Dict[str, str]] = {
    "contrarian": {
        "id": "contrarian",
        "label": "反常识批判风",
        "emoji": "⚡",
        "blurb": "否定直觉 → 揭示隐藏代价 → 给出底层解法",
        "style_hint": "犀利反常识",
        "recipe": "先否定大众直觉，再揭示隐藏代价，最后给出可执行的底层解法。语气锋利但不人身攻击。",
    },
    "build_public": {
        "id": "build_public",
        "label": "Build in Public 复盘",
        "emoji": "🧪",
        "blurb": "踩坑数据 → 实验对比 → 提炼通用经验",
        "style_hint": "故事复盘型",
        "recipe": "用具体数据/失败记录开场，对比实验前后，提炼可复用经验。语气坦诚、建设性。",
    },
    "absurd": {
        "id": "absurd",
        "label": "荒诞讽刺风",
        "emoji": "🎭",
        "blurb": "严肃日常 → 荒谬反转 → 时代痛点",
        "style_hint": "荒诞反转",
        "recipe": "从一本正经的日常切入，中段荒谬反转，收束到时代/行业痛点。可黑色幽默。",
    },
    "checklist": {
        "id": "checklist",
        "label": "硬核极简清单",
        "emoji": "🛠️",
        "blurb": "痛点直击 → 3 点硬核建议 → 落地指令",
        "style_hint": "极简清单型",
        "recipe": "开头直击痛点，中间给恰好 3 条硬核建议（可编号），结尾给一句可立刻执行的指令。",
    },
}

TWEAK_PRESETS: Dict[str, str] = {
    "sharper_hook": "只重写开头钩子，让第一句更刺眼、更抓人；后文保持大意。只输出完整帖子正文。",
    "more_colloquial": "整体改得更口语、像真人随手发的；保留核心观点。只输出完整帖子正文。",
    "add_data": "在合适位置补充具体数字/参数/对比（可合理推断但要像真实经验）。只输出完整帖子正文。",
    "shorter": "压缩到更短、信息密度更高，去掉废话。只输出完整帖子正文。",
    "softer": "语气更温和共鸣，少攻击性。只输出完整帖子正文。",
}


def list_formulas() -> List[Dict[str, str]]:
    return [dict(v) for v in FORMULA_PRESETS.values()]


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


def _cards_brief(tmpls: List[Dict[str, Any]]) -> str:
    lines = []
    for i, tmpl in enumerate(tmpls, 1):
        factors = tmpl.get("factors") or {}
        lines.append(
            f"卡片{i}(#{tmpl.get('id')} 「{tmpl.get('source_title') or ''}」):\n"
            f"- hook: {tmpl.get('hooks') or factors.get('hook') or ''}\n"
            f"- pattern: {tmpl.get('pattern') or ''}\n"
            f"- emotion: {tmpl.get('emotion') or ''}\n"
            f"- tension: {tmpl.get('tension') or ''}\n"
            f"- narrative: {factors.get('narrative_type') or tmpl.get('emotion') or ''}\n"
            f"- use_case: {factors.get('use_case') or ''}\n"
            f"- keywords: {', '.join(tmpl.get('keywords') or [])}\n"
            f"- tags: {', '.join(tmpl.get('tags') or [])}\n"
        )
    return "\n".join(lines)


def _build_cot(tmpls: List[Dict[str, Any]], topic: str, formula: Dict[str, str]) -> List[str]:
    steps = []
    if tmpls:
        names = "、".join(
            f"#{t.get('id')}「{(t.get('source_title') or t.get('emotion') or '卡')[:12]}」"
            for t in tmpls[:3]
        )
        emos = " / ".join(sorted({str(t.get("emotion") or "").strip() for t in tmpls if t.get("emotion")}))
        steps.append(f"提取 {names} 的情绪与骨架" + (f"（{emos}）" if emos else ""))
    else:
        steps.append("未选卡片，将仅按热点主题与叙事配方创作")
    steps.append(f"将热点「{topic}」映射到冲突点：{(tmpls[0].get('tension') if tmpls else '') or '预期违背/成本落差'}")
    steps.append(f"套用叙事配方「{formula.get('label')}」：{formula.get('blurb')}")
    steps.append("并行生成 3 个叙事变体，供你并排挑选")
    return steps


LAB_SYSTEM = """你是短贴创作 Agent（Post Lab）。根据热点主题、灵感卡片叙事骨架与叙事配方，一次产出 3 个变体。
只输出一个 JSON 对象，不要 markdown：
{
  "thinking": ["简短思考步骤1", "步骤2"],
  "variants": [
    {"id": "A", "label": "情绪刺眼", "hook": "第一句", "content": "完整正文"},
    {"id": "B", "label": "干货数据", "hook": "第一句", "content": "完整正文"},
    {"id": "C", "label": "故事复盘", "hook": "第一句", "content": "完整正文"}
  ]
}
固定分化：
- A：冲突与颠覆认知，情绪强、钩子刺眼。
- B：硬核推导/行动清单，可含数据或步骤。
- C：第一人称经历与教训，故事感。
规则：围绕同一热点；注入卡片的 hook/pattern/tension；80~280 字；禁止照搬原文事件细节。
"""


def lab_compose(
    *,
    template_ids: Optional[Sequence[int]] = None,
    topic: str,
    formula_id: str = "contrarian",
    platform_style: str = "X/Twitter",
    extra_prompt: str = "",
    variant_count: int = 3,
    bump_weight: bool = True,
) -> Dict[str, Any]:
    """工作台一键融合：返回 CoT + 多版本。"""
    topic = (topic or "").strip()
    if not topic:
        return {"success": False, "error": "请填写热点主题"}
    formula = FORMULA_PRESETS.get(formula_id) or FORMULA_PRESETS["contrarian"]
    ids = [int(x) for x in (template_ids or []) if x is not None]
    tmpls = get_templates_by_ids(ids) if ids else []
    # 允许无卡纯热点生成
    cot = _build_cot(tmpls, topic, formula)

    user_prompt = (
        f"平台风格：{platform_style or 'X/Twitter'}\n"
        f"热点主题：{topic}\n"
        f"叙事配方：{formula.get('label')} — {formula.get('recipe')}\n"
        f"需要变体数：{max(2, min(3, int(variant_count or 3)))}\n"
    )
    if tmpls:
        user_prompt += "灵感卡片：\n" + _cards_brief(tmpls) + "\n"
    if extra_prompt:
        user_prompt += f"补充要求：{extra_prompt.strip()}\n"
    user_prompt += "请按配方输出 JSON（含 thinking 与 variants）。\n"

    provider = ""
    payload: Dict[str, Any] = {}
    ai_error = ""
    try:
        from utils.ai_client import generate_text

        result = generate_text(
            user_prompt,
            system_prompt=LAB_SYSTEM,
            temperature=0.8,
            max_tokens=2200,
        )
        provider = str(result.get("provider") or "")
        if not result.get("success"):
            ai_error = str(result.get("error") or "生成失败")
        else:
            payload = _extract_json(str(result.get("content") or ""))
    except Exception as e:
        ai_error = f"AI 调用失败: {e}"

    thinking = payload.get("thinking") if isinstance(payload.get("thinking"), list) else cot
    variants_raw = payload.get("variants") if isinstance(payload.get("variants"), list) else []
    variants: List[Dict[str, Any]] = []
    for i, v in enumerate(variants_raw[:3]):
        if not isinstance(v, dict):
            continue
        content = str(v.get("content") or "").strip()
        if not content:
            continue
        variants.append(
            {
                "id": str(v.get("id") or chr(65 + i)),
                "label": str(v.get("label") or formula.get("style_hint") or f"版本{chr(65 + i)}"),
                "hook": str(v.get("hook") or content.split("\n", 1)[0][:80]),
                "content": content,
            }
        )

    if not variants:
        # 本地兜底变体，保证工作台可演示闭环
        hook0 = (tmpls[0].get("hooks") if tmpls else "") or f"关于{topic}，有个反直觉的点"
        base = (
            f"{hook0}\n\n"
            f"大多数人谈「{topic}」只看到表面，真正的冲突是：{(tmpls[0].get('tension') if tmpls else '预期与成本错位')}。\n"
            f"按「{formula.get('label')}」思路：{formula.get('blurb')}。\n"
            f"可先从一件小事验证，再决定是否加码。"
        )
        variants = [
            {
                "id": "A",
                "label": "情绪刺眼",
                "hook": hook0,
                "content": base,
            },
            {
                "id": "B",
                "label": "干货数据",
                "hook": f"上周我被「{topic}」打脸了一次",
                "content": (
                    f"上周我被「{topic}」打脸了一次。\n"
                    f"原本以为能一步到位，结果卡在细节上。复盘后只留下三条：把假设写下来、小步验证、公开结果。\n"
                    f"同场的人如果也在踩坑，欢迎对照。"
                ),
            },
            {
                "id": "C",
                "label": "故事复盘",
                "hook": f"做「{topic}」前先问自己这 3 句",
                "content": (
                    f"做「{topic}」前先问自己这 3 句：\n"
                    f"1) 真正要优化的指标是什么？\n"
                    f"2) 最小可验证动作是什么？\n"
                    f"3) 失败的止损线在哪？\n"
                    f"想清楚再动手，比兴奋着开干更省时间。"
                ),
            },
        ]
        thinking = list(cot) + ([f"模型暂不可用，已给本地兜底变体（{ai_error[:80]}）"] if ai_error else ["已生成兜底变体"])
        provider = "fallback"

    now = datetime.now().isoformat(timespec="seconds")
    path_steps: List[Dict[str, Any]] = []
    for t in tmpls:
        path_steps.extend(list((t.get("provenance") or {}).get("steps") or []))
    path_steps.append(
        {
            "layer": "generate",
            "mode": "lab_compose",
            "formula": formula.get("id"),
            "template_ids": [t.get("id") for t in tmpls],
            "topic": topic,
            "provider": provider,
            "at": now,
        }
    )
    path = {"steps": path_steps}

    generations = []
    primary_id = int(tmpls[0]["id"]) if tmpls else None
    for v in variants:
        gen = create_generation(
            template_id=primary_id,
            topic=topic,
            content=v["content"],
            platform_style=platform_style or "",
            path=path,
            meta={
                "provider": provider,
                "formula": formula.get("id"),
                "variant_id": v["id"],
                "variant_label": v["label"],
                "template_ids": [t.get("id") for t in tmpls],
                "mode": "lab_compose",
                "cot": thinking,
            },
        )
        v["generation_id"] = gen.get("id")
        generations.append(gen)

    if bump_weight and tmpls:
        for tmpl in tmpls:
            try:
                w = float(tmpl.get("weight") or 1.0) + 0.15
                update_template(
                    int(tmpl["id"]),
                    {"weight": round(w, 2)},
                    keep_history=True,
                    history_reason="lab_compose",
                )
            except Exception:
                pass

    return {
        "success": True,
        "topic": topic,
        "formula": formula,
        "cot": [str(x) for x in (thinking or cot)][:8],
        "variants": variants,
        "templates": tmpls,
        "path": path,
        "provider": provider,
        "content": variants[0]["content"],  # 兼容旧字段
        "generations": generations,
    }


def tweak_content(
    *,
    content: str,
    tweak_id: str = "sharper_hook",
    custom: str = "",
    topic: str = "",
) -> Dict[str, Any]:
    """对已有正文做局部微调。"""
    content = (content or "").strip()
    if not content:
        return {"success": False, "error": "没有可微调的正文"}
    instruction = TWEAK_PRESETS.get(tweak_id) or custom or TWEAK_PRESETS["sharper_hook"]
    if custom.strip():
        instruction = custom.strip() + " 只输出完整帖子正文。"
    prompt = f"原帖：\n{content}\n\n微调要求：{instruction}\n"
    if topic:
        prompt += f"热点主题（保持相关）：{topic}\n"
    try:
        from utils.ai_client import generate_text

        result = generate_text(
            prompt,
            system_prompt="你是短贴润色编辑。按要求改写，只输出改写后的完整正文，不要解释。",
            temperature=0.7,
            max_tokens=1200,
        )
    except Exception as e:
        return {"success": False, "error": f"AI 调用失败: {e}"}
    if not result.get("success"):
        return {"success": False, "error": result.get("error") or "微调失败"}
    new_content = (result.get("content") or "").strip()
    return {
        "success": True,
        "content": new_content,
        "hook": new_content.split("\n", 1)[0][:80],
        "tweak_id": tweak_id,
        "provider": result.get("provider"),
    }


CAPTURE_SYSTEM = """你是灵感卡片解析器。用户粘贴一段内容/推文/随想，请提炼成可复用灵感卡。
只输出 JSON：
{
  "title": "短标题≤16字",
  "hook": "最抓人的第一句/金句",
  "pattern": "抽象句式，用【占位】",
  "core_concept": "一句话核心观点",
  "emotion": "情绪短词",
  "tension": "冲突逻辑一句话",
  "narrative_type": "反常识破局|翻车复盘|荒诞反转|硬核清单|共鸣安慰|其他",
  "use_case": "适合作为推文开头|适合作为论据|适合作为结尾金句|适合完整成帖",
  "keywords": ["词1","词2","词3"],
  "tags": ["标签1","标签2","标签3"]
}
规则：抽象化，去掉具体人名公司日期；tags 3 个左右语义标签。
"""


def quick_capture(text: str, *, source_url: str = "") -> Dict[str, Any]:
    """快速捕捉：粘贴即入库。"""
    init_db()
    text = (text or "").strip()
    if not text:
        return {"success": False, "error": "请粘贴内容或随想"}
    # 若像 URL，保留在 provenance
    url = source_url.strip()
    if not url and re.match(r"^https?://\S+$", text.split()[0] if text.split() else ""):
        url = text.split()[0]
    factors: Dict[str, Any] = {}
    provider = ""
    try:
        from utils.ai_client import generate_text

        result = generate_text(
            f"链接：{url or '(无)'}\n内容：\n{text[:2500]}",
            system_prompt=CAPTURE_SYSTEM,
            temperature=0.35,
            max_tokens=900,
        )
        provider = str(result.get("provider") or "")
        if result.get("success"):
            factors = _extract_json(str(result.get("content") or ""))
    except Exception as e:
        return {"success": False, "error": f"AI 调用失败: {e}"}

    if not factors.get("pattern") and not factors.get("hook"):
        cut = text[:60] + ("…" if len(text) > 60 else "")
        factors = {
            "title": cut[:16] or "快捕灵感",
            "hook": cut,
            "pattern": f"关于【话题】：{cut}",
            "emotion": "共鸣",
            "tension": "预期违背",
            "narrative_type": "其他",
            "use_case": "适合完整成帖",
            "keywords": ["灵感"],
            "tags": ["快捕"],
        }
        provider = provider or "fallback"

    keywords = factors.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [x.strip() for x in re.split(r"[,，、\s]+", keywords) if x.strip()]
    tags = factors.get("tags") or []
    if isinstance(tags, str):
        tags = [x.strip().lstrip("#") for x in re.split(r"[,，、\s#]+", tags) if x.strip()]
    tags = [str(t).lstrip("#") for t in tags][:6]
    if "快捕" not in tags:
        tags.append("快捕")

    now = datetime.now().isoformat(timespec="seconds")
    import uuid

    sid = uuid.uuid4().hex[:10]
    narrative = str(factors.get("narrative_type") or "")
    template = create_template(
        source_platform="capture",
        source_url=url or "",
        source_key=f"capture-{sid}",
        source_title=str(factors.get("title") or "快捕灵感")[:40],
        raw_text=text[:3000],
        pattern=str(factors.get("pattern") or ""),
        emotion=str(factors.get("emotion") or ""),
        tension=str(factors.get("tension") or ""),
        keywords=[str(x) for x in keywords][:12],
        hooks=str(factors.get("hook") or factors.get("hooks") or ""),
        tags=tags,
        provenance={
            "steps": [
                {"layer": "collect", "via": "quick_capture", "url": url, "at": now},
                {
                    "layer": "deconstruct",
                    "provider": provider,
                    "prompt": "corpus.lab.CAPTURE_SYSTEM",
                    "at": now,
                },
                {"layer": "store", "store": "sqlite", "at": now},
            ]
        },
        factors={
            **factors,
            "narrative_type": narrative,
            "use_case": factors.get("use_case") or "",
            "hook": factors.get("hook") or "",
        },
        status="active",
        quality="unrated",
        weight=1.0,
    )
    return {
        "success": True,
        "template": template,
        "tags": tags,
        "narrative_type": narrative,
        "provider": provider,
        "message": f"已解析入库，标签：{' '.join('#' + t for t in tags[:3])}",
    }


def _snapshot_card_elements(tmpls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """留存灵感卡完整要素，而非只留短观点。"""
    out: List[Dict[str, Any]] = []
    for t in tmpls:
        factors = t.get("factors") if isinstance(t.get("factors"), dict) else {}
        raw = str(t.get("raw_text") or "")
        out.append(
            {
                "id": t.get("id"),
                "title": t.get("source_title") or "",
                "hook": t.get("hooks") or factors.get("hook") or "",
                "pattern": t.get("pattern") or "",
                "emotion": t.get("emotion") or "",
                "tension": t.get("tension") or "",
                "keywords": list(t.get("keywords") or []),
                "tags": list(t.get("tags") or []),
                "core_concept": factors.get("core_concept") or "",
                "narrative_type": factors.get("narrative_type") or "",
                "use_case": factors.get("use_case") or "",
                "raw_text": raw[:4000],
                "factors": factors,
            }
        )
    return out


def feature_variant(
    *,
    content: str,
    topic: str = "",
    hook: str = "",
    variant_id: str = "",
    variant_label: str = "",
    formula_id: str = "",
    generation_id: Optional[int] = None,
    template_ids: Optional[Sequence[int]] = None,
    source_cards: Optional[List[Dict[str, Any]]] = None,
    cot: Optional[List[str]] = None,
    platform_style: str = "X/Twitter",
    note: str = "",
) -> Dict[str, Any]:
    """
    精选留存：完整正文 + 要素细节（Hook/句式/情绪/冲突/关键词/取材卡），
    写入 generations（featured）并同步一张可检索的精选模板。
    """
    init_db()
    content = (content or "").strip()
    if not content:
        return {"success": False, "error": "没有可留存的正文"}

    hook = (hook or "").strip() or content.split("\n", 1)[0][:120]
    topic = (topic or "").strip() or "精选变体"
    now = datetime.now().isoformat(timespec="seconds")

    tids: List[int] = []
    for x in template_ids or []:
        try:
            tids.append(int(x))
        except Exception:
            pass
    tmpls = get_templates_by_ids(tids) if tids else []
    card_elements = source_cards if isinstance(source_cards, list) and source_cards else _snapshot_card_elements(tmpls)

    elements = {
        "hook": hook,
        "topic": topic,
        "variant_id": variant_id or "",
        "variant_label": variant_label or "",
        "formula": formula_id or "",
        "platform_style": platform_style or "",
        "note": (note or "").strip(),
        "full_content": content,
        "paragraphs": [p.strip() for p in re.split(r"\n+", content) if p.strip()],
        "source_cards": card_elements,
        "cot": [str(x) for x in (cot or [])][:12],
        "featured_at": now,
    }

    featured_meta = {
        "featured": True,
        "featured_at": now,
        "elements": elements,
        "variant_id": variant_id or "",
        "variant_label": variant_label or "",
        "formula": formula_id or "",
        "template_ids": [t.get("id") for t in tmpls] or tids,
        "mode": "lab_feature",
    }

    gen: Optional[Dict[str, Any]] = None
    if generation_id is not None:
        try:
            gid = int(generation_id)
        except Exception:
            gid = 0
        if gid:
            existing = get_generation(gid)
            if existing:
                gen = update_generation(
                    gid,
                    content=content,
                    platform_style="featured",
                    meta=featured_meta,
                    merge_meta=True,
                )

    if gen is None:
        primary_id = int(tmpls[0]["id"]) if tmpls else (tids[0] if tids else None)
        gen = create_generation(
            template_id=primary_id,
            topic=topic,
            content=content,
            platform_style="featured",
            path={
                "steps": [
                    {
                        "layer": "feature",
                        "mode": "lab_feature",
                        "formula": formula_id,
                        "template_ids": tids,
                        "at": now,
                    }
                ]
            },
            meta=featured_meta,
        )

    # 精选卡：pattern / raw_text 存完整正文，便于日后复用细节而非短观点
    title = (hook[:40] or f"{topic}-{variant_label or variant_id or '精选'}").strip()
    keywords: List[str] = []
    emotions: List[str] = []
    tensions: List[str] = []
    for c in card_elements:
        for kw in c.get("keywords") or []:
            if kw and kw not in keywords:
                keywords.append(str(kw))
        if c.get("emotion") and c["emotion"] not in emotions:
            emotions.append(str(c["emotion"]))
        if c.get("tension") and c["tension"] not in tensions:
            tensions.append(str(c["tension"]))
    tags = ["精选", "要素留存"]
    if formula_id:
        tags.append(str(formula_id))
    if variant_label:
        tags.append(str(variant_label)[:16])

    template = create_template(
        source_platform="featured",
        source_key=f"featured-gen-{gen.get('id')}-{int(datetime.now().timestamp())}",
        source_title=title,
        raw_text=content,
        pattern=content,
        hooks=hook,
        emotion=" · ".join(emotions)[:80] or "精选",
        tension=" · ".join(tensions)[:120] or "",
        keywords=keywords[:12],
        tags=tags[:8],
        quality="good",
        status="active",
        weight=1.2,
        provenance={
            "steps": [
                {
                    "layer": "feature",
                    "generation_id": gen.get("id"),
                    "formula": formula_id,
                    "at": now,
                }
            ]
        },
        factors={
            **elements,
            "generation_id": gen.get("id"),
            "core_concept": hook,
            "narrative_type": formula_id or "精选留存",
            "use_case": "适合完整成帖",
        },
    )

    return {
        "success": True,
        "generation": gen,
        "template": template,
        "elements": elements,
        "message": f"已精选留存 #{gen.get('id')}（完整正文 + 要素）",
    }
