"""
实时发送 CLI（python realtime_send.py）
从 news_mornitor (:8770) 获取事件列表 → 交互选择 → 调用 CDP 发布到指定平台。

默认平台来源：
  1. 优先读取 config/config.yaml 的 publish.default_platforms（逗号分隔）
  2. 退而读取 public/platforms/ 下已启用平台
  3. 均无 → 强制询问

用法（Windows PowerShell 推荐加 -X utf8 显示中文）：
  python -X utf8 realtime_send.py                           # 交互
  python -X utf8 realtime_send.py --list                   # 只列事件
  python -X utf8 realtime_send.py --list --channel twitter  # 按频道筛选
  python -X utf8 realtime_send.py --send 3 --platform okx   # 发送第 3 条到 okx
  python -X utf8 realtime_send.py --send 3 --platform okx,binance_square  # 多平台
  python -X utf8 realtime_send.py --cdp 127.0.0.1:9223     # 指定 CDP
  python -X utf8 realtime_send.py --dry-run                 # 不点发布（CDP 填完后退）
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 项目路径 ──────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("realtime_send")


# ── 常量 ───────────────────────────────────────────────────────────────────
NM_BASE = os.environ.get("NM_HOST", "http://127.0.0.1:8770")
DEFAULT_CDP = os.environ.get("CDP_URL", "127.0.0.1:9223")
SUPPORTED_PLATFORMS = ("binance_square", "okx", "x_cdp", "x")
PLATFORM_LABELS = {
    "binance_square": "币安广场",
    "okx": "OKX星球",
    "x_cdp": "X (Twitter)",
    "x": "X (Twitter)",
}
# 前端 realtime/publish-one 用的 x_cdp，这里也统一用 x_cdp
PLATFORM_ALIAS = {"x": "x_cdp"}


# ── 1. 从 news_mornitor 获取事件 ───────────────────────────────────────────

def fetch_events(
    channel: str = "all",
    min_star: int = 1,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """GET /api/v1/events（由 console/app.py 转发），失败则尝试 /api/batch/last。"""
    import requests

    # 先试 v1/events（console 转发 upstream）
    try:
        r = requests.get(
            f"{NM_BASE}/api/v1/events",
            params={"channel": channel, "min_star": min_star, "limit": limit},
            timeout=12,
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("items") or data.get("events") or []
        logger.warning("v1/events 返回 %s，尝试 batch/last", r.status_code)
    except requests.exceptions.ConnectionError:
        logger.warning("无法连接 %s/api/v1/events，尝试 batch/last", NM_BASE)
    except Exception as e:
        logger.warning("v1/events 异常 %s，尝试 batch/last", e)

    # 退而用 batch/last
    try:
        r = requests.get(
            f"{NM_BASE}/api/batch/last",
            params={"limit": limit, "candidates_only": "0"},
            timeout=12,
        )
        if r.status_code == 200:
            data = r.json()
            items = data.get("items") or []
            if channel != "all":
                items = [x for x in items if str(x.get("platform") or "") == channel]
            logger.info("从 batch/last 获取 %d 条", len(items))
            return items
    except Exception as e:
        logger.error("batch/last 也失败: %s", e)

    return []


def format_event(idx: int, item: Dict[str, Any]) -> str:
    title = (item.get("title") or item.get("content") or "")[:50]
    star = item.get("star", 0) or 0
    platform = item.get("platform") or item.get("source") or "-"
    bias = item.get("bias") or item.get("bias_label") or "-"
    desc = (item.get("description") or item.get("desc") or "")[:60].replace("\n", " ")
    stars = "*" * int(star) if star else "-"
    return (
        f"  [{idx:2d}] {stars} {platform:<12} [{bias}] {title}\n"
        f"       {desc}"
    )


def list_events_table(items: List[Dict[str, Any]]) -> None:
    if not items:
        print("\n  暂无事件，请先在 news_mornitor 中抓取。\n")
        return
    print(f"\n  共 {len(items)} 条事件：\n")
    for i, item in enumerate(items, 1):
        print(format_event(i, item))
        print()


# ── 2. 平台选择 ──────────────────────────────────────────────────────────

def load_default_platforms_from_config() -> List[str]:
    """读 config/config.yaml → publish.default_platforms（逗号分隔）。"""
    cfg_path = _ROOT / "config" / "config.yaml"
    if not cfg_path.exists():
        return []
    import yaml

    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        raw = cfg.get("publish", {}).get("default_platforms", "")
        return [p.strip() for p in str(raw).split(",") if p.strip()]
    except Exception as e:
        logger.warning("读取 config 失败: %s", e)
        return []


def list_available_platforms() -> List[Dict[str, str]]:
    """读 config/config.yaml → publish.platforms（过滤已启用）。"""
    cfg_path = _ROOT / "config" / "config.yaml"
    if not cfg_path.exists():
        return []
    import yaml

    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return [
            {"id": p.get("id", ""), "name": p.get("name", p.get("id", ""))}
            for p in cfg.get("publish", {}).get("platforms", [])
            if p.get("enabled", True)
        ]
    except Exception as e:
        logger.warning("读取 platforms 配置失败: %s", e)
        return []


def ask_platforms(defaults: List[str]) -> List[str]:
    """交互询问平台，返回选中的 platform id 列表。"""
    all_ids = list(PLATFORM_LABELS.keys())
    print("\n  支持的平台：")
    for pid in all_ids:
        label = PLATFORM_LABELS.get(pid, pid)
        default_tag = " (默认)" if pid in defaults else ""
        print(f"    {pid:<20} {label}{default_tag}")
    print()

    if defaults:
        default_str = ",".join(defaults)
        ans = input(f"  选择平台（直接回车使用默认 [{default_str}]）: ").strip()
        if not ans:
            return defaults
    else:
        ans = input("  选择平台（逗号分隔，如 okx,binance_square）: ").strip()

    if not ans:
        print("  未选择平台，退出。")
        sys.exit(0)

    selected = []
    for token in ans.replace("，", ",").split(","):
        pid = token.strip()
        pid = PLATFORM_ALIAS.get(pid, pid)
        if pid in all_ids:
            selected.append(pid)
        else:
            logger.warning("忽略未知平台: %s", pid)
    return selected


# ── 3. CDP 发布 ───────────────────────────────────────────────────────────

def resolve_cdp(url: str) -> str:
    if url:
        return url.rstrip("/")
    # 尝试环境变量
    return os.environ.get("CDP_URL", DEFAULT_CDP).rstrip("/")


def _do_publish(
    platform: str,
    text: str,
    image_path: Optional[str],
    debugger_url: str,
    dry_run: bool,
) -> Dict[str, Any]:
    """对单个平台执行 publish。"""
    from public.platforms.binance_square_publisher import BinanceSquarePublisher
    from public.platforms.okx_publisher import OkxPublisher
    from public.platforms.x_publisher import XPublisher

    media = [str(image_path)] if image_path and Path(image_path).is_file() else []

    pid = platform  # 已经是 normalized 的
    label = PLATFORM_LABELS.get(pid, pid)
    logger.info("  → 发布到 %s (%s) ...", label, pid)

    if pid == "binance_square":
        pub = BinanceSquarePublisher(
            square_url="https://www.binance.com/zh-CN/square",
            platform_id="binance_square",
            platform_name="币安广场",
            debugger_url=debugger_url,
            close_driver=False,
        )
        return pub.publish(text=text, media_paths=media, submit=not dry_run)

    if pid == "okx":
        pub = OkxPublisher(
            square_url="https://www.okx.com/cn/orbit",
            platform_id="okx",
            platform_name="OKX星球",
            debugger_url=debugger_url,
            close_driver=False,
        )
        return pub.publish(text=text, media_paths=media, submit=not dry_run)

    if pid in ("x_cdp", "x"):
        pub = XPublisher(
            platform_id="x_cdp",
            platform_name="X",
            debugger_url=debugger_url,
            close_driver=False,
        )
        return pub.publish(text=text, media_paths=media, submit=not dry_run)

    return {"success": False, "error": f"未知平台: {pid}"}


def publish_event(
    item: Dict[str, Any],
    text: str,
    platforms: List[str],
    debugger_url: str,
    dry_run: bool,
) -> Dict[str, Any]:
    """对一条事件发布到多个平台（串行）。"""
    image_path: Optional[str] = None
    # 支持 item.image / item.media 等常见字段
    for key in ("image", "image_path", "media_path", "media"):
        ip = item.get(key)
        if ip and Path(str(ip)).is_file():
            image_path = str(ip)
            break

    results = {}
    for plat in platforms:
        result = _do_publish(plat, text, image_path, debugger_url, dry_run)
        results[plat] = result
        label = PLATFORM_LABELS.get(plat, plat)
        if result.get("success"):
            logger.info("    [OK] %s", label)
            if result.get("url"):
                logger.info("      %s", result["url"])
        else:
            logger.error("    [FAIL] %s: %s", label, result.get("error") or "unknown")
        # 平台之间稍作间隔
        if len(platforms) > 1:
            time.sleep(5)

    return results


# ── 4. AI 摘要（复用 console/app.py 的 prompt） ───────────────────────────

def generate_summary(item: Dict[str, Any]) -> str:
    """调用 AI 摘要，和 console/app.py 保持一致。"""
    title = str(item.get("title") or "")
    description = str(item.get("description") or item.get("desc") or "")
    category = str(item.get("category_name") or item.get("category") or "")
    bias = str(item.get("bias") or item.get("bias_label") or "")
    star = int(item.get("star") or 0)
    source = str(item.get("source") or item.get("platform") or "")

    if not description:
        return title  # 退而用标题

    prompt = f"""你是一个加密货币内容编辑。请根据以下事件的标题和内容，撰写一条面向币圈人士的社交平台短文（约300字）：

