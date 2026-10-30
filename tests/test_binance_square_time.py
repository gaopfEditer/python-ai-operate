# coding=utf-8
"""币安 Square 发帖时间：detail API、ISO 优先于相对文案、快照 post_at。"""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from signals.binance_square.bapi import (
    _ms_to_published_iso,
    apply_detail_time_to_post,
    fetch_content_detail,
)
from signals.binance_square.cards_sync import square_post_to_card
from signals.binance_square.store import (
    _parse_post_time_fields,
    get_content_post_snapshot,
    parse_post_time,
    remember_content_post_snapshot,
    save_state,
)
from signals.binance_square.store import load_state as load_square_state
from signals.binance_square.time_detail import enrich_posts_publish_time_from_detail


class BinanceDetailApiTests(unittest.TestCase):
    def test_ms_to_iso(self):
        iso = _ms_to_published_iso(1793190310000)
        self.assertTrue(iso.endswith("Z"))
        self.assertIn("T", iso)

    @patch("signals.binance_square.bapi.urlrequest.urlopen")
    def test_fetch_content_detail_prefers_first_release(self, mock_open):
        body = {
            "data": {
                "firstReleaseTime": 1793190310000,
                "latestReleaseTime": 1793190312000,
                "createTime": 1791000000000,
                "contentType": 1,
            }
        }

        class _Resp:
            def read(self):
                return json.dumps(body).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        mock_open.return_value = _Resp()
        detail = fetch_content_detail("382153158100032")
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["published_iso"], _ms_to_published_iso(1793190310000))

    def test_apply_detail_sets_created_at(self):
        post = {"content_id": "382153158100032", "time_label": "3小时"}
        detail = {"published_iso": "2026-10-28T12:00:00.000Z"}
        out = apply_detail_time_to_post(post, detail)
        self.assertEqual(out["published_iso"], detail["published_iso"])
        self.assertEqual(out["created_at"], detail["published_iso"])


class ParsePostTimeTests(unittest.TestCase):
    def test_iso_beats_relative_label(self):
        now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
        iso = (now - timedelta(hours=1, minutes=20)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        post = {"published_iso": iso, "time_label": "3小时"}
        dt = _parse_post_time_fields(post, now=now)
        self.assertIsNotNone(dt)
        assert dt is not None
        self.assertAlmostEqual(dt.timestamp(), _parse_post_time_fields({"published_iso": iso}, now=now).timestamp(), places=0)

    def test_relative_only_when_no_iso(self):
        now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
        post = {"time_label": "2小时"}
        dt = _parse_post_time_fields(post, now=now)
        self.assertIsNotNone(dt)
        assert dt is not None
        self.assertAlmostEqual((now - dt).total_seconds(), 7200, delta=60)

    @patch("signals.binance_square.time_detail.fetch_content_detail")
    def test_enrich_from_detail(self, mock_fetch):
        mock_fetch.return_value = {
            "content_id": "382044372111413",
            "published_iso": "2026-10-28T08:30:00.000Z",
        }
        posts = [{"content_id": "382044372111413", "href": "https://www.binance.com/zh-CN/square/post/382044372111413", "time_label": "5小时"}]
        out = enrich_posts_publish_time_from_detail(posts, limit=2, workers=1)
        self.assertEqual(out[0]["published_iso"], "2026-10-28T08:30:00.000Z")
        mock_fetch.assert_called()

    def test_snapshot_post_at_persisted(self):
        st = load_square_state()
        st["content_post_snapshots"] = {}
        save_state(st)
        post = {
            "content_id": "382231620550535",
            "href": "https://www.binance.com/zh-CN/square/post/382231620550535",
            "published_iso": "2026-10-28T09:00:00.000Z",
            "time_label": "1小时",
        }
        remember_content_post_snapshot(post)
        snap = get_content_post_snapshot("382231620550535")
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertEqual(snap.get("published_iso"), post["published_iso"])
        self.assertTrue(snap.get("post_at"))
        st2 = load_square_state()
        self.assertIn("382231620550535", st2.get("content_post_snapshots") or {})

    def test_square_post_to_card_uses_iso(self):
        iso = "2026-10-28T10:00:00.000Z"
        card = square_post_to_card(
            {
                "content_id": "382153158100032",
                "href": "https://www.binance.com/zh-CN/square/post/382153158100032",
                "published_iso": iso,
                "time_label": "8小时",
                "raw": "test",
                "profile_id": "foo",
            }
        )
        dt = parse_post_time({"published_iso": iso, "time_label": "8小时"})
        self.assertIsNotNone(dt)
        self.assertIn("2026", card["created_at"])


if __name__ == "__main__":
    unittest.main()
