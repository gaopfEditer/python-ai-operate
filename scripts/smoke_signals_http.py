#!/usr/bin/env python3
# coding=utf-8
"""Live smoke（需真实会话）：SIGNALS_HTTP_SMOKE=1 python scripts/smoke_signals_http.py"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    if os.environ.get("SIGNALS_HTTP_SMOKE") != "1":
        print("跳过：设置 SIGNALS_HTTP_SMOKE=1 以运行联调 smoke")
        return 0

    from signals.x_api import fetch_list_timeline_api
    from signals.x_session import session_ready
    from signals.binance_square.bapi import fetch_profile_posts
    from signals.binance_square.session import session_ready as bn_ready

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    ok = 0

    if session_ready():
        lid = os.environ.get("SMOKE_X_LIST_ID", "2088443239435215337")
        res = fetch_list_timeline_api(lid, since=since, max_tweets=5, progress=print)
        print("X list:", res.get("success"), "count=", res.get("count"), "route=", res.get("route"))
        ok += 1 if res.get("success") else 0
    else:
        print("X 会话未配置，跳过列表 smoke")

    slug = os.environ.get("SMOKE_BS_PROFILE", "yanchibit")
    if bn_ready() or True:
        try:
            posts = fetch_profile_posts(slug, max_items=5, since=since, progress=print)
            print(f"Square @{slug}: {len(posts)} posts")
            ok += 1 if posts else 0
        except Exception as e:
            print(f"Square smoke 失败: {e}")

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
