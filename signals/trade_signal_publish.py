# coding=utf-8
"""Telegram 交易信号 → AI 短评 + OI 形态图截图 → CDP 发布。

触发方（discord-collector /telegram 建卡）调用：
  POST /api/v1/trade-signal/publish
最终发布走 docs/cdp-publish-api.md 的 POST /api/v1/publish。
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = PROJECT_ROOT / "output" / "oi_chart_cache"


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def normalize_trade_symbol(raw: Any) -> str:
    s = str(raw or "").strip().upper().replace(" ", "")
    if not s or s in ("待补充", "N/A", "-"):
        return ""
    s = re.sub(r"[^A-Z0-9]", "", s)
    if not s:
        return ""
    if s.endswith(("USDT", "USDC", "BUSD")):
        return s
    return f"{s}USDT"


def resolve_chart_url(*, symbol: str, oi_url: str | None = None) -> str:
    """截图用 URL。

    用户侧是 localhost:5178/oi；图表在 iframe 的 8765 形态页。
    跨域 iframe 无法直接 contentDocument，故默认直连嵌入页截 `.pattern-chart-body`。
    """
    sym = normalize_trade_symbol(symbol)
    if not sym:
        raise ValueError("缺少有效 symbol")

    custom = (oi_url or "").strip()
    if custom:
        if "#/patterns" in custom or "/#/" in custom:
            if "symbol=" not in custom:
                sep = "&" if "?" in custom.split("#", 1)[-1] else "?"
                # hash 路由：参数放在 # 后
                if "#" in custom:
                    base, frag = custom.split("#", 1)
                    if "symbol=" not in frag:
                        frag = frag + (("&" if "?" in frag else "?") + f"symbol={quote(sym)}&add=1")
                    return f"{base}#{frag}"
            return custom
        # 5178/oi?symbol=… → 改写为 8765 形态页
        parsed = urlparse(custom)
        if parsed.path.rstrip("/").endswith("/oi") or parsed.path.rstrip("/") == "/oi":
            embed = _env("OI_EMBED_URL", "http://127.0.0.1:8765").rstrip("/")
            return f"{embed}/#/patterns?symbol={quote(sym)}&add=1"

    shell = _env("OI_CHART_URL", "http://127.0.0.1:5178/oi")
    if shell.rstrip("/").endswith("/oi"):
        embed = _env("OI_EMBED_URL", "http://127.0.0.1:8765").rstrip("/")
        return f"{embed}/#/patterns?symbol={quote(sym)}&add=1"
    if "#/patterns" in shell:
        return resolve_chart_url(symbol=sym, oi_url=shell)
    return f"{shell.rstrip('/')}/#/patterns?symbol={quote(sym)}&add=1"


def shell_oi_url(symbol: str) -> str:
    """给人看的 /oi 入口（与截图页等价币种）。"""
    sym = normalize_trade_symbol(symbol)
    base = _env("OI_CHART_URL", "http://127.0.0.1:5178/oi").rstrip("/")
    return f"{base}?symbol={quote(sym)}" if sym else base


def write_short_analysis(
    *,
    symbol: str,
    direction: str,
    narrative: str = "",
    event: str = "entry",
    entry: str = "",
    targets: Any = None,
    stop_loss: str = "",
    note: str = "",
) -> str:
    """用 AI 根据方向/币种/叙事写 2～4 句短评；失败则回退模板。"""
    sym = normalize_trade_symbol(symbol) or str(symbol or "").strip() or "UNKNOWN"
    dir_raw = str(direction or "").strip().lower()
    if dir_raw in ("多", "long", "buy", "bull"):
        dir_zh = "做多"
    elif dir_raw in ("空", "short", "sell", "bear"):
        dir_zh = "做空"
    else:
        dir_zh = direction or "未知"

    event_key = str(event or "entry").strip().lower()
    event_map = {
        "entry": "开仓/入场",
        "open": "开仓/入场",
        "update": "补充止盈止损",
        "tp": "止盈相关更新",
        "take_profit": "止盈",
        "sl": "止损相关更新",
        "stop_loss": "止损",
    }
    event_zh = event_map.get(event_key, event_key or "信号")

    if isinstance(targets, (list, tuple)):
        tp_s = " / ".join(str(x).strip() for x in targets if str(x).strip())
    else:
        tp_s = str(targets or "").strip()

    coin = sym.replace("USDT", "")
    bits = [f"【{coin}】{dir_zh} · {event_zh}"]
    detail_parts = []
    if entry:
        detail_parts.append(f"入场 {entry}")
    if tp_s:
        detail_parts.append(f"止盈 {tp_s}")
    if stop_loss:
        detail_parts.append(f"止损 {stop_loss}")
    if detail_parts:
        bits.append(" · ".join(detail_parts))
    extra = (narrative or note or "").strip()[:280]
    if extra:
        bits.append(extra)
    fallback = "\n".join(bits)

    prompt = (
        f"币种：{sym}\n"
        f"方向：{dir_zh}\n"
        f"事件：{event_zh}\n"
        f"入场：{entry or '—'}\n"
        f"止盈：{tp_s or '—'}\n"
        f"止损：{stop_loss or '—'}\n"
        f"备注：{(note or '')[:200] or '—'}\n"
        f"叙事原文：\n{(narrative or '')[:1200] or '—'}\n\n"
        "请用中文写 2～4 句简洁行情解读，结合方向与叙事要点；"
        "不要编造未给出的价位与保证收益；不要标题党；不要 emoji 堆砌。"
    )
    system = (
        "你是加密货币交易助理，输出可直接发到社媒的短评正文。"
        "语气克制、信息密度高。"
    )
    try:
        from utils.ai_client import generate_text

        r = generate_text(prompt, system_prompt=system, temperature=0.35, max_tokens=320)
        if r.get("success") and str(r.get("content") or "").strip():
            text = str(r["content"]).strip()
            # 去掉常见 markdown 围栏
            text = re.sub(r"^```\w*\n?", "", text).strip()
            text = re.sub(r"\n?```$", "", text).strip()
            return text[:1800]
        logger.warning("AI 短评失败，用模板: %s", r.get("error"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI 短评异常，用模板: %s", exc)
    return fallback


def _wait_chart_ready(page: Any, selector: str, timeout_sec: float = 35.0) -> Dict[str, float]:
    deadline = time.time() + timeout_sec
    last_err = ""
    while time.time() < deadline:
        try:
            box = page.eval_js(
                f"""
