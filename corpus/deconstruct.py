# coding=utf-8
"""智能拆解层：Prompt + LLM → 梗骨架 JSON → 写入 SQLite。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from corpus.db import create_template, init_db

DECONSTRUCT_SYSTEM = """你是爆款内容拆解专家。目标：把具体帖子炼成可复用的「梗骨架」，去掉一时一事的细节。
只输出一个 JSON 对象，不要 markdown 代码块，不要解释。字段如下：
{
  "pattern": "句式模板，用【占位】标出可替换部分，例如：原来【A】才是【B】的真相",
  "emotion": "主情绪标签，从下列选一个或自拟短词：自嘲/反转/焦虑/狂欢/共鸣/愤怒/炫耀/共鸣安慰",
  "tension": "冲突逻辑，一句话，如：高低落差 / 新旧对立 / 预期违背 / 身份错位",
  "keywords": ["核心黑话或触发词1", "触发词2", "触发词3"],
  "hooks": "开头抓人的手法一句话",
  "notes": "可选，创作时注意事项"
}
规则：
1. pattern 必须抽象，禁止保留具体人名、公司名、日期（可用【人物】【公司】【事件】代替）。
2. emotion / tension 要短、可检索。
3. keywords 3~8 个，偏平台黑话与情绪触发词。
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


def _fallback_factors(title: str, raw: str) -> Dict[str, Any]:
    text = (raw or title or "").strip()
    cut = text[:80] + ("…" if len(text) > 80 else "")
    words = re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Za-z][A-Za-z0-9_-]{2,}", text)
    uniq: List[str] = []
    for w in words:
        if w not in uniq:
            uniq.append(w)
        if len(uniq) >= 6:
            break
    return {
        "pattern": f"关于【话题】：{cut}" if cut else "【话题】有个反转",
        "emotion": "共鸣",
        "tension": "预期违背",
        "keywords": uniq or ["热点"],
        "hooks": "用具体场景开场",
        "notes": "AI 拆解失败时的兜底骨架",
    }


def deconstruct_post(
    *,
    title: str = "",
    raw_text: str = "",
    platform: str = "",
    url: str = "",
    source_key: str = "",
    tags: Optional[List[str]] = None,
    collect_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    对单条原始帖子做拆解并写入语料库。
    返回 {success, template, factors, provider, error?}
    """
    init_db()
    title = (title or "").strip()
    raw = (raw_text or title).strip()
    if not raw:
        return {"success": False, "error": "缺少原文"}

    body = (
        f"平台：{platform or '未知'}\n"
        f"标题：{title or '(无)'}\n"
        f"正文：{raw[:2500]}\n"
        f"链接：{url or '(无)'}\n"
    )

    factors: Dict[str, Any] = {}
    provider = ""
    try:
        from utils.ai_client import generate_text

        result = generate_text(
            body,
            system_prompt=DECONSTRUCT_SYSTEM,
            temperature=0.35,
            max_tokens=900,
        )
        provider = str(result.get("provider") or "")
        if result.get("success"):
            factors = _extract_json(str(result.get("content") or ""))
        else:
            factors = {}
            provider = provider or "fallback"
    except Exception as e:
        factors = {}
        provider = f"error:{e}"

    if not factors.get("pattern"):
        factors = _fallback_factors(title, raw)
        if not provider:
            provider = "fallback"

    keywords = factors.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [x.strip() for x in re.split(r"[,，、\s]+", keywords) if x.strip()]
    if not isinstance(keywords, list):
        keywords = []

    now = datetime.now().isoformat(timespec="seconds")
    provenance = {
        "steps": [
            {
                "layer": "collect",
                "via": platform or (collect_meta or {}).get("via") or "unknown",
                "url": url,
                "title": title,
                "at": (collect_meta or {}).get("fetched_at") or now,
                **{k: v for k, v in (collect_meta or {}).items() if k not in {"via", "fetched_at"}},
            },
            {
                "layer": "deconstruct",
                "provider": provider,
                "prompt": "corpus.deconstruct.DECONSTRUCT_SYSTEM",
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

    template = create_template(
        source_platform=platform or "unknown",
        source_url=url or "",
        source_key=source_key or url or title or now,
        source_title=title or (raw[:40] + ("…" if len(raw) > 40 else "")),
        raw_text=raw,
        pattern=str(factors.get("pattern") or ""),
        emotion=str(factors.get("emotion") or ""),
        tension=str(factors.get("tension") or ""),
        keywords=[str(x) for x in keywords][:12],
        hooks=str(factors.get("hooks") or ""),
        tags=list(tags or []),
        provenance=provenance,
        factors=factors,
        status="active",
        quality="unrated",
        weight=1.0,
    )
    # 回写 store 步骤的 id
    prov = dict(template.get("provenance") or provenance)
    steps = list(prov.get("steps") or [])
    for step in steps:
        if step.get("layer") == "store":
            step["template_id"] = template.get("id")
    prov["steps"] = steps
    from corpus.db import update_template

    template = update_template(int(template["id"]), {"provenance": prov}) or template

    return {
        "success": True,
        "template": template,
        "factors": factors,
        "provider": provider,
    }


def import_and_deconstruct(posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """批量拆解。posts 项字段：title/raw/content/platform/url/key/tags/fetched_at"""
    ok = 0
    fail = 0
    items: List[Dict[str, Any]] = []
    errors: List[str] = []
    for post in posts:
        try:
            r = deconstruct_post(
                title=str(post.get("title") or ""),
                raw_text=str(post.get("raw") or post.get("content") or post.get("summary") or ""),
                platform=str(post.get("platform") or post.get("platform_id") or ""),
                url=str(post.get("url") or post.get("href") or ""),
                source_key=str(post.get("key") or post.get("source_key") or ""),
                tags=list(post.get("tags") or []) if isinstance(post.get("tags"), list) else [],
                collect_meta={
                    "via": post.get("platform") or post.get("platform_id") or "import",
                    "fetched_at": post.get("fetched_at") or "",
                    "author": post.get("author") or "",
                },
            )
            if r.get("success"):
                ok += 1
                items.append(r.get("template") or {})
            else:
                fail += 1
                errors.append(str(r.get("error") or "失败"))
        except Exception as e:
            fail += 1
            errors.append(str(e))
    return {"success": True, "ok": ok, "fail": fail, "items": items, "errors": errors[:10]}
