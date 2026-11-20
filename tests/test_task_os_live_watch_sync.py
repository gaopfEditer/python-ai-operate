# coding=utf-8
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.task_os_live_watch_digest import collect_publish, collect_signals, collect_vpn
from scripts.task_os_live_watch_sync import merge_feed, window_for_slot

HKT = ZoneInfo("Asia/Hong_Kong")


def _slot12():
    ref = datetime(2026, 11, 17, 12, 0, tzinfo=HKT)
    return window_for_slot(12, ref)


class TestLiveWatchWindow(unittest.TestCase):
    def test_slot_8_window(self):
        ref = datetime(2026, 11, 16, 8, 5, tzinfo=HKT)
        start, end = window_for_slot(8, ref)
        self.assertEqual(start.isoformat(timespec="seconds"), "2026-11-16T00:00:00+08:00")
        self.assertEqual(end.isoformat(timespec="seconds"), "2026-11-16T08:00:00+08:00")

    def test_slot_0_window(self):
        ref = datetime(2026, 11, 16, 0, 10, tzinfo=HKT)
        start, end = window_for_slot(0, ref)
        self.assertEqual(start.isoformat(timespec="seconds"), "2026-11-15T20:00:00+08:00")
        self.assertEqual(end.isoformat(timespec="seconds"), "2026-11-16T00:00:00+08:00")

    def test_slot_12_window(self):
        ref = datetime(2026, 11, 16, 12, 0, tzinfo=HKT)
        start, end = window_for_slot(12, ref)
        self.assertEqual(start.isoformat(timespec="seconds"), "2026-11-16T08:00:00+08:00")
        self.assertEqual(end.isoformat(timespec="seconds"), "2026-11-16T12:00:00+08:00")


