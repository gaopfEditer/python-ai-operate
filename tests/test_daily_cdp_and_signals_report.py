# coding=utf-8
"""daily_cdp_and_signals_report：过滤规则与 HKT 日窗。"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

_SPEC = importlib.util.spec_from_file_location(
    "daily_cdp_and_signals_report",
    SCRIPTS / "daily_cdp_and_signals_report.py",
)
rpt = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(rpt)


class TestDirectionCoinFilter(unittest.TestCase):
    def test_keep_coin_and_long_short(self):
        self.assertTrue(rpt.is_directional_coin_signal({"coins": ["BTC"], "direction": "long"}))
        self.assertTrue(rpt.is_directional_coin_signal({"coins": ["ETH"], "direction": "short"}))
        self.assertTrue(rpt.is_directional_coin_signal({"coins": ["SOL"], "direction": "做多"}))
        self.assertTrue(rpt.is_directional_coin_signal({"coins": ["DOGE"], "direction": "看空"}))
        self.assertTrue(rpt.is_directional_coin_signal({"coins": ["BTC", "ETH"], "direction": "买入"}))

    def test_drop_missing_coin_or_direction(self):
        self.assertFalse(rpt.is_directional_coin_signal({"coins": ["BTC"], "direction": "unknown"}))
        self.assertFalse(rpt.is_directional_coin_signal({"coins": ["BTC"], "direction": "watch"}))
        self.assertFalse(rpt.is_directional_coin_signal({"coins": ["BTC"], "direction": "flat"}))
        self.assertFalse(rpt.is_directional_coin_signal({"coins": ["BTC"], "direction": "观望"}))
        self.assertFalse(rpt.is_directional_coin_signal({"coins": [], "direction": "long"}))
        self.assertFalse(rpt.is_directional_coin_signal({"coins": [""], "direction": "short"}))
        self.assertFalse(rpt.is_directional_coin_signal({"coins": [], "direction": "unknown"}))
        self.assertFalse(rpt.is_directional_coin_signal({}))
        self.assertFalse(rpt.is_directional_coin_signal(None))
        self.assertFalse(rpt.is_directional_coin_signal("long"))

    def test_agrees_with_project_is_trade_signal_when_importable(self):
        try:
            from signals.labels import is_trade_signal
        except Exception:
            self.skipTest("signals.labels 不可导入")
        samples = [
            {"coins": ["BTC"], "direction": "long"},
            {"coins": ["ETH"], "direction": "做空"},
            {"coins": ["BTC"], "direction": "unknown"},
            {"coins": [], "direction": "long"},
            {"coins": ["DOGE"], "direction": "watch"},
            {},
        ]
        for sig in samples:
            self.assertEqual(
                rpt.is_directional_coin_signal(sig),
                is_trade_signal(sig),
                msg=sig,
            )


class TestHktDayWindow(unittest.TestCase):
    def setUp(self):
        self.day = date(2026, 11, 12)
        self.start, self.end, self.start_ts, self.end_ts = rpt.day_window(self.day)

    def test_window_bounds(self):
        self.assertEqual(self.start.isoformat(timespec="seconds"), "2026-11-12T00:00:00+08:00")
        self.assertEqual(self.end.isoformat(timespec="seconds"), "2026-11-13T00:00:00+08:00")
        self.assertEqual(self.start_ts, 1794412800)
        self.assertEqual(self.end_ts, 1794499200)

    def test_inclusive_start_exclusive_end(self):
        self.assertTrue(rpt.in_window(rpt.parse_datetime("2026-11-12T00:00:00+08:00"), self.start, self.end))
        self.assertTrue(rpt.in_window(rpt.parse_datetime("2026-11-12T23:59:59.999+08:00"), self.start, self.end))
        self.assertFalse(rpt.in_window(rpt.parse_datetime("2026-11-11T23:59:59+08:00"), self.start, self.end))
        self.assertFalse(rpt.in_window(rpt.parse_datetime("2026-11-13T00:00:00+08:00"), self.start, self.end))

    def test_utc_z_converted(self):
        # 2026-11-11T16:00:00Z == 2026-11-12 00:00 HKT
        self.assertTrue(rpt.in_window(rpt.parse_datetime("2026-11-11T16:00:00Z"), self.start, self.end))
        self.assertTrue(rpt.in_window(rpt.parse_datetime("2026-11-11T16:00:00.000Z"), self.start, self.end))
        # 2026-11-12T16:00:00Z == 2026-11-13 00:00 HKT，落在次日
        self.assertFalse(rpt.in_window(rpt.parse_datetime("2026-11-12T16:00:00Z"), self.start, self.end))

    def test_naive_treated_as_hkt_not_utc(self):
        # naive 00:00 视为 HKT 午夜，属于当日
        self.assertTrue(rpt.in_window(rpt.parse_datetime("2026-11-12T00:00:00"), self.start, self.end))
        # 若误按 UTC 解释，11-11T16:00:00 naive 会等于当日 HKT 午夜；按 HKT 则属于 11-11
        self.assertFalse(rpt.in_window(rpt.parse_datetime("2026-11-11T16:00:00"), self.start, self.end))
        self.assertTrue(rpt.in_window(rpt.parse_datetime("2026-11-12T16:00:00"), self.start, self.end))

    def test_filter_published_uses_created_at_ts(self):
        cards = [
            {"created_at_ts": self.start_ts, "list_id": "user:a", "signal": {"coins": ["BTC"], "direction": "long"}},
            {"created_at_ts": self.end_ts, "list_id": "user:a", "signal": {"coins": ["BTC"], "direction": "long"}},
            {"created_at_ts": self.start_ts - 1, "list_id": "binance:x", "signal": {}},
        ]
        got = rpt.filter_published(cards, self.start_ts, self.end_ts)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["created_at_ts"], self.start_ts)


class TestCdpLogAndCardSummarize(unittest.TestCase):
    def test_summarize_cdp_success_and_fail_reasons(self):
        records = [
            {"event": "run_start", "ts": "2026-11-12T00:04:05+08:00", "platforms": ["gate", "okx"]},
            {
                "event": "platform_ok",
                "platform": "okx",
                "platform_name": "OKX",
                "ts": "2026-11-12T00:07:48+08:00",
                "message": "发布成功",
            },
            {
                "event": "platform_fail",
                "platform": "gate",
                "platform_name": "Gate 广场",
                "ts": "2026-11-12T00:06:49+08:00",
                "failure_category": "selector",
                "step": "find_editor",
                "message": "无法写入正文编辑区",
            },
            {
                "event": "platform_fail",
                "platform": "gate",
                "platform_name": "Gate 广场",
                "ts": "2026-11-12T09:47:05+08:00",
                "failure_category": "selector",
                "step": "find_editor",
                "message": "无法写入正文编辑区",
            },
            {"event": "run_end", "ts": "2026-11-12T00:09:58+08:00", "success_count": 1, "total": 2},
        ]
        cdp = rpt.summarize_cdp(records)
        self.assertEqual(cdp["total"], 3)
        self.assertEqual(cdp["success"], 1)
        self.assertEqual(cdp["fail"], 2)
        self.assertEqual(cdp["runs"], 1)
        self.assertEqual(cdp["by_platform"]["okx"]["success"], 1)
        self.assertEqual(cdp["by_platform"]["gate"]["fail"], 2)
        self.assertEqual(
            cdp["by_platform"]["gate"]["fail_reasons"],
            {"selector: 无法写入正文编辑区": 2},
        )

    def test_load_publish_records_filters_hkt_day(self):
        day = date(2026, 11, 12)
        start, end, _, _ = rpt.day_window(day)
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            (log_dir / "publish_2026-11-12.log").write_text(
                json.dumps(
                    {
                        "event": "platform_ok",
                        "platform": "okx",
                        "ts": "2026-11-12T01:00:00+08:00",
                        "message": "发布成功",
                    },
                    ensure_ascii=False,
                )
                + "\n"
                + json.dumps(
                    {
                        "event": "platform_ok",
                        "platform": "okx",
                        "ts": "2026-11-13T00:00:00+08:00",
                        "message": "次日不应计入",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            records, gaps, files = rpt.load_publish_records(log_dir, day, start, end)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["platform"], "okx")
        self.assertEqual(files, ["publish_2026-11-12.log"])
        self.assertEqual(gaps, [])

    def test_summarize_cards_keeps_and_splits_platforms(self):
        cards = [
            {
                "list_id": "user:luge517",
                "user_handle": "luge517",
                "source_mode": "kol_realtime",
                "text": "做多 BTC",
                "signal": {"coins": ["BTC"], "direction": "long"},
            },
            {
                "list_id": "user:luge517",
                "user_handle": "luge517",
                "source_mode": "kol_realtime",
                "text": "喜欢看？",
                "signal": {"coins": [], "direction": "unknown"},
            },
            {
                "list_id": "binance:yanchibit",
                "user_handle": "yanchibit",
                "source_mode": "binance_square",
                "text": "#BTC 日内行情分析",
                "signal": {"coins": ["BTC"], "direction": "unknown"},
            },
        ]
        out = rpt.summarize_cards(cards)
        self.assertEqual(out["twitter"]["raw"], 2)
        self.assertEqual(out["twitter"]["kept"], 1)
        self.assertEqual(out["twitter"]["dropped"], 1)
        self.assertEqual(out["binance"]["raw"], 1)
        self.assertEqual(out["binance"]["kept"], 0)
        self.assertEqual(out["binance"]["dropped"], 1)
        self.assertEqual(out["twitter"]["kept_by_handle"], {"luge517": 1})




class TestHoursWindow(unittest.TestCase):
    def test_bounds_and_span(self):
        end = datetime(2026, 11, 12, 20, 0, tzinfo=rpt.HKT)
        start, finish, start_ts, end_ts = rpt.hours_window(12, end=end)
        self.assertEqual(start.isoformat(timespec="seconds"), "2026-11-12T08:00:00+08:00")
        self.assertEqual(finish.isoformat(timespec="seconds"), "2026-11-12T20:00:00+08:00")
        self.assertEqual(start_ts, int(start.timestamp()))
        self.assertEqual(end_ts, int(finish.timestamp()))

    def test_crosses_midnight(self):
        end = datetime(2026, 11, 12, 8, 0, tzinfo=rpt.HKT)
        start, finish, _, _ = rpt.hours_window(12, end=end)
        self.assertEqual(start.isoformat(timespec="seconds"), "2026-11-11T20:00:00+08:00")
        self.assertEqual(rpt.dates_touching_window(start, finish), [date(2026, 11, 11), date(2026, 11, 12)])

    def test_load_publish_records_across_midnight(self):
        end = datetime(2026, 11, 12, 8, 0, tzinfo=rpt.HKT)
        start, finish, _, _ = rpt.hours_window(12, end=end)
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            (log_dir / "publish_2026-11-11.log").write_text(
                json.dumps({"event": "platform_ok", "platform": "okx", "ts": "2026-11-11T21:00:00+08:00"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (log_dir / "publish_2026-11-12.log").write_text(
                json.dumps({"event": "platform_ok", "platform": "bitget", "ts": "2026-11-12T07:00:00+08:00"}, ensure_ascii=False)
                + "\n"
                + json.dumps({"event": "platform_ok", "platform": "gate", "ts": "2026-11-12T09:00:00+08:00"}, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            records, gaps, files = rpt.load_publish_records(log_dir, date(2026, 11, 12), start, finish)
        plats = sorted(r["platform"] for r in records)
        self.assertEqual(plats, ["bitget", "okx"])
        self.assertIn("publish_2026-11-11.log", files)
        self.assertIn("publish_2026-11-12.log", files)
        self.assertEqual(gaps, [])


if __name__ == "__main__":
    unittest.main()
