# coding=utf-8
"""从多条帖子 AI 合成一条可复用语料模板。"""

from __future__ import annotations

import json
import random
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from corpus.db import create_template, init_db

SYNTH_SYSTEM = """你是爆款内容炼金师。用户会给出若干原始帖子，请综合它们的共性，炼成一条可复用的「梗骨架」模板。
只输出一个 JSON 对象，不要 markdown，不要解释。字段：
{
  "pattern": "抽象句式模板，用【占位】标可替换部分",
  "emotion": "主情绪短词：自嘲/反转/焦虑/狂欢/共鸣/愤怒/炫耀等",
  "tension": "冲突逻辑一句话",
  "keywords": ["触发词1","触发词2","触发词3"],
  "hooks": "开头抓人手法",
  "notes": "创作注意事项",
  "title": "给这条模板起的短名（10字内）"
}
规则：
1. 必须抽象，去掉具体人名/公司/日期。
2. 融合多帖共性，不要只抄其中一条。
3. keywords 3~8 个。
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


def _brief(post: Dict[str, Any], idx: int) -> str:
    title = str(post.get("title") or "").strip()
    raw = str(
        post.get("raw") or post.get("content") or post.get("summary") or ""
    ).strip()
    plat = str(post.get("platform") or post.get("platform_id") or "")
    body = raw[:600] + ("…" if len(raw) > 600 else "")
    return f"[{idx}] 平台={plat}\n标题={title or '(无)'}\n正文={body or '(空)'}\n"


def synthesize_from_posts(
    posts: List[Dict[str, Any]],
    *,
    tags: Optional[List[str]] = None,
    note: str = "",
) -> Dict[str, Any]:
    """
    用多条帖子合成一条模板并入库。
    posts 项：title/raw/content/summary/platform/platform_id/url/href/key
    """
    init_db()
    clean = [p for p in (posts or []) if isinstance(p, dict)]
    if len(clean) < 1:
        return {"success": False, "error": "至少需要 1 条帖子"}

    blob = "\n---\n".join(_brief(p, i + 1) for i, p in enumerate(clean[:12]))
    if note:
        blob += f"\n用户说明：{note.strip()}\n"

    factors: Dict[str, Any] = {}
    provider = ""
    try:
        from utils.ai_client import generate_text

        result = generate_text(
            blob,
            system_prompt=SYNTH_SYSTEM,
            temperature=0.45,
            max_tokens=1000,
        )
        provider = str(result.get("provider") or "")
        if result.get("success"):
            factors = _extract_json(str(result.get("content") or ""))
    except Exception as e:
        return {"success": False, "error": f"AI 调用失败: {e}"}

    if not factors.get("pattern"):
        # 兜底：取第一条抽象化
        first = clean[0]
        text = str(first.get("title") or first.get("content") or first.get("raw") or "")[:60]
        factors = {
            "pattern": f"关于【话题】：{text}…" if text else "【话题】有个反转",
            "emotion": "共鸣",
            "tension": "预期违背",
            "keywords": ["热点"],
            "hooks": "场景开场",
            "title": "合成模板",
            "notes": "AI 解析失败兜底",
        }
        provider = provider or "fallback"

    keywords = factors.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [x.strip() for x in re.split(r"[,，、\s]+", keywords) if x.strip()]
    if not isinstance(keywords, list):
        keywords = []

    now = datetime.now().isoformat(timespec="seconds")
    sid = uuid.uuid4().hex[:10]
    sources = []
    for p in clean:
        sources.append(
            {
                "platform": p.get("platform") or p.get("platform_id") or "",
                "key": p.get("key") or p.get("source_key") or "",
                "url": p.get("url") or p.get("href") or "",
                "title": (p.get("title") or "")[:80],
            }
        )

    provenance = {
        "steps": [
            {
                "layer": "collect",
                "via": "multi-post-synth",
                "count": len(clean),
                "sources": sources,
                "at": now,
            },
            {
                "layer": "deconstruct",
                "provider": provider,
                "prompt": "corpus.synthesize.SYNTH_SYSTEM",
                "mode": "synthesize",
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

    title = str(factors.get("title") or f"合成·{len(clean)}帖")[:40]
    template = create_template(
        source_platform="synth",
        source_url="",
        source_key=f"synth-{sid}",
        source_title=title,
        raw_text="\n\n".join(
            str(p.get("title") or p.get("content") or p.get("raw") or "")[:200]
            for p in clean[:8]
        ),
        pattern=str(factors.get("pattern") or ""),
        emotion=str(factors.get("emotion") or ""),
        tension=str(factors.get("tension") or ""),
        keywords=[str(x) for x in keywords][:12],
        hooks=str(factors.get("hooks") or ""),
        tags=list(tags or []) + ["合成"],
        provenance=provenance,
        factors={**factors, "source_posts": sources, "notes": factors.get("notes") or ""},
        status="active",
        quality="unrated",
        weight=1.0,
    )
    return {
        "success": True,
        "template": template,
        "factors": factors,
        "provider": provider,
        "source_count": len(clean),
    }


def pick_random_posts(pool: List[Dict[str, Any]], n: int = 3) -> List[Dict[str, Any]]:
    items = [p for p in (pool or []) if isinstance(p, dict)]
    if not items:
        return []
    n = max(1, min(int(n or 3), len(items), 12))
    return random.sample(items, n)
