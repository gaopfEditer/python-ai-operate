#!/usr/bin/env python3
# coding=utf-8
"""可选：将 CDP Cookie 写入 X session 文件（正常运行 Console 不需要）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Optional: export X API session file from CDP")
    parser.add_argument("--debugger", default="127.0.0.1:9223")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    from signals.cdp_session_loader import pull_x_session_from_cdp, resolve_debugger_url
    from signals.x_session import load_x_session, merge_x_supplemental, save_x_session

    dbg = resolve_debugger_url(explicit=str(args.debugger))
    sess, err = pull_x_session_from_cdp(dbg)
    if not sess:
        print(f"未在 CDP 中找到 x.com auth_token/ct0（{dbg}）: {err}", file=sys.stderr)
        return 2

    out = Path(args.out) if args.out else ROOT / "output" / "signals" / "x_api_session.json"
    save_x_session(merge_x_supplemental(sess, load_x_session()), path=out)
    print(f"已写入 {out}（可选；运行时抓取会直接从 CDP 读 Cookie）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
