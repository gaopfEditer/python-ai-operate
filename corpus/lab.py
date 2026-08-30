# coding=utf-8
"""Post Lab：叙事配方、多版本生成、CoT 步骤、局部微调。"""

from __future__ import annotations

import json
import re
import copy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

from corpus.db import (
    create_generation,
    create_template,
    get_generation,
    get_templates_by_ids,
    init_db,
    list_templates,
    update_generation,
    update_template,
)
from corpus.materials import category_label

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


PROMPT_PROFILES: Dict[str, Dict[str, Any]] = {
    "general": {
        "id": "general",
        "label": "通用短贴",
        "emoji": "📝",
        "blurb": "归纳可复用提示词 + A/B/C 三版短贴（当前默认）",
        "variant_hint": "A 刺眼 · B 干货 · C 故事",
        "max_tokens": 2200,
        "temperature": 0.8,
        "output_extra": ["prompt_snippets"],
        "system": """你是灵感碰撞通用短贴 Agent。根据热点、灵感卡骨架与叙事配方，产出 3 个短贴变体，并归纳可复用提示词。
只输出 JSON，不要 markdown：
{
  "thinking": ["步骤1", "步骤2"],
  "prompt_snippets": ["从卡片与主题归纳的可复用提示词/句式1", "句式2", "句式3"],
  "variants": [
    {"id": "A", "label": "情绪刺眼", "hook": "第一句", "content": "完整正文"},
    {"id": "B", "label": "干货数据", "hook": "第一句", "content": "完整正文"},
    {"id": "C", "label": "故事复盘", "hook": "第一句", "content": "完整正文"}
  ]
}
固定分化：A 冲突颠覆认知；B 硬核推导/清单；C 第一人称经历。
prompt_snippets：抽象句式，用【占位】，3~5 条，便于下次复用。
规则：80~280 字/条；注入卡片 hook/pattern/tension；禁止照搬原文细节。""",
    },
    "technical": {
        "id": "technical",
        "label": "行情/宏观技术分析",
        "emoji": "📊",
        "blurb": "技术面快评 · 宏观事件解读 · 场景交易计划（含美联储/数据）",
        "variant_hint": "A 技术面 · B 宏观 · C 交易计划",
        "max_tokens": 2800,
        "temperature": 0.65,
        "output_extra": [],
        "system": """你是灵感碰撞行情分析 Agent。针对热点（行情波动、美联储、CPI/非农、流动性、重大政策），结合灵感卡观点，产出 3 个分析变体。
只输出 JSON：
{
  "thinking": ["步骤1", "步骤2"],
  "variants": [
    {"id": "A", "label": "技术面快评", "hook": "第一句", "content": "完整正文"},
    {"id": "B", "label": "宏观解读", "hook": "第一句", "content": "完整正文"},
    {"id": "C", "label": "场景交易计划", "hook": "第一句", "content": "完整正文"}
  ]
}
固定分化：
- A：关键位/趋势/量价/指标逻辑（可写支撑阻力、结构，但不给具体喊单）。
- B：宏观事件 → 传导链 → 对 BTC/ETH/风险资产/美元/利率的影响（适合美联储、数据公布）。
- C： bull/base/bear 三场景 + 观察位 + 失效条件 + 风险提示。
规则：150~400 字/条；数字可合理推断但要像研究笔记；禁止保证收益、禁止「必涨必跌」。""",
    },
    "longform_video": {
        "id": "longform_video",
        "label": "结构化长文·转视频",
        "emoji": "🎬",
        "blurb": "口播大纲 · 分镜脚本 · 完整视频稿（后续可拆镜）",
        "variant_hint": "A 口播大纲 · B 分镜 · C 完整稿",
        "max_tokens": 4500,
        "temperature": 0.75,
        "output_extra": ["video_meta"],
        "system": """你是灵感碰撞长文/视频脚本 Agent。根据热点与灵感卡，产出可转视频的 3 个结构化变体。
只输出 JSON：
{
  "thinking": ["步骤1", "步骤2"],
  "video_meta": {"duration_min": 8, "audience": "受众", "tone": "语气"},
  "variants": [
    {"id": "A", "label": "口播大纲", "hook": "开场 Hook", "content": "Markdown 大纲：Hook / 3段论点 / 金句 / CTA"},
    {"id": "B", "label": "分镜脚本", "hook": "第一镜旁白", "content": "按场景编号：画面描述 + 旁白 + 字幕要点（至少 5 镜）"},
    {"id": "C", "label": "完整视频稿", "hook": "开场 15 秒", "content": "可照读的完整口播稿，800~1500 字，段落清晰"}
  ]
}
规则：三版围绕同一主题递进；B 必须可分镜；C 适合 6~12 分钟口播；保留卡片核心冲突但扩展论证。""",
    },
}


