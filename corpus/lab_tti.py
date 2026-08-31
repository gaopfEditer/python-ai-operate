# coding=utf-8
"""灵感碰撞变体配图：桥接 auto-deal-eth browser_media_runner.tti。"""

from __future__ import annotations

import os
import re
import sys
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAB_MEDIA_ROOT = PROJECT_ROOT / "output" / "lab_media"
AUTO_DEAL_ETH_ROOT = Path(os.environ.get("AUTO_DEAL_ETH_ROOT", PROJECT_ROOT.parent / "auto-deal-eth"))


def _ensure_tti() -> None:
    root = str(AUTO_DEAL_ETH_ROOT.resolve())
    if not AUTO_DEAL_ETH_ROOT.is_dir():
        raise FileNotFoundError(f"未找到 auto-deal-eth：{AUTO_DEAL_ETH_ROOT}")
    if root not in sys.path:
        sys.path.insert(0, root)


def _apply_debugger_url(debugger_url: str) -> None:
    raw = str(debugger_url or "").strip()
    if not raw:
        return
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    if ":" in raw:
        port = raw.rsplit(":", 1)[-1]
    else:
        port = raw
    if port.isdigit():
        os.environ["CHROME_DEBUG_PORT"] = port
        os.environ["USE_REMOTE_DEBUGGING"] = "True"


def resolve_lab_media(rel: str) -> Path:
    rel = str(rel or "").strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError("非法路径")
    root = LAB_MEDIA_ROOT.resolve()
    fpath = (LAB_MEDIA_ROOT / rel).resolve()
    if fpath != root and root not in fpath.parents:
        raise ValueError("非法路径")
    return fpath


def build_image_prompt(*, topic: str, hook: str, content: str, label: str = "") -> str:
    topic = (topic or "").strip()
    hook = (hook or "").strip()
    body = (content or "").strip()
    if len(body) > 320:
        body = body[:320] + "…"
    label = (label or "").strip()
    parts = [
        "请为一条加密货币社区短帖生成一张配图横幅。",
        "要求：深色背景、轻微网格或行情氛围、视觉元素呼应帖子主题；",
        "不要出现真实人脸、不要水印、不要大段文字；16:9 构图，适合 X/Twitter 配图。",
    ]
    if topic:
        parts.append(f"热点主题：{topic}")
    if label:
        parts.append(f"变体风格：{label}")
    if hook:
        parts.append(f"开头 Hook：{hook}")
    if body:
        parts.append(f"正文要点：{body}")
    return "\n".join(parts)


_MEMOS_BRIEF_SYSTEM = """你是短内容视觉策划编辑。阅读文章后，只输出 JSON（不要 Markdown）：
{
  "elements": ["要素1", "要素2", "要素3"],
  "punchline": "一句点睛之笔",
  "visual": "具体画面意象"
}
规则：
1. elements：3～6 条，必须是原文里的事实/结论/关键数字/对立点，短词或短语，适合直接印在图上；禁止空话套话。
2. punchline：一句中文 ≤28 字，三选一写法——把要素串成一句 / 点出最重要要义 / 制造吸睛反差；禁止「未来已来」「抓住机会」这类空泛口号。
3. visual：一句具体可见的物体/场景/符号（如「断裂的上涨箭头」「两扇门一明一暗」），禁止空洞形容词堆砌。
"""


