# coding=utf-8
"""
编排流程：执行爬虫 → 用千问从当日 txt 提炼话题 → 调用创作模块生成文章。
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from crawler.index import format_date_folder, main as crawl_main, parse_file_titles
from create.index import generate_article_by_topic
from utils.ai_client import get_qwen_client

logger = logging.getLogger(__name__)

MAX_TITLE_BLOB_CHARS = 12000
DEFAULT_MAX_TOPICS = 5


def _safe_filename_part(s: str, max_len: int = 40) -> str:
    s = re.sub(r'[<>:"/\\|?*]', "_", s.strip())
    return (s[:max_len] or "topic").strip() or "topic"


def get_latest_txt_path() -> Optional[Path]:
    """当日 output/日期/txt 下按文件名排序的最后一个 txt（与爬虫写入批次一致）。"""
    date_folder = format_date_folder()
    txt_dir = project_root / "output" / date_folder / "txt"
    if not txt_dir.is_dir():
        return None
    files = sorted(f for f in txt_dir.iterdir() if f.suffix == ".txt")
    return files[-1] if files else None


def build_titles_blob(txt_path: Path, max_chars: int = MAX_TITLE_BLOB_CHARS) -> str:
    titles_by_id, id_to_name = parse_file_titles(txt_path)
    lines: List[str] = []
    for source_id, title_data in titles_by_id.items():
        name = id_to_name.get(source_id, source_id)
        for title in list(title_data.keys())[:80]:
            lines.append(f"[{name}] {title}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...(已截断，仅用于话题提炼)"
    return text


def _parse_topics_json(content: str) -> Dict[str, Any]:
    """从模型输出中解析 JSON（允许包裹在 markdown 代码块中）。"""
    content = content.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if fence:
        content = fence.group(1).strip()
    m = re.search(r"\{[\s\S]*\}", content)
    if not m:
        raise ValueError("模型未返回可解析的 JSON 对象")
    return json.loads(m.group(0))


def extract_topics_via_ai(
    raw_titles: str,
    max_topics: int,
    client: Any,
) -> List[Dict[str, str]]:
    """调用千问从标题列表中提炼可写成文章的话题。"""
    system_prompt = """你是热点编辑。用户会提供一批热搜/新闻标题列表（带平台标签）。
请归纳为若干「可独立写成一篇文章」的话题，每个话题一条。要求：
- 话题具体、互相尽量不重复，可覆盖不同角度；
- 每个话题给出写稿时希望侧重的要点（requirements）；
- 只输出一个 JSON 对象，不要其他说明文字。
格式严格如下（注意是合法 JSON）：
{"topics":[{"title":"话题标题","requirements":"侧重角度与要点，1-3句"}]}"""

    user_prompt = f"""请从下列标题中最多提炼 {max_topics} 个话题：

{raw_titles}
"""
    result = client.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=0.45,
        max_tokens=2048,
    )
    if not result.get("success"):
        raise RuntimeError(result.get("error", "千问提炼话题失败"))

    data = _parse_topics_json(result["content"])
    topics = data.get("topics") or []
    out: List[Dict[str, str]] = []
    for item in topics:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        if not title:
            continue
        req = (item.get("requirements") or item.get("desc") or "").strip()
        out.append({"title": title, "requirements": req})
    return out[:max_topics]


def save_article_md(
    topic_title: str,
    platform: str,
    content_type: str,
    content: str,
) -> Path:
    output_dir = project_root / "output" / "articles"
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_filename_part(topic_title)
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{stem}.md"
    path = output_dir / filename
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {topic_title}\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**平台**: {platform}\n\n")
        f.write(f"**类型**: {content_type}\n\n")
        f.write("---\n\n")
        f.write(content)
    return path


def run_pipeline(
    *,
    skip_crawl: bool = False,
    max_topics: int = DEFAULT_MAX_TOPICS,
    platform: str = "通用",
    content_type: str = "技术文章",
    word_count: int = 2000,
    style: str = "专业",
) -> Dict[str, Any]:
    """
    执行完整编排。

    Returns:
        包含各步骤结果摘要的字典。
    """
    summary: Dict[str, Any] = {
        "crawl": "skipped" if skip_crawl else None,
        "txt_file": None,
        "topics": [],
        "articles": [],
        "errors": [],
    }

    client = get_qwen_client()
    if not client.enable:
        raise RuntimeError("请在 config/config.yaml 中配置 ai.qwen.api_key")

    if not skip_crawl:
        logger.info("开始执行爬虫...")
        crawl_main()
        summary["crawl"] = "done"

    latest = get_latest_txt_path()
    if not latest:
        raise FileNotFoundError(
            f"未找到当日爬取结果：{project_root / 'output' / format_date_folder() / 'txt'}"
        )
    summary["txt_file"] = str(latest)

    blob = build_titles_blob(latest)
    if not blob.strip():
        raise ValueError(f"文件无可用标题: {latest}")

    logger.info("正在用 AI 提炼话题...")
    topics = extract_topics_via_ai(blob, max_topics, client)
    if not topics:
        raise ValueError("AI 未返回任何话题，请检查标题内容或重试")
    summary["topics"] = topics

    for i, t in enumerate(topics, 1):
        title = t["title"]
        req = t.get("requirements", "")
        logger.info("正在创作 [%s/%s]: %s", i, len(topics), title)
        result = generate_article_by_topic(
            topic=title,
            requirements=req,
            platform=platform,
            content_type=content_type,
            word_count=word_count,
            style=style,
        )
        if result.get("success"):
            path = save_article_md(title, platform, content_type, result["content"])
            summary["articles"].append({"topic": title, "path": str(path)})
        else:
            err = result.get("error", "未知错误")
            summary["errors"].append({"topic": title, "error": err})
            logger.error("创作失败: %s — %s", title, err)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="TrendRadar：爬取 → AI 提炼话题 → 创作文章"
    )
    parser.add_argument(
        "--skip-crawl",
        action="store_true",
        help="跳过爬虫，仅使用当日 output 目录下已有最新 txt",
    )
    parser.add_argument(
        "--max-topics",
        type=int,
        default=DEFAULT_MAX_TOPICS,
        help=f"最多提炼并创作的话题数（默认 {DEFAULT_MAX_TOPICS}）",
    )
    parser.add_argument("--platform", type=str, default="通用", help="目标平台")
    parser.add_argument("--type", type=str, default="技术文章", help="内容类型")
    parser.add_argument("--words", type=int, default=2000, help="目标字数")
    parser.add_argument("--style", type=str, default="专业", help="文章风格")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("=" * 60)
    print("TrendRadar：爬取 → AI 提炼话题 → 创作")
    print("=" * 60)

    try:
        summary = run_pipeline(
            skip_crawl=args.skip_crawl,
            max_topics=args.max_topics,
            platform=args.platform,
            content_type=args.type,
            word_count=args.words,
            style=args.style,
        )
    except Exception as e:
        print(f"\n❌ 流程失败: {e}")
        raise SystemExit(1) from e

    print(f"\n📂 使用的爬取文件: {summary['txt_file']}")
    print(f"\n📌 提炼的话题 ({len(summary['topics'])} 个):")
    for t in summary["topics"]:
        print(f"  • {t['title']}")
    print(f"\n✅ 已生成文章 ({len(summary['articles'])} 篇):")
    for a in summary["articles"]:
        print(f"  • {a['topic']}\n    → {a['path']}")
    if summary["errors"]:
        print(f"\n⚠️ 部分失败 ({len(summary['errors'])}):")
        for e in summary["errors"]:
            print(f"  • {e['topic']}: {e['error']}")
    print()


if __name__ == "__main__":
    main()
