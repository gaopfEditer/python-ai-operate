# coding=utf-8
"""灵感碰撞素材类目：筛选语料卡、类目结构模板。"""

from __future__ import annotations

from typing import Any, Dict, List

# 加密 X 生态内容支柱（占比见 content_mix）
MATERIAL_CATEGORIES: List[Dict[str, str]] = [
    {"id": "market", "label": "量价技术", "emoji": "📐"},
    {"id": "onchain", "label": "链上聪明钱", "emoji": "🐋"},
    {"id": "derivatives", "label": "情绪衍生品", "emoji": "⚖️"},
    {"id": "kol_review", "label": "KOL复盘", "emoji": "🧭"},
    {"id": "toolkit", "label": "工具投研", "emoji": "🧰"},
    {"id": "tokenomics", "label": "代币Alpha", "emoji": "🪙"},
    {"id": "engagement", "label": "模因互动", "emoji": "🎭"},
    {"id": "signal", "label": "交易信号", "emoji": "📡"},
    {"id": "thread", "label": "长推Thread", "emoji": "🧵"},
    {"id": "capture", "label": "快捕碎片", "emoji": "⚡"},
    {"id": "general", "label": "通用灵感", "emoji": "💡"},
]

# 人设内容配比建议（供 Lab 提示与面板展示）
CONTENT_MIX: List[Dict[str, Any]] = [
    {"category": "market", "pct": 30, "role": "树立专业度与交易审美"},
    {"category": "onchain", "pct": 15, "role": "即时信息差与预警"},
    {"category": "derivatives", "pct": 10, "role": "极端情绪与反转机会"},
    {"category": "kol_review", "pct": 20, "role": "引流私域、制造转化悬念"},
    {"category": "toolkit", "pct": 8, "role": "高收藏、算法加权"},
    {"category": "tokenomics", "pct": 7, "role": "平淡行情的高质量长内容"},
    {"category": "engagement", "pct": 10, "role": "人格化与互动率"},
]

_CATEGORY_MAP = {c["id"]: c for c in MATERIAL_CATEGORIES}


def list_material_categories() -> List[Dict[str, str]]:
    return [dict(c) for c in MATERIAL_CATEGORIES]


def list_content_mix() -> List[Dict[str, Any]]:
    out = []
    for row in CONTENT_MIX:
        cid = row["category"]
        meta = _CATEGORY_MAP.get(cid) or {}
        out.append(
            {
                **row,
                "label": meta.get("label") or cid,
                "emoji": meta.get("emoji") or "",
            }
        )
    return out


def category_label(category_id: str) -> str:
    cid = str(category_id or "").strip()
    if not cid or cid == "uncategorized":
        return "未分类"
    hit = _CATEGORY_MAP.get(cid)
    if hit:
        return hit["label"]
    return cid


def template_material_category(tmpl: Dict[str, Any]) -> str:
    factors = tmpl.get("factors") if isinstance(tmpl.get("factors"), dict) else {}
    return str(factors.get("material_category") or "").strip()


def is_category_template(tmpl: Dict[str, Any]) -> bool:
    factors = tmpl.get("factors") if isinstance(tmpl.get("factors"), dict) else {}
    return bool(factors.get("is_category_template"))


def material_category_stats(
    *,
    db_path=None,
) -> Dict[str, Any]:
    from corpus.db import _json_loads, connect, init_db

    init_db(db_path)
    counts: Dict[str, int] = {c["id"]: 0 for c in MATERIAL_CATEGORIES}
    counts["uncategorized"] = 0
    tpl_counts: Dict[str, int] = {c["id"]: 0 for c in MATERIAL_CATEGORIES}
    tpl_counts["uncategorized"] = 0
    total = 0
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT factors_json FROM templates WHERE status='active'"
        ).fetchall()
    for row in rows:
        total += 1
        factors = _json_loads(row["factors_json"], {})
        cat = str(factors.get("material_category") or "").strip() or "uncategorized"
        if cat not in counts:
            counts[cat] = 0
            tpl_counts[cat] = 0
        counts[cat] += 1
        if factors.get("is_category_template"):
            tpl_counts[cat] = tpl_counts.get(cat, 0) + 1
    categories = []
    for c in MATERIAL_CATEGORIES:
        cid = c["id"]
        categories.append(
            {
                **c,
                "count": counts.get(cid, 0),
                "template_count": tpl_counts.get(cid, 0),
            }
        )
    categories.append(
        {
            "id": "uncategorized",
            "label": "未分类",
            "emoji": "📁",
            "count": counts.get("uncategorized", 0),
            "template_count": tpl_counts.get("uncategorized", 0),
        }
    )
    return {
        "categories": categories,
        "total": total,
        "content_mix": list_content_mix(),
    }