const sel = {json.dumps(selector)};
const el = document.querySelector(sel);
if (!el) return null;
const canvas = el.querySelector('canvas');
const r = el.getBoundingClientRect();
if (r.width < 40 || r.height < 40) return null;
// 等 K 线 canvas 出现更稳
if (!canvas) return {{pending: true, x: r.x, y: r.y, width: r.width, height: r.height}};
return {{
  x: r.x, y: r.y, width: r.width, height: r.height,
  dpr: window.devicePixelRatio || 1
}};
"""
            )
            if isinstance(box, dict) and box.get("pending"):
                time.sleep(0.45)
                continue
            if isinstance(box, dict) and float(box.get("width") or 0) >= 40:
                return {
                    "x": float(box["x"]),
                    "y": float(box["y"]),
                    "width": float(box["width"]),
                    "height": float(box["height"]),
                }
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
        time.sleep(0.4)
    raise TimeoutError(f"等待 {selector} 超时{(': ' + last_err) if last_err else ''}")


def screenshot_pattern_chart(
    *,
    symbol: str,
    oi_url: str | None = None,
    selector: str | None = None,
    debugger_url: str | None = None,
    out_path: Path | None = None,
) -> Path:
    """CDP 打开 OI 形态图并截 `.pattern-chart-body`。"""
    from allnews_mornitor.cdp_browser import BackgroundTarget, _CdpClient, _browser_ws_url

    chart_url = resolve_chart_url(symbol=symbol, oi_url=oi_url)
    css = (selector or _env("OI_CHART_SELECTOR", ".pattern-chart-body")).strip() or ".pattern-chart-body"
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = out_path or (_CACHE_DIR / f"oi_{normalize_trade_symbol(symbol)}_{uuid.uuid4().hex[:10]}.png")

    # 可选覆盖调试口（截图默认跟 crawl CDP，与发布 9222 可分开）
    prev = None
    if debugger_url:
        prev = os.environ.get("CDP_DEBUGGER_URL")
        os.environ["CDP_DEBUGGER_URL"] = debugger_url.replace("http://", "").replace("https://", "")

    client: Optional[_CdpClient] = None
    page: Optional[BackgroundTarget] = None
    try:
        client = _CdpClient(_browser_ws_url())
        page = BackgroundTarget.create(client, "about:blank")
        logger.info("OI 图表导航: %s", chart_url)
        page.silent_navigate(chart_url)
        time.sleep(1.2)
        box = _wait_chart_ready(page, css)
        # 滚入视口，避免 clip 被裁
        page.eval_js(
            f"""