PROFILE_IDS = ("general", "technical", "longform_video")
_LAB_PROFILES_PATH = Path(__file__).resolve().parent.parent / "config" / "lab_prompt_profiles.yaml"
_profiles_cache: Optional[Dict[str, Dict[str, Any]]] = None


def _builtin_prompt_profiles() -> Dict[str, Dict[str, Any]]:
    return copy.deepcopy(PROMPT_PROFILES)


def _invalidate_profiles_cache() -> None:
    global _profiles_cache
    _profiles_cache = None


def get_merged_prompt_profiles() -> Dict[str, Dict[str, Any]]:
    global _profiles_cache
    if _profiles_cache is not None:
        return _profiles_cache
    merged = _builtin_prompt_profiles()
    if _LAB_PROFILES_PATH.exists():
        try:
            with open(_LAB_PROFILES_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            overrides = data.get("profiles") or {}
            for pid in PROFILE_IDS:
                ov = overrides.get(pid)
                if not isinstance(ov, dict) or pid not in merged:
                    continue
                for key, val in ov.items():
                    if key == "id" or val is None:
                        continue
                    merged[pid][key] = val
        except Exception:
            pass
    _profiles_cache = merged
    return merged


def is_profiles_customized() -> bool:
    return _LAB_PROFILES_PATH.exists()


def list_prompt_profiles() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for pid in PROFILE_IDS:
        p = get_merged_prompt_profiles()[pid]
        out.append(
            {
                "id": p["id"],
                "label": p["label"],
                "emoji": p.get("emoji") or "",
                "blurb": p.get("blurb") or "",
                "variant_hint": p.get("variant_hint") or "",
            }
        )
    return out


def list_prompt_profiles_full() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for pid in PROFILE_IDS:
        p = get_merged_prompt_profiles()[pid]
        extra = p.get("output_extra") or []
        if not isinstance(extra, list):
            extra = []
        out.append(
            {
                "id": p["id"],
                "label": p.get("label") or "",
                "emoji": p.get("emoji") or "",
                "blurb": p.get("blurb") or "",
                "variant_hint": p.get("variant_hint") or "",
                "max_tokens": int(p.get("max_tokens") or 2200),
                "temperature": float(p.get("temperature") or 0.8),
                "output_extra": [str(x) for x in extra if str(x).strip()],
                "system": p.get("system") or "",
            }
        )
    return out


def _normalize_profile_payload(raw: Dict[str, Any], pid: str) -> Dict[str, Any]:
    label = str(raw.get("label") or "").strip()
    system = str(raw.get("system") or "").strip()
    if not label:
        raise ValueError(f"{pid}: 缺少 label")
    if not system:
        raise ValueError(f"{pid}: system prompt 不能为空")
    try:
        max_tokens = int(raw.get("max_tokens") or 2200)
    except Exception as exc:
        raise ValueError(f"{pid}: max_tokens 无效") from exc
    try:
        temperature = float(raw.get("temperature") if raw.get("temperature") is not None else 0.8)
    except Exception as exc:
        raise ValueError(f"{pid}: temperature 无效") from exc
    if max_tokens < 500 or max_tokens > 12000:
        raise ValueError(f"{pid}: max_tokens 需在 500~12000")
    if temperature < 0 or temperature > 2:
        raise ValueError(f"{pid}: temperature 需在 0~2")
    extra_raw = raw.get("output_extra")
    if isinstance(extra_raw, str):
        output_extra = [x.strip() for x in extra_raw.split(",") if x.strip()]
    elif isinstance(extra_raw, list):
        output_extra = [str(x).strip() for x in extra_raw if str(x).strip()]
    else:
        output_extra = []
    return {
        "label": label,
        "emoji": str(raw.get("emoji") or "").strip(),
        "blurb": str(raw.get("blurb") or "").strip(),
        "variant_hint": str(raw.get("variant_hint") or "").strip(),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "output_extra": output_extra,
        "system": system,
    }


def save_prompt_profiles(profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(profiles, list) or not profiles:
        return {"success": False, "error": "profiles 不能为空"}
    by_id: Dict[str, Dict[str, Any]] = {}
    for raw in profiles:
        if not isinstance(raw, dict):
            continue
        pid = str(raw.get("id") or "").strip()
        if pid not in PROFILE_IDS:
            continue
        try:
            by_id[pid] = _normalize_profile_payload(raw, pid)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
    missing = [pid for pid in PROFILE_IDS if pid not in by_id]
    if missing:
        return {"success": False, "error": f"缺少配置: {', '.join(missing)}"}
    _LAB_PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"profiles": by_id}
    with open(_LAB_PROFILES_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    _invalidate_profiles_cache()
    return {
        "success": True,
        "items": list_prompt_profiles_full(),
        "customized": True,
        "path": str(_LAB_PROFILES_PATH),
    }


def reset_prompt_profiles() -> Dict[str, Any]:
    if _LAB_PROFILES_PATH.exists():
        _LAB_PROFILES_PATH.unlink()
    _invalidate_profiles_cache()
    return {
        "success": True,
        "items": list_prompt_profiles_full(),
        "customized": False,
    }


def get_prompt_profile(profile_id: str) -> Dict[str, Any]:
    merged = get_merged_prompt_profiles()
    return dict(merged.get(profile_id) or merged["general"])


def _build_cot(
    tmpls: List[Dict[str, Any]],
    topic: str,
    formula: Dict[str, str],
    profile: Dict[str, Any],
) -> List[str]:
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
    steps.append(f"后处理配置「{profile.get('label')}」→ {profile.get('variant_hint') or '三版本'}")
    if profile.get("id") == "general":
        steps.append("归纳 prompt_snippets 供下次复用")
    elif profile.get("id") == "technical":
        steps.append("分化：技术面 / 宏观传导 / 场景计划")
    elif profile.get("id") == "longform_video":
        steps.append("分化：口播大纲 / 分镜 / 完整视频稿")
    else:
        steps.append("并行生成 3 个叙事变体，供并排挑选")
    return steps


def _fallback_variants(
    profile: Dict[str, Any],
    topic: str,
    tmpls: List[Dict[str, Any]],
    formula: Dict[str, str],
) -> List[Dict[str, Any]]:
    hook0 = (tmpls[0].get("hooks") if tmpls else "") or f"关于{topic}，有个反直觉的点"
    tension = (tmpls[0].get("tension") if tmpls else "预期与成本错位") or "预期与成本错位"
    pid = profile.get("id") or "general"

    if pid == "technical":
        return [
            {
                "id": "A",
                "label": "技术面快评",
                "hook": f"{topic}：结构比情绪更重要",
                "content": (
                    f"「{topic}」当前更值得看结构而非单日涨跌。\n"
                    f"关键位附近若放量失败，往往意味着 {(tmpls[0].get('emotion') if tmpls else '预期')} 被修正。\n"
                    f"短线思路：等确认再动，别在消息尖刺里追。"
                ),
            },
            {
                "id": "B",
                "label": "宏观解读",
                "hook": f"若把 {topic} 放进流动性框架",
                "content": (
                    f"把「{topic}」放进利率/流动性框架：政策预期 → 美元/风险资产 → .crypto  beta。\n"
                    f"数据或 Fed 口径若偏鹰，高 beta 往往先承压；偏鸽则反弹但需看持续性。\n"
                    f"宏观不是直接喊单，而是定优先级。"
                ),
            },
            {
                "id": "C",
                "label": "场景交易计划",
                "hook": f"围绕 {topic} 的三场景推演",
                "content": (
                    f"围绕「{topic}」三场景：\n"
                    f"1) 延续：趋势不破，回撤接多/空需带止损；\n"
                    f"2) 震荡：区间内高抛低吸，缩小仓位；\n"
                    f"3) 失效：关键位失守则认错，不扛单。\n"
                    f"计划写在动手前，比盘中临时改口径更省成本。"
                ),
            },
        ]

    if pid == "longform_video":
        return [
            {
                "id": "A",
                "label": "口播大纲",
                "hook": hook0,
                "content": (
                    f"## Hook\n{hook0}\n\n"
                    f"## 段1 · 问题\n为什么「{topic}」现在被误解？{tension}\n\n"
                    f"## 段2 · 拆解\n按「{formula.get('label')}」：{formula.get('blurb')}\n\n"
                    f"## 段3 ·  takeaway\n给观众的 3 条可带走结论 + 关注/收藏 CTA"
                ),
            },
            {
                "id": "B",
                "label": "分镜脚本",
                "hook": "镜1：大字标题 + 旁白",
                "content": (
                    f"镜1 画面：标题卡「{topic}」｜旁白：{hook0}\n"
                    f"镜2 画面：图表/新闻截图｜旁白：冲突点 {tension}\n"
                    f"镜3 画面：三点列表动画｜旁白：核心论点展开\n"
                    f"镜4 画面：案例/对比｜旁白：结合卡片洞察\n"
                    f"镜5 画面：主持人总结｜旁白：风险提醒 + CTA"
                ),
            },
            {
                "id": "C",
                "label": "完整视频稿",
                "hook": hook0,
                "content": (
                    f"{hook0}\n\n"
                    f"今天聊「{topic}」。很多人只盯着表面波动，但真正要理解的是 {tension}。\n\n"
                    f"我会按三个部分讲清楚：先讲误区，再讲框架，最后讲你可以怎么验证。\n\n"
                    f"（此处为兜底短稿，模型恢复后会生成 800+ 字完整口播稿。）\n\n"
                    f"如果你也在跟踪这个主题，评论区说说你的观察。"
                ),
            },
        ]

    base = (
        f"{hook0}\n\n"
        f"大多数人谈「{topic}」只看到表面，真正的冲突是：{tension}。\n"
        f"按「{formula.get('label')}」思路：{formula.get('blurb')}。\n"
        f"可先从一件小事验证，再决定是否加码。"
    )
    return [
        {"id": "A", "label": "情绪刺眼", "hook": hook0, "content": base},
        {
            "id": "B",
            "label": "干货数据",
            "hook": f"上周我被「{topic}」打脸了一次",
            "content": (
                f"上周我被「{topic}」打脸了一次。\n"
                f"复盘后只留下三条：把假设写下来、小步验证、公开结果。\n"
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
                f"3) 失败的止损线在哪？"
            ),
        },
    ]


# 兼容旧引用
LAB_SYSTEM = PROMPT_PROFILES["general"]["system"]


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


def _cards_brief(tmpls: List[Dict[str, Any]], *, title: str = "灵感卡片") -> str:
    if not tmpls:
        return ""
    lines = [f"{title}："]
    for i, tmpl in enumerate(tmpls, 1):
        factors = tmpl.get("factors") or {}
        cat = str(factors.get("material_category") or "").strip()
        cat_s = category_label(cat) if cat else ""
        lines.append(
            f"卡片{i}(#{tmpl.get('id')} 「{tmpl.get('source_title') or ''}」"
            f"{f' · 素材={cat_s}' if cat_s else ''}):\n"
            f"- hook: {tmpl.get('hooks') or factors.get('hook') or ''}\n"
            f"- pattern: {tmpl.get('pattern') or ''}\n"
            f"- emotion: {tmpl.get('emotion') or ''}\n"
            f"- tension: {tmpl.get('tension') or ''}\n"
            f"- narrative: {factors.get('narrative_type') or tmpl.get('emotion') or ''}\n"
            f"- use_case: {factors.get('use_case') or ''}\n"
            f"- keywords: {', '.join(tmpl.get('keywords') or [])}\n"
            f"- tags: {', '.join(tmpl.get('tags') or [])}\n"
        )
    return "\n".join(lines) + "\n"


def _structure_brief(tmpls: List[Dict[str, Any]], *, category: str = "") -> str:
    """类目结构模板：句式骨架 + 步骤 + 案例，供生成时仿写（勿照搬数字）。"""
    if not tmpls:
        return ""
    cat_s = category_label(category) if category else "当前素材"
    lines = [
        f"类目结构模板（{cat_s} · 参考段落结构/句式与案例节奏，"
        f"热点细节与具体数据请按用户主题改写，勿照搬案例数字）："
    ]
    for i, tmpl in enumerate(tmpls, 1):
        factors = tmpl.get("factors") or {}
        struct = factors.get("structure")
        struct_s = ""
        if isinstance(struct, list) and struct:
            struct_s = " → ".join(str(x).strip() for x in struct if str(x).strip())
        ex = factors.get("example") if isinstance(factors.get("example"), dict) else {}
        ex_hook = str(ex.get("hook") or "").strip()
        ex_body = str(ex.get("body") or "").strip()
        block = (
            f"结构{i}(#{tmpl.get('id')} 「{tmpl.get('source_title') or ''}」):\n"
            f"- pattern: {tmpl.get('pattern') or ''}\n"
            f"- hook范式: {tmpl.get('hooks') or factors.get('hook') or ''}\n"
            f"- 步骤: {struct_s or '（见 raw_text）'}\n"
            f"- 叙事: {factors.get('narrative_type') or tmpl.get('emotion') or ''}\n"
            f"- 冲突: {tmpl.get('tension') or ''}\n"
            f"- 适用: {factors.get('use_case') or ''}\n"
            f"- 核心: {factors.get('core_concept') or ''}\n"
        )
        if ex_hook or ex_body:
            block += f"- 案例钩子: {ex_hook}\n"
            if ex_body:
                block += f"- 案例正文:\n{ex_body}\n"
        lines.append(block)
    return "\n".join(lines) + "\n"


def lab_compose(
    *,
    template_ids: Optional[Sequence[int]] = None,
    topic: str,
    formula_id: str = "contrarian",
    prompt_profile_id: str = "general",
    platform_style: str = "X/Twitter",
    extra_prompt: str = "",
    variant_count: int = 3,
    bump_weight: bool = True,
    material_category: str = "",
) -> Dict[str, Any]:
    """工作台一键融合：返回 CoT + 多版本（支持后处理提示词配置）。"""
    topic = (topic or "").strip()
    if not topic:
        return {"success": False, "error": "请填写热点主题"}
    formula = FORMULA_PRESETS.get(formula_id) or FORMULA_PRESETS["contrarian"]
    profile = get_prompt_profile(prompt_profile_id)
    ids = [int(x) for x in (template_ids or []) if x is not None]
    tmpls = get_templates_by_ids(ids) if ids else []
    struct_tmpls: List[Dict[str, Any]] = []
    cat = str(material_category or "").strip()
    if cat and cat not in ("all", ""):
        picked = set(ids)
        struct_tmpls = [
            t
            for t in list_templates(
                material_category=cat,
                category_template=True,
                status="active",
                limit=6,
            )
            if int(t.get("id") or 0) not in picked
        ][:3]
    cot = _build_cot(tmpls, topic, formula, profile)

    user_prompt = (
        f"后处理配置：{profile.get('label')} — {profile.get('blurb')}\n"
        f"平台风格：{platform_style or 'X/Twitter'}\n"
        f"热点主题：{topic}\n"
        f"叙事配方：{formula.get('label')} — {formula.get('recipe')}\n"
        f"需要变体数：{max(2, min(3, int(variant_count or 3)))}\n"
    )
    if cat and cat not in ("all", ""):
        user_prompt += f"当前素材类目：{category_label(cat)}\n"
    if struct_tmpls:
        user_prompt += _structure_brief(struct_tmpls, category=cat)
    if tmpls:
        user_prompt += _cards_brief(tmpls)
    if extra_prompt:
        user_prompt += f"补充要求：{extra_prompt.strip()}\n"
    user_prompt += "请严格按 system 要求的 JSON 结构输出。\n"

    provider = ""
    payload: Dict[str, Any] = {}
    ai_error = ""
    try:
        from utils.ai_client import generate_text

        result = generate_text(
            user_prompt,
            system_prompt=str(profile.get("system") or LAB_SYSTEM),
            temperature=float(profile.get("temperature") or 0.8),
            max_tokens=int(profile.get("max_tokens") or 2200),
        )
        provider = str(result.get("provider") or "")
        if not result.get("success"):
            ai_error = str(result.get("error") or "生成失败")
        else:
            payload = _extract_json(str(result.get("content") or ""))
    except Exception as e:
        ai_error = f"AI 调用失败: {e}"

    thinking = payload.get("thinking") if isinstance(payload.get("thinking"), list) else cot
    prompt_snippets = payload.get("prompt_snippets") if isinstance(payload.get("prompt_snippets"), list) else []
    video_meta = payload.get("video_meta") if isinstance(payload.get("video_meta"), dict) else {}
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
                "hook": str(v.get("hook") or content.split("\n", 1)[0][:120]),
                "content": content,
            }
        )

    if not variants:
        variants = _fallback_variants(profile, topic, tmpls, formula)
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
            "prompt_profile": profile.get("id"),
            "template_ids": [t.get("id") for t in tmpls],
            "structure_template_ids": [t.get("id") for t in struct_tmpls],
            "material_category": cat or "",
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
                "prompt_profile": profile.get("id"),
                "variant_id": v["id"],
                "variant_label": v["label"],
                "template_ids": [t.get("id") for t in tmpls],
                "structure_template_ids": [t.get("id") for t in struct_tmpls],
                "material_category": cat or "",
                "mode": "lab_compose",
                "cot": thinking,
                "prompt_snippets": prompt_snippets,
                "video_meta": video_meta,
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
        "prompt_profile": {
            "id": profile.get("id"),
            "label": profile.get("label"),
            "variant_hint": profile.get("variant_hint"),
        },
        "prompt_snippets": [str(x) for x in prompt_snippets][:8],
        "video_meta": video_meta,
        "cot": [str(x) for x in (thinking or cot)][:10],
        "variants": variants,
        "templates": tmpls,
        "path": path,
        "provider": provider,
        "content": variants[0]["content"],
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
