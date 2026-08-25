# coding=utf-8
"""Post Lab 素材类目：筛选语料卡、类目结构模板。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

MATERIAL_CATEGORIES: List[Dict[str, str]] = [
    {"id": "x_hot", "label": "X 热帖", "emoji": "🔥"},
    {"id": "market", "label": "行情快评", "emoji": "📊"},
    {"id": "build", "label": "Build 复盘", "emoji": "🧪"},
    {"id": "thread", "label": "长推 Thread", "emoji": "🧵"},
    {"id": "meme", "label": "段子讽刺", "emoji": "🎭"},
    {"id": "signal", "label": "交易信号", "emoji": "📡"},
    {"id": "capture", "label": "快捕碎片", "emoji": "⚡"},
    {"id": "general", "label": "通用灵感", "emoji": "💡"},
]

_CATEGORY_MAP = {c["id"]: c for c in MATERIAL_CATEGORIES}


def list_material_categories() -> List[Dict[str, str]]:
    return [dict(c) for c in MATERIAL_CATEGORIES]


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
    }