def _strip_md_noise(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    # 去掉已有配图 markdown，减轻干扰
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > 2400:
        text = text[:2400] + "…"
    return text


def _fallback_memos_brief(content: str, hook: str = "") -> Dict[str, Any]:
    """AI 不可用时的本地兜底：用标题行 + 短句当上图要素。"""
    text = _strip_md_noise(content)
    lines = [ln.strip(" #-*>") for ln in text.splitlines() if ln.strip()]
    elems: List[str] = []
    for ln in lines:
        s = re.sub(r"^[\d]+[\.\)、]\s*", "", ln).strip()
        if len(s) < 2:
            continue
        if s.startswith("http"):
            continue
        elems.append(s[:28])
        if len(elems) >= 4:
            break
    hook = (hook or "").strip() or (elems[0] if elems else "要点速览")
    punch = hook[:28]
    if len(elems) >= 2:
        punch = f"{elems[0]} → {elems[1]}"[:28]
    return {
        "elements": elems[:5] or [punch],
        "punchline": punch,
        "visual": "深色资讯卡片，关键数字高亮",
        "provider": "fallback",
    }


def compose_memos_image_brief(
    content: str,
    *,
    hook: str = "",
    title: str = "",
) -> Dict[str, Any]:
    """先提炼上图要素 + 点睛句，供生图提示词使用。"""
    body = _strip_md_noise(content)
    if not body:
        return _fallback_memos_brief(content, hook=hook)

    user = (
        f"标题/开头：{(title or hook or '').strip() or '（无）'}\n"
        f"正文：\n{body}\n\n"
        "请严格输出 JSON。"
    )
    try:
        from utils.ai_client import generate_text

        result = generate_text(
            user,
            system_prompt=_MEMOS_BRIEF_SYSTEM,
            temperature=0.4,
            max_tokens=800,
        )
        if not result.get("success"):
            brief = _fallback_memos_brief(content, hook=hook)
            brief["ai_error"] = str(result.get("error") or "摘要失败")
            return brief
        text = str(result.get("content") or "")
        m = re.search(r"\{[\s\S]*\}", text)
        payload = json.loads(m.group(0)) if m else {}
        elems = payload.get("elements") if isinstance(payload.get("elements"), list) else []
        elems = [str(x).strip() for x in elems if str(x).strip()][:6]
        punch = str(payload.get("punchline") or "").strip()[:40]
        visual = str(payload.get("visual") or "").strip()[:80]
        if not elems or not punch:
            brief = _fallback_memos_brief(content, hook=hook)
            brief["provider"] = str(result.get("provider") or "")
            return brief
        return {
            "elements": elems,
            "punchline": punch,
            "visual": visual or "深色资讯横幅，文字高对比",
            "provider": str(result.get("provider") or ""),
        }
    except Exception as e:
        brief = _fallback_memos_brief(content, hook=hook)
        brief["ai_error"] = str(e)
        return brief


def build_memos_image_prompt(brief: Dict[str, Any], *, title: str = "") -> str:
    """用摘要要素 + 点睛句拼出具体生图提示词（避免空泛描述）。"""
    elems = [str(x).strip() for x in (brief.get("elements") or []) if str(x).strip()]
    punch = str(brief.get("punchline") or "").strip()
    visual = str(brief.get("visual") or "").strip()
    title = (title or "").strip()

    lines = [
        "请直接生成一张 16:9 社交媒体配图横幅。",
        "画面上必须用清晰、高对比的中文大字标出下列内容（不要英文堆砌、不要水印、不要真人脸）：",
    ]
    if punch:
        lines.append(f"主标题（最大字）：「{punch}」")
    if elems:
        lines.append("次级要点（小字或标签，逐条出现在图上）：")
        for i, e in enumerate(elems[:6], 1):
            lines.append(f"  {i}. {e}")
    if visual:
        lines.append(f"画面意象：{visual}")
    if title and title not in punch:
        lines.append(f"文章语境：{title[:60]}")
    lines.append(
        "风格：深色背景、资讯/行情氛围、文字可读优先；禁止空泛口号"
        "（如「未来已来」「抓住红利」）；不要大段正文粘贴。"
    )
    return "\n".join(lines)


def _image_entry(src: Path, batch_id: str) -> Dict[str, str]:
    rel = f"{batch_id}/{src.name}"
    return {
        "path": str(src),
        "rel": rel,
        "url": f"/api/corpus/lab/media?rel={rel}",
        "name": src.name,
    }


def generate_variant_image(
    *,
    topic: str,
    hook: str,
    content: str,
    label: str = "",
    variant_id: str = "v",
    batch_id: Optional[str] = None,
    debugger_url: str = "",
    keep_browser_open: bool = True,
    use_content_brief: bool = False,
) -> Dict[str, Any]:
    _ensure_tti()
    _apply_debugger_url(debugger_url)
    from browser_media_runner import text_to_image

    brief: Optional[Dict[str, Any]] = None
    if use_content_brief or (topic or "").strip().lower() == "memos":
        brief = compose_memos_image_brief(content, hook=hook, title=label or hook)
        prompt = build_memos_image_prompt(brief, title=label or hook)
    else:
        prompt = build_image_prompt(topic=topic, hook=hook, content=content, label=label)

    batch_id = batch_id or datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    batch_dir = LAB_MEDIA_ROOT / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    tag = "".join(c if c.isalnum() else "_" for c in (variant_id or "v"))[:24] or "lab"

    result = text_to_image(
        prompt,
        prompt_is_text=True,
        domain_tag=tag,
        out_dir=str(batch_dir),
        keep_browser_open=keep_browser_open,
    )
    web = result.get("web_result") if isinstance(result.get("web_result"), dict) else {}
    images_raw = list(result.get("images") or [])
    if not images_raw and web:
        images_raw = list(web.get("images") or [])

    images: List[Dict[str, str]] = []
    for p in images_raw:
        src = Path(p)
        if not src.is_file():
            continue
        name = src.name.lower()
        # 排除调试/兜底图（含历史 trendradar_test.png、整页截图）
        if "trendradar_test" in name or name.endswith("_page.png"):
            continue
        if src.stat().st_size < 800:
            continue
        images.append(_image_entry(src, batch_id))

    # web 明确失败时，即使有兜底文件也不算成功
    if web and web.get("ok") is False and not images:
        err = str(web.get("error") or result.get("error") or "文生图未返回图片")
        return {
            "success": False,
            "error": err,
            "prompt": prompt,
            "brief": brief,
            "batch_id": batch_id,
        }

    if not images:
        err = ""
        if web:
            err = str(web.get("error") or "")
        if not err:
            err = str(result.get("error") or "文生图未返回图片")
        return {
            "success": False,
            "error": err,
            "prompt": prompt,
            "brief": brief,
            "batch_id": batch_id,
        }

    # 配图只需一张：取第一张可用图
    images = images[:1]
    return {
        "success": True,
        "images": images,
        "prompt": prompt,
        "brief": brief,
        "batch_id": batch_id,
    }


def append_images_to_content(content: str, images: Sequence[Dict[str, str]]) -> str:
    base = (content or "").rstrip()
    if not images:
        return base
    lines: List[str] = []
    for im in images:
        url = str(im.get("url") or "")
        if url and url not in base:
            lines.append(f"![配图]({url})")
    if not lines:
        return base
    return base + "\n\n" + "\n".join(lines)


def batch_generate_images(
    variants: Sequence[Dict[str, Any]],
    indices: Sequence[int],
    *,
    topic: str = "",
    debugger_url: str = "",
    progress_cb: Optional[Callable[[int, int, int, str], None]] = None,
    use_content_brief: Optional[bool] = None,
) -> Dict[str, Any]:
    picked = [int(i) for i in indices]
    results: List[Dict[str, Any]] = []
    ok_n = 0
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    keep_browser_open = True
    if use_content_brief is None:
        use_content_brief = (topic or "").strip().lower() == "memos"

    for n, idx in enumerate(picked):
        if idx < 0 or idx >= len(variants):
            results.append({"index": idx, "success": False, "error": "变体索引无效"})
            continue
        v = variants[idx]
        label = str(v.get("label") or v.get("id") or idx)
        if progress_cb:
            progress_cb(n + 1, len(picked), idx, f"摘要·{label}" if use_content_brief else label)
        try:
            gen = generate_variant_image(
                topic=topic,
                hook=str(v.get("hook") or ""),
                content=str(v.get("content") or ""),
                label=str(v.get("label") or ""),
                variant_id=str(v.get("id") or f"v{idx}"),
                batch_id=batch_id,
                debugger_url=debugger_url,
                keep_browser_open=keep_browser_open,
                use_content_brief=bool(use_content_brief),
            )
            keep_browser_open = True
        except Exception as e:
            gen = {"success": False, "error": str(e)}

        if gen.get("success"):
            ok_n += 1
            imgs = gen.get("images") or []
            new_content = append_images_to_content(str(v.get("content") or ""), imgs)
            results.append(
                {
                    "index": idx,
                    "success": True,
                    "images": imgs,
                    "content": new_content,
                    "media_paths": [im["path"] for im in imgs],
                    "prompt": gen.get("prompt"),
                    "brief": gen.get("brief"),
                }
            )
        else:
            results.append(
                {
                    "index": idx,
                    "success": False,
                    "error": gen.get("error") or "生成失败",
                    "prompt": gen.get("prompt"),
                    "brief": gen.get("brief"),
                }
            )

    failures = [r for r in results if not r.get("success")]
    return {
        "success": ok_n > 0,
        "ok_count": ok_n,
        "fail_count": len(failures),
        "total": len(picked),
        "batch_id": batch_id,
        "results": results,
        "failures": failures,
    }
