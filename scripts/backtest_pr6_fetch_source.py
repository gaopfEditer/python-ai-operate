#!/usr/bin/env python3
# coding=utf-8
"""PR#6 回测：分别验证 cookie+api / cdp，并写入 docs/backtests/。

用法（本机 Chrome 远程调试已开、已登录 x.com / binance.com）:
  .venv/bin/python scripts/backtest_pr6_fetch_source.py

环境变量:
  SMOKE_X_LIST_ID   默认 2088443239435215337
  SMOKE_BS_PROFILE  默认 yanchibit
  SKIP_CDP_HEAVY=1  跳过耗时的 CDP 页面滚动（只测 cookie+api）
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# CDP 访问 127.0.0.1 不能走系统 SOCKS；对外 API（x.com/bapi）需要本机 HTTP 代理。
import urllib.request

_CDP_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
# macOS 系统代理常见为 7891（Clash）；仅对 http/https 启用，localhost 走直连
_SYS_HTTP_PROXY = os.environ.get("BACKTEST_HTTP_PROXY", "http://127.0.0.1:7891")
_API_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler(
        {
            "http": _SYS_HTTP_PROXY,
            "https": _SYS_HTTP_PROXY,
        }
    )
)


def _use_cdp_network() -> None:
    """本地 CDP / websocket 友好：禁用代理。"""
    urllib.request.install_opener(_CDP_OPENER)
    for k in (
        "ALL_PROXY",
        "all_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "SOCKS_PROXY",
        "socks_proxy",
    ):
        os.environ.pop(k, None)
    os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1,*"
    os.environ["no_proxy"] = "127.0.0.1,localhost,::1,*"


def _use_api_network() -> None:
    """对外 GraphQL/bapi：走本机 HTTP 代理，避免直连 SSL 被墙/被掐。"""
    urllib.request.install_opener(_API_OPENER)
    os.environ["HTTP_PROXY"] = _SYS_HTTP_PROXY
    os.environ["HTTPS_PROXY"] = _SYS_HTTP_PROXY
    os.environ["http_proxy"] = _SYS_HTTP_PROXY
    os.environ["https_proxy"] = _SYS_HTTP_PROXY
    os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1"
    os.environ["no_proxy"] = "127.0.0.1,localhost,::1"
    os.environ.pop("ALL_PROXY", None)
    os.environ.pop("all_proxy", None)
    os.environ.pop("SOCKS_PROXY", None)


_use_cdp_network()


def _map_post_source_to_fetch(src: str) -> str:
    s = (src or "").lower()
    if any(x in s for x in ("bapi", "x_api", "graphql", "api")):
        return "cookie+api"
    if "cdp" in s or s in ("dom", "profile_js", "scroll"):
        return "cdp"
    return src or "unknown"


def main() -> int:
    from signals.store import resolve_signals_debugger_url

    dbg = resolve_signals_debugger_url()
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    lid = os.environ.get("SMOKE_X_LIST_ID", "2088443239435215337")
    slug = os.environ.get("SMOKE_BS_PROFILE", "yanchibit")
    skip_cdp_heavy = os.environ.get("SKIP_CDP_HEAVY", "").strip() in ("1", "true", "yes")
    records: List[Dict[str, Any]] = []

    def rec(
        platform: str,
        fetch_source: str,
        ok: bool,
        detail: str,
        *,
        count: Optional[int] = None,
        sample_sources: Optional[List[str]] = None,
        routes: Optional[List[str]] = None,
    ) -> None:
        row = {
            "platform": platform,
            "fetch_source": fetch_source,
            "ok": bool(ok),
            "count": count,
            "detail": detail,
            "sample_sources": sample_sources or [],
            "routes": routes or [],
            "at": datetime.now(timezone.utc).isoformat(),
        }
        records.append(row)
        print(
            f"[{platform}/{fetch_source}] ok={ok} count={count} "
            f"sources={sample_sources or []} | {detail}"
        )

    # ---------- X cookie+api ----------
    try:
        from signals.x_api import fetch_list_timeline_api
        from signals.x_session import resolve_x_session, session_ready

        print("=== X: resolve session (CDP bootstrap → cookie+api) ===")
        _use_cdp_network()
        resolve_x_session(debugger_url=dbg, progress=print, force_refresh=True)
        if not session_ready():
            rec("x", "cookie+api", False, "session_ready=False after CDP bootstrap")
        else:
            _use_api_network()
            res = fetch_list_timeline_api(
                lid, since=since, max_tweets=5, progress=print
            )
            items = res.get("items") or []
            srcs = sorted(
                {str(i.get("source") or "") for i in items if isinstance(i, dict)}
            )
            rec(
                "x",
                "cookie+api",
                bool(res.get("success")),
                f"route={res.get('route')} err={res.get('error')}",
                count=res.get("count")
                if res.get("count") is not None
                else len(items),
                sample_sources=srcs,
                routes=[str(res.get("route") or "")],
            )
    except Exception as e:
        rec("x", "cookie+api", False, f"exception: {e}")
        traceback.print_exc()

    # ---------- X cdp (force no API) ----------
    if skip_cdp_heavy:
        rec("x", "cdp", False, "skipped (SKIP_CDP_HEAVY=1)")
    else:
        try:
            print("=== X: CDP list timeline (SIGNALS_X_USE_CDP=1) ===")
            _use_cdp_network()
            os.environ["SIGNALS_X_USE_CDP"] = "1"
            # clear cached primary flags if module already imported
            from signals import crawl as crawl_mod

            res = crawl_mod.crawl_list_timeline(
                lid,
                since=since,
                max_tweets=5,
                max_scroll=4,
                progress=print,
                realtime_incremental=True,
            )
            items = res.get("items") or res.get("tweets") or []
            if not isinstance(items, list):
                items = []
            srcs = sorted(
                {str(i.get("source") or "") for i in items if isinstance(i, dict)}
            )
            # infer fetch_source from item sources or success path
            inferred = "cdp"
            if srcs and all(_map_post_source_to_fetch(s) == "cookie+api" for s in srcs):
                inferred = "cookie+api"
            rec(
                "x",
                "cdp",
                bool(res.get("success", len(items) > 0)),
                f"keys={list(res.keys())[:12]} err={res.get('error')} inferred_path={inferred}",
                count=res.get("count")
                if res.get("count") is not None
                else len(items),
                sample_sources=srcs,
            )
        except Exception as e:
            rec("x", "cdp", False, f"exception: {e}")
            traceback.print_exc()
        finally:
            os.environ.pop("SIGNALS_X_USE_CDP", None)

    # ---------- Square cookie+api ----------
    try:
        print("=== Square: bapi cookie+api ===")
        from signals.binance_square.bapi import fetch_profile_posts, resolve_square_uid
        from signals.binance_square.realtime import ensure_binance_session_for_realtime
        from signals.binance_square.session import session_diagnostics

        _use_cdp_network()
        ok_sess = ensure_binance_session_for_realtime(print, debugger_url=dbg)
        diag = session_diagnostics()
        print("Square session:", diag)
        if not ok_sess and not diag.get("ready"):
            rec(
                "binance_square",
                "cookie+api",
                False,
                f"session not ready: {diag}",
            )
        else:
            _use_api_network()
            uid = resolve_square_uid(slug)
            posts = fetch_profile_posts(
                slug,
                max_items=5,
                since=since,
                progress=print,
                realtime_incremental=True,
            )
            srcs = sorted(
                {str(p.get("source") or "") for p in posts if isinstance(p, dict)}
            )
            rec(
                "binance_square",
                "cookie+api",
                bool(posts),
                f"uid={str(uid)[:12]} diag_ready={diag.get('ready')} has_cookie={diag.get('has_cookie')} has_fp={diag.get('has_fingerprint')}",
                count=len(posts),
                sample_sources=srcs,
                routes=["bapi_profile"],
            )
    except Exception as e:
        rec("binance_square", "cookie+api", False, f"exception: {e}")
        traceback.print_exc()

    # ---------- Square cdp ----------
    if skip_cdp_heavy:
        rec("binance_square", "cdp", False, "skipped (SKIP_CDP_HEAVY=1)")
    else:
        try:
            print("=== Square: CDP profile (try_bapi=False) ===")
            _use_cdp_network()
            os.environ["BINANCE_SQUARE_USE_CDP"] = "1"
            os.environ["BINANCE_SQUARE_USE_API"] = "0"
            from signals.binance_square.crawl import run_binance_square_fetch

            res = run_binance_square_fetch(
                profile_ids=[slug],
                debugger_url=dbg,
                cutoff_hours=24,
                max_posts_per_profile=5,
                try_bapi=False,
                progress=print,
                realtime_incremental=True,
            )
            posts = res.get("posts") or res.get("items") or []
            if not isinstance(posts, list):
                posts = []
            srcs = sorted(
                {str(p.get("source") or "") for p in posts if isinstance(p, dict)}
            )
            routes = list(res.get("routes") or [])
            rec(
                "binance_square",
                "cdp",
                bool(posts) or "profile_cdp" in routes,
                f"routes={routes} keys={list(res.keys())[:14]} err={res.get('error')}",
                count=len(posts) if posts else res.get("count"),
                sample_sources=srcs,
                routes=routes,
            )
        except Exception as e:
            rec("binance_square", "cdp", False, f"exception: {e}")
            traceback.print_exc()
        finally:
            os.environ.pop("BINANCE_SQUARE_USE_CDP", None)
            os.environ.pop("BINANCE_SQUARE_USE_API", None)

    # ---------- write report ----------
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "docs" / "backtests" / f"pr6_fetch_source_{ts}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# PR#6 回测：卡片拉取路径 `cookie+api` vs `cdp`",
        "",
        f"- 时间（Asia/Hong_Kong）: {datetime.now().astimezone().isoformat()}",
        f"- debugger: `{dbg}`",
        f"- X list: `{lid}` / Square profile: `@{slug}`",
        "- 约定: `cookie+api` = Cookie + HTTP(GraphQL/bapi)；`cdp` = 页面 CDP 抓取。",
        "- 注: 本脚本对 urllib 禁用系统代理，规避 macOS SOCKS→CDP ws 失败。",
        "",
        "| platform | fetch_source | ok | count | post.source | routes | detail |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            "| {platform} | `{fs}` | {ok} | {count} | {srcs} | {routes} | {detail} |".format(
                platform=r["platform"],
                fs=r["fetch_source"],
                ok=r["ok"],
                count=r["count"],
                srcs=", ".join(r["sample_sources"]) or "-",
                routes=", ".join(r["routes"]) or "-",
                detail=str(r["detail"]).replace("|", "/"),
            )
        )
    lines += [
        "",
        "## 卡片标注缺口",
        "",
        "- 帖子层: `source` 已有 `bapi_profile` / `profile_cdp` / `x_api` 等。",
        "- 卡片层: `source_mode` 仍是业务模式（`list_realtime` / `binance_square`），未标 `cookie+api`|`cdp`。",
        "- 建议: 卡片增加 `fetch_source`（或并入 `source_modes`），控制台显示「来源」。",
        "",
        "## raw JSON",
        "",
        "```json",
        json.dumps(records, ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    latest = ROOT / "docs" / "backtests" / "pr6_fetch_source_latest.md"
    latest.write_text("\n".join(lines), encoding="utf-8")
    print("WROTE", out)
    print("WROTE", latest)

    api_fail = [
        r
        for r in records
        if r["fetch_source"] == "cookie+api" and not r["ok"]
    ]
    if api_fail:
        print(
            "结论: cookie+api 存在失败样本 —",
            "; ".join(f"{r['platform']}: {r['detail'][:120]}" for r in api_fail),
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
