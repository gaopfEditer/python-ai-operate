# coding=utf-8
"""预置 Post Lab 素材类目结构模板（可重复运行，按 source_key  upsert）。"""

from __future__ import annotations

from typing import Any, Dict, List

from corpus.db import create_template, init_db, list_templates

SEED_TEMPLATES: List[Dict[str, Any]] = [
    {
        "source_platform": "seed",
        "source_key": "tpl-market-structure",
        "source_title": "行情快评 · 事件→传导→观点",
        "pattern": (
            "【时间/事件】刚出，市场第一反应是【直觉解读】。"
            "但细看【关键数据/结构位】，真正影响的是【传导链条】。"
            "我的看法：短期【震荡/偏多/偏空】，关注【观察位】，失效看【条件】。"
        ),
        "emotion": "冷静",
        "tension": "直觉 vs 数据",
        "hooks": "刚出数/刚官宣，别急着下结论——",
        "keywords": ["宏观", "关键位", "传导", "观察", "失效"],
        "tags": ["行情快评", "类目模板", "结构"],
        "factors": {
            "material_category": "market",
            "is_category_template": True,
            "lab_profile": "technical",
            "narrative_type": "宏观快评",
            "use_case": "数据公布、美联储、突发政策、大盘波动后的短评",
            "hook": "事件刚落地，先别跟着情绪跑——",
            "structure": ["事件锚点", "第一反应", "深层传导", "观点+观察位+失效"],
        },
    },
    {
        "source_platform": "seed",
        "source_key": "tpl-signal-structure",
        "source_title": "交易信号 · 币种+方向+风控",
        "pattern": (
            "【币种/板块】：【做多/做空/观望】。"
            "逻辑：【1句核心原因】。"
            "计划：入场【区间/条件】，止盈【目标】，止损【价位/条件】。"
            "备注：【杠杆/周期/风险提示】"
        ),
        "emotion": "果断",
        "tension": "机会 vs 风控",
        "hooks": "【币种】这边有说法——",
        "keywords": ["入场", "止盈", "止损", "逻辑", "风控"],
        "tags": ["交易信号", "类目模板", "结构"],
        "factors": {
            "material_category": "signal",
            "is_category_template": True,
            "lab_profile": "technical",
            "narrative_type": "交易计划",
            "use_case": "列表信号、KOL 喊单、带价位与方向的推文",
            "hook": "$【币种】 有说法——",
            "structure": ["标的+方向", "核心逻辑", "入场/止盈/止损", "杠杆与风险提示"],
        },
    },
    {
        "source_platform": "seed",
        "source_key": "tpl-xhot-structure",
        "source_title": "X 热帖 · 钩子→反转→收束",
        "pattern": (
            "【刺眼钩子/反常识一句】。"
            "大多数人以为【常见误区】，其实【反转洞察】。"
            "举个例子：【具体场景/数据/经历】。"
            "所以：【可带走的结论/行动】"
        ),
        "emotion": "挑衅",
        "tension": "常识 vs 反转",
        "hooks": "说句得罪人的：",
        "keywords": ["反转", "误区", "洞察", "例子", "结论"],
        "tags": ["X热帖", "类目模板", "结构"],
        "factors": {
            "material_category": "x_hot",
            "is_category_template": True,
            "lab_profile": "general",
            "narrative_type": "反常识",
            "use_case": "短帖爆点、争议观点、热榜拆解后的再创作",
            "hook": "说句可能得罪人的——",
            "structure": ["钩子", "误区", "反转", "例证", "收束结论"],
        },
    },
    {
        "source_platform": "seed",
        "source_key": "tpl-thread-structure",
        "source_title": "长推 Thread · 目录→展开→收束",
        "pattern": (
            "1/ 【主题】为什么现在值得聊？\n"
            "2/ 【背景/误区】大多数人忽略了【关键点】\n"
            "3/ 【核心论点A】+ 例子\n"
            "4/ 【核心论点B】+ 数据/经历\n"
            "5/ 【怎么落地】给读者 3 条可执行建议\n"
            "6/ 【总结】一句带走 + 欢迎补充"
        ),
        "emotion": "展开",
        "tension": "浅读 vs 深读",
        "hooks": "Thread 🧵 关于【主题】，有 6 点想讲清楚：",
        "keywords": ["Thread", "论点", "例子", "落地", "总结"],
        "tags": ["长推", "类目模板", "结构"],
        "factors": {
            "material_category": "thread",
            "is_category_template": True,
            "lab_profile": "longform_video",
            "narrative_type": "Thread",
            "use_case": "长推、口播大纲、视频分镜前的结构化展开",
            "hook": "Thread 🧵 关于【主题】——",
            "structure": ["开场钩子", "背景误区", "论点展开", "例证", "落地建议", "收束"],
        },
    },
]


def seed_category_templates(*, replace: bool = False) -> Dict[str, Any]:
    """写入三类目结构模板。replace=False 时仅 upsert，不删已有。"""
    init_db()
    created: List[Dict[str, Any]] = []
    for row in SEED_TEMPLATES:
        item = create_template(
            source_platform=row["source_platform"],
            source_key=row["source_key"],
            source_title=row["source_title"],
            pattern=row["pattern"],
            emotion=row["emotion"],
            tension=row["tension"],
            hooks=row["hooks"],
            keywords=row.get("keywords") or [],
            tags=row.get("tags") or [],
            quality="good",
            weight=2.0,
            status="active",
            provenance={"steps": [{"layer": "seed", "note": "category_template"}]},
            factors=row.get("factors") or {},
        )
        created.append(item)
    return {
        "success": True,
        "count": len(created),
        "items": created,
        "categories": ["market", "signal", "x_hot", "thread"],
    }


if __name__ == "__main__":
    result = seed_category_templates()
    print(f"已写入 {result['count']} 个类目结构模板：")
    for it in result["items"]:
        cat = (it.get("factors") or {}).get("material_category", "?")
        print(f"  #{it.get('id')} [{cat}] {it.get('source_title')}")