class TestSignalSummary(unittest.TestCase):
    def _db(self, path: Path) -> None:
        with sqlite3.connect(path) as conn:
            conn.execute(
                """
                CREATE TABLE signal_cards (
                    tweet_id TEXT, user_handle TEXT, author TEXT, url TEXT, text TEXT,
                    created_at TEXT, updated_at TEXT, parsed_at TEXT,
                    signal_json TEXT, extra_json TEXT, list_id TEXT
                )
                """
            )
            extra = json.dumps(
                {"source_mode": "binance_square", "channel": {"channelName": "禹柔"}},
                ensure_ascii=False,
            )
            conn.execute(
                """
                INSERT INTO signal_cards VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "366",
                    "yurou",
                    "@yurou",
                    "https://www.binance.com/zh-CN/square/post/366",
                    "长文",
                    "2026-11-17T09:15:00+08:00",
                    "2026-11-17T09:16:00+08:00",
                    "2026-11-17T09:16:00+08:00",
                    json.dumps({"coins": ["BTC"], "direction": "short", "summary": "反弹做空"}, ensure_ascii=False),
                    extra,
                    "binance:yurou",
                ),
            )
            conn.execute(
                """
                INSERT INTO signal_cards VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "old",
                    "yurou",
                    "@yurou",
                    "https://example.invalid/old",
                    "窗口外",
                    "2026-11-17T07:00:00+08:00",
                    "2026-11-17T07:00:00+08:00",
                    "2026-11-17T07:00:00+08:00",
                    json.dumps({"coins": ["ETH"], "direction": "long", "summary": "不该出现"}),
                    extra,
                    "binance:yurou",
                ),
            )
            conn.execute(
                """
                INSERT INTO signal_cards VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "chat",
                    "someone",
                    "@someone",
                    "",
                    "闲聊",
                    "2026-11-17T10:00:00+08:00",
                    "2026-11-17T10:00:00+08:00",
                    "2026-11-17T10:00:00+08:00",
                    json.dumps({"coins": [], "direction": "watch", "summary": "观望"}),
                    extra,
                    "binance:someone",
                ),
            )

    def test_one_summary_in_window(self):
        start, end = _slot12()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "cards.db"
            self._db(db)
            items = collect_signals(db, start, end, set(), set(), {}, slot=12)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["id"], "sig:summary:12:2026-11-17")
        self.assertEqual(item["category"], "signal")
        self.assertEqual(item["title"], "信号汇总 · 08:00–12:00 · 1 条")
        self.assertIn("币安广场 · 禹柔（yurou） · 做空 · 反弹做空", item["body"])
        self.assertIn("https://www.binance.com/zh-CN/square/post/366", item["body"])
        self.assertNotIn("不该出现", item["body"])
        self.assertNotIn("观望", item["body"])
        self.assertEqual(item["meta"]["count"], 1)
        self.assertEqual(item["meta"]["items"][0]["account"], "禹柔（yurou）")
        self.assertEqual(item["meta"]["window_start"], "2026-11-17T08:00:00+08:00")
        self.assertEqual(item["meta"]["window_end"], "2026-11-17T12:00:00+08:00")

    def test_empty_window_is_explicit(self):
        start, end = _slot12()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "cards.db"
            with sqlite3.connect(db) as conn:
                conn.execute(
                    """
                    CREATE TABLE signal_cards (
                        tweet_id TEXT, user_handle TEXT, created_at TEXT, updated_at TEXT,
                        signal_json TEXT, extra_json TEXT
                    )
                    """
                )
            items = collect_signals(db, start, end, set(), set(), {}, slot=12)
        self.assertEqual(items[0]["body"], "本时段无信号")
        self.assertEqual(items[0]["meta"]["count"], 0)
        self.assertEqual(items[0]["meta"]["items"], [])

    def test_db_missing_is_not_reported_as_no_signal(self):
        start, end = _slot12()
        items = collect_signals(Path("/tmp/does-not-exist-cards.db"), start, end, set(), set(), {}, slot=12)
        self.assertIn("读取失败", items[0]["title"])
        self.assertNotIn("本时段无信号", items[0]["body"])
        self.assertIsNone(items[0]["meta"]["count"])

    def test_merge_keeps_historical_signal_rows(self):
        start, _end = _slot12()
        existing = {
            "version": 1,
            "items": [
                {
                    "id": "sig:binance_square:366",
                    "category": "signal",
                    "ts": "2026-11-16T13:16:44+08:00",
                    "title": "币安广场 · btc7873 · ETH short",
                    "body": "旧逐条",
                    "meta": {},
                }
            ],
        }
        summary = {
            "id": "sig:summary:12:2026-11-17",
            "category": "signal",
            "ts": start.isoformat(),
            "title": "信号汇总 · 08:00–12:00 · 0 条",
            "body": "本时段无信号",
            "meta": {"count": 0, "items": []},
        }
        merged = merge_feed(existing, [summary], 500, "2026-11-17T12:00+08:00")
        ids = [it["id"] for it in merged["items"]]
        self.assertIn("sig:binance_square:366", ids)
        self.assertIn("sig:summary:12:2026-11-17", ids)


class TestPublishSummary(unittest.TestCase):
    def test_log_and_history_merge(self):
        start, end = _slot12()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "publish_2026-11-17.log"
            log.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "ts": "2026-11-17T09:01:00+08:00",
                                "event": "platform_ok",
                                "platform": "x",
                                "platform_name": "X / Twitter",
                                "post_url": "https://x.com/a/status/1",
                                "message": "发布成功",
                                "job_id": "job1",
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "ts": "2026-11-17T09:05:00+08:00",
                                "event": "platform_fail",
                                "platform": "xueqiu",
                                "platform_name": "雪球",
                                "failure_category": "selector",
                                "message": "未找到编辑框",
                                "job_id": "job1",
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            db = root / "publish_history.db"
            with sqlite3.connect(db) as conn:
                conn.execute(
                    """
                    CREATE TABLE publish_history (
                        id TEXT, title TEXT, status TEXT, success_count INTEGER, total_count INTEGER,
                        message TEXT, created_at TEXT, platforms_json TEXT, results_json TEXT,
                        job_id TEXT, entry_kind TEXT
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO publish_history VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "h1",
                        "早盘观点",
                        "done",
                        1,
                        2,
                        "部分完成",
                        "2026-11-17T09:06:00",
                        json.dumps(["x", "xueqiu"]),
                        json.dumps(
                            [
                                {"platform": "x", "name": "X / Twitter", "success": True},
                                {"platform": "xueqiu", "name": "雪球", "success": False, "error": "历史库失败"},
                            ]
                        ),
                        "job1",
                        "run",
                    ),
                )
            items = collect_publish(root, db, start, end, slot=12)
        item = items[0]
        self.assertEqual(item["title"], "发布 · 成功 1 / 失败 1")
        self.assertEqual(item["meta"]["success_count"], 1)
        self.assertEqual(item["meta"]["fail_count"], 1)
        self.assertEqual(len(item["meta"]["items"]), 2)
        self.assertIn("早盘观点", item["body"])
        self.assertIn("https://x.com/a/status/1", item["body"])
        self.assertIn("selector: 未找到编辑框", item["body"])
        self.assertNotIn("历史库失败", item["body"])

    def test_missing_log_uses_history(self):
        start, end = _slot12()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "publish_history.db"
            with sqlite3.connect(db) as conn:
                conn.execute(
                    """
                    CREATE TABLE publish_history (
                        id TEXT, title TEXT, status TEXT, success_count INTEGER, total_count INTEGER,
                        message TEXT, created_at TEXT, platforms_json TEXT, results_json TEXT,
                        job_id TEXT, entry_kind TEXT
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO publish_history VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "h2",
                        "只有历史库",
                        "done",
                        1,
                        1,
                        "",
                        "2026-11-17T10:00:00",
                        json.dumps(["binance_square"]),
                        json.dumps(
                            [
                                {
                                    "platform": "binance_square",
                                    "name": "币安广场",
                                    "success": True,
                                    "url": "https://www.binance.com/zh-CN/square/post/9",
                                }
                            ]
                        ),
                        "h2",
                        "run",
                    ),
                )
            items = collect_publish(root, db, start, end, slot=12)
        item = items[0]
        self.assertEqual(item["title"], "发布 · 成功 1 / 失败 0")
        self.assertIn("币安广场", item["body"])
        self.assertIn("只有历史库", item["body"])
        self.assertIn("https://www.binance.com/zh-CN/square/post/9", item["body"])
        self.assertIn("不存在", item["body"])
        self.assertNotEqual(item["body"].strip(), item["body"].splitlines()[-1])

    def test_no_records_when_sources_exist_and_empty(self):
        start, end = _slot12()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "publish_2026-11-17.log").write_text("", encoding="utf-8")
            db = root / "publish_history.db"
            with sqlite3.connect(db) as conn:
                conn.execute(
                    """
                    CREATE TABLE publish_history (
                        id TEXT, title TEXT, status TEXT, created_at TEXT, entry_kind TEXT,
                        results_json TEXT, platforms_json TEXT, success_count INTEGER, total_count INTEGER,
                        message TEXT, job_id TEXT
                    )
                    """
                )
            items = collect_publish(root, db, start, end, slot=12)
        self.assertEqual(items[0]["title"], "发布 · 当日无发布记录")
        self.assertIn("当日无发布记录", items[0]["body"])
        self.assertEqual(items[0]["meta"]["success_count"], 0)
        self.assertEqual(items[0]["meta"]["fail_count"], 0)

    def test_missing_log_and_history_is_not_success(self):
        start, end = _slot12()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            items = collect_publish(root, root / "missing.db", start, end, slot=12)
        item = items[0]
        self.assertEqual(item["title"], "发布 · 发布日志缺失")
        self.assertIn("发布日志缺失", item["body"])
        self.assertIn("不记为成功", item["body"])
        self.assertNotIn("/Users/", item["body"])
        self.assertEqual(item["meta"]["success_count"], 0)
        self.assertEqual(item["meta"]["fail_count"], 0)
        self.assertEqual(item["meta"]["items"], [])


class TestVpnSummary(unittest.TestCase):
    def test_sparse_state_does_not_invent_counts(self):
        _start, end = _slot12()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.json"
            state.write_text(
                json.dumps({"last_health": {"ok": True, "owner": "gsycloud"}}, ensure_ascii=False),
                encoding="utf-8",
            )
            items = collect_vpn(state, 12, end, log_dir=root)
        item = items[0]
        self.assertEqual(item["title"], "VPN Guard · OK · gsycloud")
        self.assertIn("截止: 2026-11-17 12:00", item["body"])
        self.assertIn("健康: 正常", item["body"])
        self.assertIn("出口归属: gsycloud", item["body"])
        self.assertIn("不可用", item["body"])
        self.assertIsNone(item["meta"]["disconnects"])
        self.assertIsNone(item["meta"]["unstable_minutes"])
        self.assertIsNone(item["meta"]["current_node"])
        self.assertTrue(item["meta"]["ok"])
        self.assertEqual(item["meta"]["owner"], "gsycloud")

    def test_events_fill_title_body_and_meta(self):
        _start, end = _slot12()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.json"
            state.write_text(
                json.dumps(
                    {
                        "last_health": {
                            "ok": True,
                            "owner": "gsycloud",
                            "client": "clash",
                            "node": "jp-3",
                            "ip": "1.2.3.4",
                            "sites": {"ChatGPT": True, "YouTube": True, "X": True, "币安广场": True},
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            lines = [
                {"ts": "2026-11-16T01:00:00+08:00", "event": "disconnect", "reason": "timeout", "duration_sec": 300, "node": "hk-1"},
                {"ts": "2026-11-16T02:00:00+08:00", "event": "disconnect", "reason": "timeout", "duration_sec": 300, "node": "hk-1"},
                {"ts": "2026-11-16T03:00:00+08:00", "event": "disconnect", "reason": "timeout", "duration_sec": 300, "node": "hk-1"},
                {"ts": "2026-11-16T04:00:00+08:00", "event": "disconnect", "reason": "timeout", "duration_sec": 300, "node": "hk-1"},
                {"ts": "2026-11-16T05:00:00+08:00", "event": "site_check", "node": "hk-1", "sites": {"ChatGPT": False, "YouTube": True, "X": True, "币安广场": True}},
                {"ts": "2026-11-17T01:02:00+08:00", "event": "disconnect", "reason": "timeout", "duration_sec": 120, "node": "hk-1"},
                {"ts": "2026-11-17T02:10:00+08:00", "event": "disconnect", "reason": "high_latency", "duration_sec": 684, "node": "hk-1"},
                {"ts": "2026-11-17T02:22:00+08:00", "event": "switch", "from_node": "hk-1", "to_node": "sg-2", "ok": True, "to_client": "clash"},
                {"ts": "2026-11-17T03:00:00+08:00", "event": "restart", "ok": True},
                {"ts": "2026-11-17T03:05:00+08:00", "event": "site_check", "node": "sg-2", "sites": {"ChatGPT": False, "YouTube": True, "X": True, "币安广场": True}},
                {"ts": "2026-11-17T03:08:00+08:00", "event": "switch", "from_node": "sg-2", "to_node": "jp-3", "ok": True, "switched_clash": False},
                {"ts": "2026-11-17T03:10:00+08:00", "event": "site_check", "node": "jp-3", "sites": {"ChatGPT": True, "YouTube": True, "X": True, "币安广场": True}},
                {"ts": "2026-11-17T13:00:00+08:00", "event": "disconnect", "reason": "timeout", "duration_sec": 999, "node": "late"},
            ]
            (root / "events.jsonl").write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in lines) + "\n",
                encoding="utf-8",
            )
            items = collect_vpn(state, 12, end, log_dir=root)
        item = items[0]
        self.assertEqual(item["id"], "vpn:12:2026-11-17")
        self.assertEqual(
            item["title"],
            "VPN Guard · OK · gsycloud · jp-3 · 1.2.3.4 · 断开2次 / 不稳定13.4分钟",
        )
        body = item["body"]
        self.assertIn("当前客户端与节点: Clash（gsycloud） · jp-3 · 出口 IP 1.2.3.4", body)
        self.assertIn("ChatGPT 通", body)
        self.assertIn("超时 1 次，高延迟 1 次", body)
        self.assertIn("成功 2 次", body)
        self.assertIn("切过 Clash: 是", body)
        self.assertIn("重启应用: 是", body)
        self.assertIn("hk-1", body)
        self.assertIn("挡住 ChatGPT", body)
        self.assertIn("换到 jp-3", body)
        self.assertIn("换后四站都通", body)
        self.assertIn("更稳", body)
        self.assertNotIn("999", body)
        meta = item["meta"]
        self.assertEqual(meta["disconnects"], 2)
        self.assertEqual(meta["unstable_minutes"], 13.4)
        self.assertEqual(meta["current_client"], "Clash")
        self.assertEqual(meta["current_node"], "jp-3")
        self.assertEqual(meta["current_ip"], "1.2.3.4")
        self.assertEqual(meta["site_status"]["币安广场"], True)
        self.assertEqual(meta["switches"]["success"], 2)
        self.assertTrue(meta["switches"]["switched_clash"])
        self.assertTrue(meta["switches"]["restarted_app"])

    def test_daily_rollup_used_when_no_events(self):
        _start, end = _slot12()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.json"
            state.write_text(
                json.dumps(
                    {
                        "last_health": {"ok": False, "owner": "gsycloud"},
                        "today": {"date": "2026-11-17", "disconnects": 20, "unstable_minutes": 13.4, "blocks": 1},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            items = collect_vpn(state, 12, end, log_dir=root)
        self.assertEqual(items[0]["title"], "VPN Guard · FAULT · gsycloud · 断开20次 / 不稳定13.4分钟")
        self.assertIn("守卫按日汇总", items[0]["body"])
        self.assertEqual(items[0]["meta"]["disconnects"], 20)
        self.assertEqual(items[0]["meta"]["unstable_minutes"], 13.4)

    def test_usage_jsonl_real_shape(self):
        _start, end = _slot12()
        node_before = "🇨🇳台湾一号专线03"
        node_after = "🇨🇳台湾一号专线04"
        ip = "203.0.113.8"
        four_ok = (
            "chatgpt=ok (http 200, 2263ms); youtube=ok (http 200, 180ms); "
            "x=ok (http 200, 90ms); binance_square=ok (http 200, 140ms)"
        )
        blocked_detail = (
            "sites_blocked=binance_square; chatgpt=ok (http 200, 10ms); "
            "youtube=ok (http 200, 10ms); x=ok (http 200, 10ms); binance_square=BLOCKED"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state.json").write_text(
                json.dumps(
                    {
                        "last_health": {
                            "ok": True,
                            "owner": "gsycloud",
                            "country": "TW",
                            "ip": ip,
                            "gsy_node": node_after,
                            "at": "2026-11-17T11:50:00+08:00",
                        },
                        "last_action": "rotate_gsy_node_ok",
                        "last_owner": "gsycloud",
                        "manual_clash": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            rows = [
                {
                    "ts": "2026-11-17T00:30:00+08:00",
                    "event": "health",
                    "owner": "gsycloud",
                    "gsy_node": "🇨🇳香港01",
                    "ip": "198.51.100.1",
                    "ok": True,
                    "detail": four_ok,
                },
                {
                    "ts": "2026-11-17T01:00:00+08:00",
                    "event": "fail_start",
                    "owner": "gsycloud",
                    "gsy_node": "🇨🇳香港01",
                    "ip": "198.51.100.1",
                    "ok": False,
                    "detail": "timeout: timed out",
                },
                {
                    "ts": "2026-11-17T01:02:00+08:00",
                    "event": "fail_recover",
                    "owner": "gsycloud",
                    "gsy_node": "🇨🇳香港01",
                    "ok": True,
                    "detail": "downtime_sec=120",
                },
                {
                    "ts": "2026-11-17T02:10:00+08:00",
                    "event": "fail_start",
                    "owner": "gsycloud",
                    "gsy_node": "🇨🇳香港01",
                    "ok": False,
                    "detail": "latency 1574ms > 1500ms",
                },
                {
                    "ts": "2026-11-17T02:22:00+08:00",
                    "event": "fail_recover",
                    "owner": "gsycloud",
                    "ok": True,
                    "detail": "downtime_sec=684",
                },
                {
                    "ts": "2026-11-17T02:25:00+08:00",
                    "event": "node_try",
                    "owner": "gsycloud",
                    "node": "tw-try",
                    "ok": False,
                    "detail": "try tw-try",
                },
                {
                    "ts": "2026-11-17T02:30:00+08:00",
                    "event": "owner_change",
                    "owner": "clash",
                    "action": "to_clash",
                    "ok": True,
                },
                {
                    "ts": "2026-11-17T02:40:00+08:00",
                    "event": "recover_action",
                    "owner": "gsycloud",
                    "action": "return_to_gsy",
                    "gsy_node": node_before,
                    "ok": True,
                    "detail": f"node={node_before}",
                },
                {
                    "ts": "2026-11-17T03:05:00+08:00",
                    "event": "site_blocked",
                    "owner": "gsycloud",
                    "gsy_node": node_before,
                    "ip": "198.51.100.8",
                    "blocked_sites": "binance_square",
                    "detail": blocked_detail,
                },
                {
                    "ts": "2026-11-17T03:08:00+08:00",
                    "event": "node_ok",
                    "owner": "gsycloud",
                    "node": "tw-04",
                    "gsy_node": node_after,
                    "ip": ip,
                    "ok": True,
                    "detail": four_ok,
                },
                {
                    "ts": "2026-11-17T03:12:00+08:00",
                    "event": "healthy",
                    "owner": "gsycloud",
                    "gsy_node": node_after,
                    "ip": ip,
                    "ok": True,
                    "detail": four_ok,
                },
                {
                    "ts": "2026-11-17T13:00:00+08:00",
                    "event": "fail_start",
                    "owner": "gsycloud",
                    "gsy_node": "AFTER-SLOT",
                    "detail": "timeout: timed out",
                },
                {
                    "ts": "2026-11-17T13:01:00+08:00",
                    "event": "fail_recover",
                    "detail": "downtime_sec=999",
                },
            ]
            (root / "usage.jsonl").write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                encoding="utf-8",
            )
            (root / "vpn_guard.log").write_text(
                json.dumps(
                    {
                        "ts": "2026-11-17T04:00:00+08:00",
                        "event": "fail_start",
                        "detail": "timeout: timed out",
                        "gsy_node": "DECOY-NODE",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "launchd.out.log").write_text(
                "plain text line\n"
                + json.dumps({"event": "fail_start", "ts": "2026-11-17T04:05:00+08:00", "gsy_node": "LAUNCHD-NODE"})
                + "\n",
                encoding="utf-8",
            )
            (root / "usage-summary.md").write_text("今日断开 99 次\n", encoding="utf-8")
            items = collect_vpn(root / "state.json", 12, end, log_dir=root)
        item = items[0]
        self.assertEqual(
            item["title"],
            f"VPN Guard · OK · gsycloud · {node_after} · {ip} · 断开2次 / 不稳定13.4分钟",
        )
        body = item["body"]
        self.assertNotIn("不可用", body)
        self.assertIn("由事件计算", body)
        self.assertIn(f"当前客户端与节点: 光速云（gsycloud） · {node_after} · 出口 IP {ip} · TW", body)
        self.assertIn("超时 1 次，高延迟 1 次", body)
        self.assertIn("超时 2 分钟", body)
        self.assertIn("高延迟 11.4 分钟", body)
        self.assertIn(f"节点 {node_before} 挡住 币安广场", body)
        self.assertIn(f"换到 {node_after}", body)
        self.assertIn("换后四站都通", body)
        self.assertIn("ChatGPT 通", body)
        self.assertIn("币安广场 通", body)
        self.assertIn("切过 Clash: 是", body)
        self.assertIn("重启应用: 否", body)
        self.assertIn("最近动作 rotate_gsy_node_ok", body)
        self.assertNotIn("DECOY-NODE", body)
        self.assertNotIn("LAUNCHD-NODE", body)
        self.assertNotIn("AFTER-SLOT", body)
        self.assertNotIn("99", body)
        self.assertNotIn("999", body)
        meta = item["meta"]
        self.assertEqual(meta["disconnects"], 2)
        self.assertEqual(meta["unstable_minutes"], 13.4)
        self.assertEqual(meta["owner"], "gsycloud")
        self.assertEqual(meta["current_client"], "光速云")
        self.assertEqual(meta["current_node"], node_after)
        self.assertEqual(meta["current_ip"], ip)
        self.assertEqual(meta["site_status"]["ChatGPT"], True)
        self.assertEqual(meta["site_status"]["YouTube"], True)
        self.assertEqual(meta["site_status"]["X"], True)
        self.assertEqual(meta["site_status"]["币安广场"], True)
        self.assertIn("usage.jsonl", meta["sources"])
        self.assertNotIn("vpn_guard.log", meta["sources"])
        self.assertNotIn("launchd.out.log", meta["sources"])
        self.assertNotIn("usage-summary.md", meta["sources"])


if __name__ == "__main__":
    unittest.main()