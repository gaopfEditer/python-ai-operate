# coding=utf-8
"""规则与防抖单测（假数据，不依赖外网）。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realtime_info.filters import (
    rule_kol_prefilter,
    rule_liq,
    rule_oi_funding_oi_surge,
    rule_oi_funding_squeeze,
    rule_onchain,
    rule_tv,
    rule_unlock,
)
from realtime_info.filters.debounce import pass_debounce
from realtime_info.collectors.tv_webhook import handle_tv_webhook
from realtime_info.storage.db import init_db, list_events


class RuleTests(unittest.TestCase):
    def test_tv_tf(self):
        ok, _ = rule_tv({"symbol": "BTCUSDT", "timeframe": "4H"})
        self.assertTrue(ok)
        bad, reason = rule_tv({"symbol": "BTCUSDT", "timeframe": "1m"})
        self.assertFalse(bad)
        self.assertIn("timeframe", reason)

    def test_oi_surge(self):
        ok, _ = rule_oi_funding_oi_surge(
            {"oi_change_pct": 10, "price_change_pct": 0.5}
        )
        self.assertTrue(ok)
        bad, _ = rule_oi_funding_oi_surge(
            {"oi_change_pct": 10, "price_change_pct": 3}
        )
        self.assertFalse(bad)

    def test_funding_squeeze(self):
        ok, _ = rule_oi_funding_squeeze(
            {
                "funding_rates": [-0.0006, -0.0007],
                "broke_24h_low": False,
            }
        )
        self.assertTrue(ok)

    def test_onchain_major(self):
        ok, _ = rule_onchain({"symbol": "ETH", "usd_value": 6_000_000})
        self.assertTrue(ok)
        bad, _ = rule_onchain({"symbol": "ETH", "usd_value": 1000})
        self.assertFalse(bad)

    def test_liq(self):
        ok, _ = rule_liq({"liq_15m_usd": 60_000_000})
        self.assertTrue(ok)
        ok2, _ = rule_liq({"heatmap_proximity_pct": 1.0})
        self.assertTrue(ok2)

    def test_unlock(self):
        ok, _ = rule_unlock({"unlock_usd": 8_000_000, "circulating_pct": 3})
        self.assertTrue(ok)

    def test_kol_prefilter(self):
        self.assertTrue(rule_kol_prefilter("准备做多 $BTC 突破"))
        self.assertFalse(rule_kol_prefilter("今天天气不错"))


class PipelineTests(unittest.TestCase):
    def test_tv_ingest_and_debounce(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "t.db"
            init_db(db)
            r1 = handle_tv_webhook(
                {
                    "symbol": "ETHUSDT",
                    "timeframe": "1H",
                    "side": "short",
                    "structure": "spring",
                    "message": "test",
                },
                skip_llm=True,
                db_path=db,
            )
            self.assertTrue(r1.get("ok"), r1)
            r2 = handle_tv_webhook(
                {
                    "symbol": "ETHUSDT",
                    "timeframe": "1H",
                    "side": "short",
                    "structure": "spring",
                    "message": "test again",
                },
                skip_llm=True,
                db_path=db,
            )
            self.assertFalse(r2.get("ok"))
            items = list_events(status="pending", db_path=db)
            self.assertEqual(len(items), 1)

    def test_pass_debounce_marks(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "d.db"
            init_db(db)
            ok1, _ = pass_debounce("tv", "x:y", hours=6, db_path=db)
            self.assertTrue(ok1)
            ok2, _ = pass_debounce("tv", "x:y", hours=6, db_path=db)
            self.assertFalse(ok2)


if __name__ == "__main__":
    unittest.main()
