# coding=utf-8
"""
资讯关键词衍生：本地 AI（优先 Ollama）生成种子词 + Twitter 友好搜索语法。
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional


SYSTEM_PROMPT = """你是社交媒体搜索顾问。根据用户主题，输出便于在 X(Twitter)/Reddit/Telegram 检索的衍生词与查询。
只输出 JSON，不要 markdown 代码块，不要解释。
JSON 结构：
{
  "seeds": ["短词或短语，以中文为主，可少量英文专有名词，6~12个"],
  "twitter_queries": ["3~6条 X 高级搜索语法，可用引号、OR、min_faves、-filter:replies、-filter:retweets、lang:zh 等"],
  "reddit_queries": ["2~5个适合 Reddit search 的中文或中英混合短语"],
  "telegram_queries": ["2~5个适合 Telegram 全文搜索的中文短语"],
  "questions": ["2~4个用户常搜的中文问题句，可选"]
}
twitter_queries 要求：每条可直接粘贴到 X 搜索框；优先中文内容；必须带 lang:zh；不要太长。
"""


def _prefer_chinese_queries() -> bool:
    env = os.environ.get("ONLY_CHINESE", "").strip().lower()
    if env:
        return env in ("1", "true", "yes")
    try:
        from pathlib import Path
        import yaml

        cfg = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
        with open(cfg, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return bool((data.get("crawler") or {}).get("only_chinese", False))
    except Exception:
        return False


def _ensure_lang_zh(query: str) -> str:
    q = (query or "").strip()
    if not q:
        return q
    if re.search(r"\blang:\w+", q, re.I):
        return re.sub(r"\blang:\w+", "lang:zh", q, flags=re.I)
    return f"{q} lang:zh"


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*", s)
    if not m:
        return None
    chunk = m.group(0)
    # 尝试直接解析；失败则修补被截断的 JSON
    for candidate in (chunk, _repair_truncated_json(chunk)):
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def _repair_truncated_json(text: str) -> Optional[str]:
    """尽量闭合被 max_tokens 截断的 JSON 对象。"""
    s = (text or "").strip()
    if not s.startswith("{"):
        return None
    # 丢掉最后一个不完整的字符串值
    if s.count('"') % 2 == 1:
        s = s.rsplit('"', 1)[0]
    s = re.sub(r",\s*$", "", s)
    # 补齐括号
    opens = s.count("{") - s.count("}")
    opens_b = s.count("[") - s.count("]")
    s += "]" * max(0, opens_b)
    s += "}" * max(0, opens)
    return s


def _heuristic_expand(keyword: str) -> Dict[str, Any]:
    """无 AI 时的兜底衍生。"""
    kw = (keyword or "").strip()
    seeds = [kw]
    lower = kw.lower()
    mapping = {
        "远程工作": ["remote work", "work from home", "digital nomad", "WFH", "remote job"],
        "remote work": ["work from home", "digital nomad", "WFH", "remote job", "远程工作"],
        "数字游民": ["digital nomad", "remote work", "nomad life", "远程工作"],
    }
    for k, extras in mapping.items():
        if k in kw or k in lower:
            seeds.extend(extras)
            break
    else:
        if any("\u4e00" <= c <= "\u9fff" for c in kw):
            seeds.append(f"{kw} 招聘")
            seeds.append(f"{kw} 机会")
        else:
            seeds.extend([f"{kw} job", f"{kw} hiring", f'"{kw}"'])

    seen = set()
    uniq: List[str] = []
    for s in seeds:
        s = str(s).strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            uniq.append(s)

    en = next((s for s in uniq if re.search(r"[A-Za-z]", s)), kw)
    alt = next((s for s in uniq if re.search(r"[A-Za-z]", s) and s.lower() != en.lower()), "remote job")
    zh_only = _prefer_chinese_queries()
    if zh_only:
        twitter = [
            f'("{kw}" OR "{en}") (min_faves:20 OR min_retweets:5) -filter:replies lang:zh',
            f'"{kw}" (招聘 OR 机会 OR 远程) -filter:replies lang:zh',
            f'"{kw}" -filter:retweets -filter:replies lang:zh',
        ]
    else:
        twitter = [
            f'("{en}" OR "{alt}") (min_faves:20 OR min_retweets:5) -filter:replies',
            f'"{en}" (hiring OR job OR opportunity) -filter:replies lang:en',
            f'"{en}" -filter:retweets -filter:replies',
        ]
    return {
        "seeds": uniq[:10],
        "twitter_queries": twitter[:4],
        "reddit_queries": uniq[:4],
        "telegram_queries": uniq[:4],
        "questions": [f"如何找到{kw}机会？", f"What are tips for {en}?"],
        "provider": "heuristic",
        "keyword": kw,
    }


def _normalize_list(val: Any, limit: int = 12) -> List[str]:
    if isinstance(val, str):
        items = [x.strip() for x in re.split(r"[,，;；|\n]+", val) if x.strip()]
    elif isinstance(val, list):
        items = [str(x).strip() for x in val if str(x).strip()]
    else:
        items = []
    out: List[str] = []
    seen = set()
    for it in items:
        key = it.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
        if len(out) >= limit:
            break
    return out


def expand_keyword(keyword: str, max_twitter: int = 5) -> Dict[str, Any]:
    """
    对主题做衍生，返回 seeds / twitter_queries / reddit_queries / telegram_queries。
    """
    kw = (keyword or "").strip()
    if not kw:
        return {
            "success": False,
            "error": "关键词为空",
            "seeds": [],
            "twitter_queries": [],
            "reddit_queries": [],
            "telegram_queries": [],
        }

    from utils.ai_client import generate_text

    prompt = (
        f"主题：{kw}\n"
        f"请生成便于检索的衍生词与查询；twitter_queries 最多 {max_twitter} 条。"
    )
    result = generate_text(prompt, system_prompt=SYSTEM_PROMPT, temperature=0.3, max_tokens=1800)
    parsed = _extract_json(result.get("content") or "") if result.get("success") else None

    # 再试一次更短、更硬的输出约束
    if not parsed and result.get("success"):
        retry = generate_text(
            f"主题：{kw}\n只输出一个完整 JSON 对象，字段 seeds/twitter_queries/reddit_queries/telegram_queries，数组宜短。",
            system_prompt="只输出合法 JSON，不要 markdown。",
            temperature=0.1,
            max_tokens=1000,
        )
        if retry.get("success"):
            parsed = _extract_json(retry.get("content") or "")
            if parsed:
                result = retry

    if not parsed:
        data = _heuristic_expand(kw)
        data["success"] = True
        data["ai_error"] = result.get("error") or "模型输出无法解析，已用规则衍生"
        return data

    data = {
        "success": True,
        "keyword": kw,
        "seeds": _normalize_list(parsed.get("seeds"), 12),
        "twitter_queries": _normalize_list(parsed.get("twitter_queries"), max_twitter),
        "reddit_queries": _normalize_list(parsed.get("reddit_queries"), 6),
        "telegram_queries": _normalize_list(parsed.get("telegram_queries"), 6),
        "questions": _normalize_list(parsed.get("questions"), 6),
        "provider": result.get("provider") or "ai",
        "model": result.get("model") or "",
    }
    if not data["seeds"]:
        data["seeds"] = [kw]
    if not data["twitter_queries"]:
        fallback = _heuristic_expand(kw)
        data["twitter_queries"] = fallback["twitter_queries"]
    if not data["reddit_queries"]:
        data["reddit_queries"] = data["seeds"][:4]
    if not data["telegram_queries"]:
        data["telegram_queries"] = data["seeds"][:4]
    if _prefer_chinese_queries():
        data["twitter_queries"] = [_ensure_lang_zh(q) for q in data["twitter_queries"]]
    return data