const el = document.querySelector({json.dumps(css)});
if (el) el.scrollIntoView({{block: 'center', inline: 'nearest'}});
"""
        )
        time.sleep(0.35)
        box = _wait_chart_ready(page, css, timeout_sec=8.0)
        result = page.call(
            "Page.captureScreenshot",
            {
                "format": "png",
                "fromSurface": True,
                "captureBeyondViewport": True,
                "clip": {
                    "x": max(0.0, box["x"]),
                    "y": max(0.0, box["y"]),
                    "width": box["width"],
                    "height": box["height"],
                    "scale": 1,
                },
            },
            timeout=90.0,
        )
        data_b64 = str(result.get("data") or "")
        if not data_b64:
            raise RuntimeError("Page.captureScreenshot 未返回 data")
        dest.write_bytes(base64.b64decode(data_b64))
        logger.info("OI 图表已截图 → %s (%dx%d)", dest, int(box["width"]), int(box["height"]))
        return dest
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        if debugger_url is not None:
            if prev is None:
                os.environ.pop("CDP_DEBUGGER_URL", None)
            else:
                os.environ["CDP_DEBUGGER_URL"] = prev


def _default_platforms() -> List[str]:
    raw = _env("TRADE_SIGNAL_PUBLISH_PLATFORMS", "")
    if raw:
        return [p.strip() for p in raw.split(",") if p.strip()]
    try:
        from public.index import load_publish_config

        cfg = load_publish_config() or {}
        plats = cfg.get("default_platforms") or []
        if isinstance(plats, list) and plats:
            return [str(p).strip() for p in plats if str(p).strip()]
    except Exception:
        pass
    return ["gate"]


def publish_text_with_image(
    *,
    text: str,
    image_path: Path,
    platforms: Optional[List[str]] = None,
    title: str = "",
    submit: bool = True,
    debugger_url: str | None = None,
) -> Dict[str, Any]:
    """调用本进程发布实现（等同 /api/v1/publish）。"""
    from console.publish_api import _run_publish

    path = Path(image_path)
    if not path.is_file():
        return {"success": False, "error": f"截图不存在: {path}"}
    payload = {
        "title": (title or "").strip(),
        "content": (text or "").strip(),
        "platforms": platforms or _default_platforms(),
        "tags": None,
        "debugger_url": (debugger_url or "").strip(),
        "submit": bool(submit),
        "media_paths": [str(path.resolve())],
    }
    return _run_publish(payload)


def run_trade_signal_pipeline(body: Dict[str, Any]) -> Dict[str, Any]:
    """完整编排：分析 → 截图 → 发布。"""
    symbol = str(body.get("symbol") or "").strip()
    direction = str(body.get("direction") or "").strip()
    if not symbol:
        return {"success": False, "error": "缺少 symbol"}
    if not direction:
        return {"success": False, "error": "缺少 direction"}

    event = str(body.get("event") or body.get("phase") or "entry").strip() or "entry"
    narrative = str(body.get("narrative") or body.get("body") or body.get("rawContent") or "").strip()
    note = str(body.get("note") or "").strip()
    entry = str(body.get("entry") or "").strip()
    stop_loss = str(body.get("stopLoss") or body.get("stop_loss") or "").strip()
    targets = body.get("targets")
    if targets is None:
        targets = body.get("takeProfit") or body.get("take_profit") or ""

    skip_ai = bool(body.get("skip_ai"))
    skip_shot = bool(body.get("skip_screenshot"))
    skip_publish = bool(body.get("skip_publish"))
    submit = body.get("submit")
    if submit is None or submit == "":
        submit = True

    platforms = body.get("platforms")
    if isinstance(platforms, str):
        platforms = [p.strip() for p in platforms.split(",") if p.strip()]
    elif not isinstance(platforms, list):
        platforms = None

    analysis = (
        str(body.get("text") or body.get("content") or "").strip()
        if skip_ai
        else write_short_analysis(
            symbol=symbol,
            direction=direction,
            narrative=narrative,
            event=event,
            entry=entry,
            targets=targets,
            stop_loss=stop_loss,
            note=note,
        )
    )
    if skip_ai and not analysis:
        analysis = write_short_analysis(
            symbol=symbol,
            direction=direction,
            narrative=narrative,
            event=event,
            entry=entry,
            targets=targets,
            stop_loss=stop_loss,
            note=note,
        )

    image_path: Optional[Path] = None
    chart_url = ""
    if not skip_shot:
        chart_url = resolve_chart_url(symbol=symbol, oi_url=body.get("oi_url") or body.get("oiUrl"))
        image_path = screenshot_pattern_chart(
            symbol=symbol,
            oi_url=body.get("oi_url") or body.get("oiUrl"),
            selector=body.get("selector") or None,
            debugger_url=str(body.get("chart_debugger_url") or body.get("cdp_debugger_url") or "").strip()
            or None,
        )

    publish_result: Dict[str, Any] = {"skipped": True}
    if not skip_publish:
        if image_path is None and not analysis:
            return {"success": False, "error": "无正文且无截图，无法发布"}
        if image_path is None:
            # 仅文：仍走 publish
            from console.publish_api import _run_publish

            publish_result = _run_publish(
                {
                    "title": str(body.get("title") or "").strip(),
                    "content": analysis,
                    "platforms": platforms or _default_platforms(),
                    "tags": None,
                    "debugger_url": str(body.get("debugger_url") or "").strip(),
                    "submit": bool(submit),
                    "media_paths": [],
                }
            )
        else:
            publish_result = publish_text_with_image(
                text=analysis,
                image_path=image_path,
                platforms=platforms,
                title=str(body.get("title") or "").strip(),
                submit=bool(submit),
                debugger_url=str(body.get("debugger_url") or "").strip() or None,
            )

    ok = True if skip_publish else bool(publish_result.get("success"))
    return {
        "success": ok,
        "analysis": analysis,
        "chart_url": chart_url or resolve_chart_url(symbol=symbol, oi_url=body.get("oi_url")),
        "shell_url": shell_oi_url(symbol),
        "image_path": str(image_path) if image_path else None,
        "publish": publish_result,
        "symbol": normalize_trade_symbol(symbol),
        "direction": direction,
        "event": event,
        "error": None if ok else str(publish_result.get("error") or "发布失败"),
    }
