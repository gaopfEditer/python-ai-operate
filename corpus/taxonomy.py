# coding=utf-8
"""爆款语料两级标签体系 + 四要素字段约定。"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# domain → 一级 → 二级
TAG_TREE: Dict[str, Dict[str, List[str]]] = {
    "Web3交易": {
        "交易策略/认知": [
            "实盘战绩/晒单",
            "指标/K线解构",
            "巨鲸/SmartMoney追踪",
            "交易心理/避坑",
        ],
        "项目/赛道分析": [
            "Alpha发现/潜伏",
            "研报/空投教程",
            "生态/赛道前景",
            "项目暴雷/揭露",
        ],
        "情绪与市场心理": [
            "FOMO/牛市狂欢",
            "恐慌/熊市抱团",
            "信仰/Web3价值观",
            "黑天鹅/宏观解读",
        ],
        "营销转化/推广": [
            "交易所/工具体验",
            "跟单/返佣引导",
            "社区/社群招募",
            "福利/抽奖Giveaway",
        ],
    },
    "泛娱乐": {
        "职场/打工人": [
            "发疯/精神状态",
            "黑话/摸鱼吐槽",
            "薪资/对齐颗粒度",
            "反牛马/整顿职场",
        ],
        "梗图/文化": [
            "地狱笑话/暗黑幽默",
            "表情包/Meme二次创作",
            "热点梗追击",
            "抽象/无厘头",
        ],
        "人际/情感吐槽": [
            "奇葩见闻/吃瓜",
            "当代男女现状",
            "社交毒瘤/扎心痛点",
            "反转/爽文结局",
        ],
        "科技/时代讽刺": [
            "AI替代/赛博危机",
            "消费陷阱/智商税",
            "低水平停滞/文化反思",
            "赛博朋克现实",
        ],
    },
}

FORMAT_CHOICES = ["Long-form", "Short-form", "Long-form Thread", "Short-form 金句", "短帖+图"]
HOOK_TYPES = [
    "反直觉",
    "制造焦虑",
    "利益诱惑",
    "打脸反转",
    "共鸣痛点",
    "猎奇八卦",
    "揭秘内幕",
    "FOMO催促",
    "悬念提问",
]
CTA_TYPES = [
    "引导评论区吵架/打字",
    "引导点赞收藏",
    "引导点击链接",
    "引导关注",
    "引导使用工具",
    "无明显CTA",
]


def flatten_tag_options() -> List[Tuple[str, str, str]]:
    rows: List[Tuple[str, str, str]] = []
    for domain, primaries in TAG_TREE.items():
        for primary, secondaries in primaries.items():
            for sec in secondaries:
                rows.append((domain, primary, sec))
    return rows


def normalize_tags(parsed: Dict[str, Any]) -> Dict[str, str]:
    """尽量对齐到标签树；对不上也保留模型原文。"""
    domain = str(parsed.get("domain") or "").strip()
    tags = parsed.get("tags") if isinstance(parsed.get("tags"), dict) else {}
    primary = str(tags.get("primary") or parsed.get("primary") or "").strip()
    secondary = str(tags.get("secondary") or parsed.get("secondary") or "").strip()

    # 模糊匹配：二级命中则回填一级/domain
    for d, p, s in flatten_tag_options():
        if secondary and (secondary == s or secondary in s or s in secondary):
            return {"domain": d, "primary": p, "secondary": s}
    for d, p, s in flatten_tag_options():
        if primary and (primary == p or primary in p or p in primary):
            # 选该一级下第一个二级或保留原文二级
            sec = secondary if secondary in TAG_TREE.get(d, {}).get(p, []) else (
                TAG_TREE[d][p][0] if TAG_TREE[d][p] else secondary
            )
            return {"domain": d, "primary": p, "secondary": sec or secondary}
    if not domain:
        domain = "泛娱乐" if any(k in (primary + secondary) for k in ("职场", "梗", "吃瓜", "情感")) else "Web3交易"
    return {"domain": domain or "泛娱乐", "primary": primary or "未分类", "secondary": secondary or "未分类"}


def tags_as_list(domain: str, primary: str, secondary: str, extra: List[str] | None = None) -> List[str]:
    out: List[str] = []
    for t in [domain, primary, secondary, *(extra or [])]:
        t = (t or "").strip()
        if t and t not in out:
            out.append(t)
    return out


def taxonomy_prompt_block() -> str:
    lines = ["可选标签（优先从中选择，不要自造一级标签）："]
    for domain, primaries in TAG_TREE.items():
        lines.append(f"【{domain}】")
        for primary, secondaries in primaries.items():
            lines.append(f"  - 一级「{primary}」→ 二级：{' / '.join(secondaries)}")
    return "\n".join(lines)
