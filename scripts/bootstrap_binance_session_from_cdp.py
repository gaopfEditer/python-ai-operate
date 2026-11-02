#!/usr/bin/env python3
# coding=utf-8
"""从 CDP 导出 binance.com Cookie + 常见指纹头到 output/signals/binance_square_session.json。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_WANT_COOKIES = ("csrftoken", "bnc-uuid", "BNC-UUID")
_WANT_HEADERS = ("device-info", "fvideo-id", "fvideo-token", "bnc-uuid", "csrftoken")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Binance Square session from CDP")
    parser.add_argument("--debugger", default="127.0.0.1:9223")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    from allnews_mornitor.cdp_browser import _http_json
    from signals.binance_square.session import save_binance_session

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
    headers: dict = {}
    for page in pages or []:
        ws = page.get("webSocketDebuggerUrl") if isinstance(page, dict) else None
        if not ws:
            continue
        try:
            from allnews_mornitor.cdp_browser import _CdpClient

            client = _CdpClient(ws)
            client.send("Network.enable", {})
            res = client.send(
                "Network.getCookies",
                {"urls": ["https://www.binance.com", "https://binance.com"]},
            )
            for c in res.get("cookies") or []:
                if not isinstance(c, dict):
                    continue
                name = str(c.get("name") or "")
                val = str(c.get("value") or "")
                if name.lower() in {x.lower() for x in _WANT_COOKIES} and val:
                    cookies[name] = val
            client.close()
        except Exception:
            continue
        if cookies:
            break

    for k in ("csrftoken", "bnc-uuid"):
        if cookies.get(k):
            headers[k] = cookies[k]

    if not cookies:
        print("未找到 binance.com Cookie；请先登录币安并打开 Square。", file=sys.stderr)
        return 2

    out = Path(args.out) if args.out else ROOT / "output" / "signals" / "binance_square_session.json"
    save_binance_session({"cookies": cookies, "headers": headers}, path=out)
    print(f"已写入 {out}")
    print("若 bapi 仍返回空 data，请在 Square 页滚动一次后重跑，或从 DevTools 复制 device-info 等到 headers。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
