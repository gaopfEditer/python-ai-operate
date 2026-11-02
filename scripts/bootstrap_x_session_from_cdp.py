#!/usr/bin/env python3
# coding=utf-8
"""从已登录 Chrome CDP 导出 X auth_token + ct0 到 output/signals/x_api_session.json。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap X API session from CDP cookies")
    parser.add_argument(
        "--debugger",
        default="127.0.0.1:9223",
        help="Chrome remote debugging host:port",
    )
    parser.add_argument(
        "--out",
        default="",
        help="输出 JSON（默认 output/signals/x_api_session.json）",
    )
    args = parser.parse_args()

    from allnews_mornitor.cdp_browser import _http_json
    from signals.x_session import save_x_session

    host = str(args.debugger).replace("http://", "").replace("https://", "").strip("/")
    try:
        import allnews_mornitor.cdp_browser as cdp_mod

        orig = cdp_mod.get_debugger_url

        def _patched() -> str:
            return host

        cdp_mod.get_debugger_url = _patched  # type: ignore
    except Exception:
        pass

    try:
        pages = _http_json("/json/list")
    except Exception as e:
        print(f"无法连接 CDP ({host}): {e}", file=sys.stderr)
        return 1

    cookies: dict = {}
    for page in pages or []:
        if not isinstance(page, dict):
            continue
        ws = page.get("webSocketDebuggerUrl")
        if not ws:
            continue
        try:
            from allnews_mornitor.cdp_browser import _CdpClient

            client = _CdpClient(ws)
            client.send("Network.enable", {})
            res = client.send("Network.getCookies", {"urls": ["https://x.com", "https://twitter.com"]})
            for c in res.get("cookies") or []:
                if not isinstance(c, dict):
                    continue
                name = str(c.get("name") or "")
                if name in ("auth_token", "ct0"):
                    cookies[name] = str(c.get("value") or "")
            client.close()
        except Exception:
            continue
        if cookies.get("auth_token") and cookies.get("ct0"):
            break

    if not cookies.get("auth_token") or not cookies.get("ct0"):
        print("未在 CDP Chrome 中找到 x.com 的 auth_token/ct0，请先登录 X。", file=sys.stderr)
        return 2

    out = Path(args.out) if args.out else ROOT / "output" / "signals" / "x_api_session.json"
    save_x_session(
        {
            "auth_token": cookies["auth_token"],
            "ct0": cookies["ct0"],
        },
        path=out,
    )
    print(f"已写入 {out}")
    print("提示：若 GraphQL 返回 404，请在 X 上打开列表/主页让 chrome-x-toolkit 捕获最新 queryId，写入 query_ids。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