标题：{title}
事件：{description}
类目：{category}
偏向：{bias}
星级：{"重要" if star >= 4 else "一般"}
来源：{source}

要求：
  - 开头结合标题制造吸引力（疑问句或数据开场），不重复标题原话
  - 围绕"这对币圈/相关赛道/相关币种有什么影响"展开分析
  - 明确指出利多还是利空，以及影响程度
  - 简洁专业，有观点有判断，不只是描述事件
  - 可加1-2个相关话题标签
  - 中文输出"""

    try:
        from utils.ai_client import generate_text

        result = generate_text(prompt, max_tokens=400, temperature=0.7)
        if result and result.get("success"):
            return result.get("content", "").strip()
    except Exception as e:
        logger.warning("AI 摘要失败: %s，退而使用描述", e)

    # 回退：截取 description
    return description[:300]


# ── 5. 主入口 ──────────────────────────────────────────────────────────────

def _pick(items: List[Dict[str, Any]], idx_str: str) -> Optional[tuple[int, Dict[str, Any]]]:
    """把用户输入解析成 (index, item) 或 None。"""
    try:
        n = int(idx_str.strip())
    except ValueError:
        return None
    if 1 <= n <= len(items):
        return n - 1, items[n - 1]
    return None


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="实时发送 CLI：获取事件 → 摘要 → CDP 发布",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--list", dest="list_only", action="store_true",
                      help="只列出事件，不发送")
    group.add_argument("--send", dest="send_idx", metavar="N", type=int,
                      help="直接发送第 N 条（交互前自动列出）")
    parser.add_argument("--channel", default="all",
                      help="news_mornitor 频道过滤（默认 all）")
    parser.add_argument("--min-star", dest="min_star", type=int, default=1,
                      help="最低星级（默认 1）")
    parser.add_argument("--limit", type=int, default=30,
                      help="最多取事件数（默认 30）")
    parser.add_argument("--platform", dest="platform", default="",
                      help="指定平台，逗号分隔（如 okx,binance_square）；省略则交互选择")
    parser.add_argument("--cdp", dest="cdp", default=DEFAULT_CDP,
                      help=f"CDP 地址（默认 {DEFAULT_CDP}）")
    parser.add_argument("--text", dest="text", default="",
                      help="直接指定发布文本（省略则 AI 摘要）")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                      help="CDP 填完内容后不点发布")
    parser.add_argument("--wait", dest="wait", type=float, default=0,
                      help="发布前等待 N 秒（可接管道输入延迟）")
    args = parser.parse_args()

    if args.wait > 0:
        logger.info("等待 %.0f 秒后开始...", args.wait)
        time.sleep(args.wait)

    # ── 1. 获取事件列表 ────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  实时发送 CLI")
    print(f"{'='*60}")
    print(f"\n  从 {NM_BASE} 获取事件（频道={args.channel}，星级≥{args.min_star}）...")

    items = fetch_events(channel=args.channel, min_star=args.min_star, limit=args.limit)

    if not items:
        print("\n  [!] No events fetched.")
        print("  Check:")
        print("    1. news_mornitor is running: python -m allnews_mornitor")
        print("    2. a crawl has been executed")
        print("    3. or try --channel twitter")
        print("  NOTE: On Windows, run with '-X utf8' for proper Chinese display:")
        print(f"       python -X utf8 realtime_send.py --list\n")
        sys.exit(1)

    list_events_table(items)

    if args.list_only:
        return

    # ── 2. 选择事件 ────────────────────────────────────────────────────
    if args.send_idx:
        picked = _pick(items, str(args.send_idx))
        if not picked:
            print(f"\n  序号 {args.send_idx} 超出范围（1–{len(items)}），退出。\n")
            sys.exit(1)
        _, chosen = picked
    else:
        print(f"  选择要发送的事件（1–{len(items)}），直接回车退出：", end=" ")
        ans = sys.stdin.readline().strip()
        if not ans:
            print("\n  退出。\n")
            return
        picked = _pick(items, ans)
        if not picked:
            print(f"\n  输入无效，退出。\n")
            sys.exit(1)
        _, chosen = picked

    title = chosen.get("title") or chosen.get("content") or ""
    print(f"\n  已选：{title[:60]}\n")

    # ── 3. 确定平台 ────────────────────────────────────────────────────
    if args.platform:
        raw_platforms = [p.strip() for p in args.platform.replace("，", ",").split(",")]
        platforms = [PLATFORM_ALIAS.get(p, p) for p in raw_platforms]
        platforms = [p for p in platforms if p in SUPPORTED_PLATFORMS]
    else:
        defaults = load_default_platforms_from_config()
        if not defaults:
            # 尝试从 config/platforms 取已启用
            for p in list_available_platforms():
                pid = p["id"]
                pid = PLATFORM_ALIAS.get(pid, pid)
                if pid in SUPPORTED_PLATFORMS and pid not in defaults:
                    defaults.append(pid)
        platforms = ask_platforms(defaults)

    if not platforms:
        print("\n  未选择平台，退出。\n")
        sys.exit(1)

    print(f"\n  目标平台：{', '.join(PLATFORM_LABELS.get(p, p) for p in platforms)}")

    # ── 4. 确定文本 ───────────────────────────────────────────────────
    if args.text:
        text = args.text
    else:
        print("\n  正在生成摘要（AI）...")
        text = generate_summary(chosen)
        print(f"\n  摘要预览：\n{'  ' + '-'*50}")
        print("  " + text[:200].replace("\n", "\n  "))
        if len(text) > 200:
            print("  ...")
        print("  " + "-" * 50)

        # 检查是否有配图
        image_path: Optional[str] = None
        for key in ("image", "image_path", "media_path", "media"):
            ip = chosen.get(key)
            if ip and Path(str(ip)).is_file():
                image_path = str(ip)
                print(f"\n  附带图片：{image_path}")
                break

        ans = input("\n  确认发布？直接回车确认，输入新文本替换： ").strip()
        if ans:
            text = ans

    # ── 5. 发布 ───────────────────────────────────────────────────────
    cdp = resolve_cdp(args.cdp)
    print(f"\n  CDP: {cdp}")
    print(f"  Dry-run: {args.dry_run}")
    print()
    print(f"{'─'*60}")
    print("  开始发布...\n")

    results = publish_event(
        item=chosen,
        text=text,
        platforms=platforms,
        debugger_url=cdp,
        dry_run=args.dry_run,
    )

    print(f"\n{'─'*60}")
    ok_n = sum(1 for r in results.values() if r.get("success"))
    print(f"  结果：{ok_n}/{len(platforms)} 成功\n")
    for plat, res in results.items():
        label = PLATFORM_LABELS.get(plat, plat)
        status = "[OK] success" if res.get("success") else "[FAIL] failed"
        err = f" ({res.get('error')})" if not res.get("success") else ""
        url = f"\n       {res.get('url', '')}" if res.get("url") else ""
        print(f"  {status}  {label} {err}{url}")
    print()


if __name__ == "__main__":
    main()
