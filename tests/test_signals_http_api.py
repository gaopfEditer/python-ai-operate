# coding=utf-8
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestXApiParse(unittest.TestCase):
    def test_twitter_created_to_iso(self):
        from signals.x_api import twitter_created_to_iso

        iso = twitter_created_to_iso("Wed Oct 10 20:19:24 +0000 2018")
        self.assertTrue(iso.startswith("2018-10-10"))

    def test_parse_timeline_fixture(self):
        from signals.x_api import parse_timeline_payload, tweet_node_to_item

        data = json.loads((FIXTURES / "x_list_timeline.json").read_text(encoding="utf-8"))
        items, cursor = parse_timeline_payload(data)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["tweet_id"], "1001")
        self.assertTrue(items[0]["author"].startswith("@"))
        self.assertEqual(cursor, "cursor-bottom-abc")

    def test_fetch_list_timeline_api_mock(self):
        from signals import x_api

        since = datetime(2010, 1, 1, tzinfo=timezone.utc)
        page = json.loads((FIXTURES / "x_list_timeline.json").read_text(encoding="utf-8"))

        class FakeClient:
            def fetch_timeline_page(self, operation, variables):
                assert operation == "ListLatestTweetsTimeline"
                return x_api.parse_timeline_payload(page)

        with mock.patch("signals.x_api.session_ready", return_value=True), mock.patch(
            "signals.x_api.XApiClient", return_value=FakeClient()
        ):
            res = x_api.fetch_list_timeline_api(
                "2088443239435215337",
                since=since,
                max_tweets=10,
            )
        self.assertTrue(res.get("success"), msg=str(res))
        self.assertEqual(res.get("route"), "x_api")
        self.assertGreaterEqual(len(res.get("items") or []), 1)


class TestPublishTime(unittest.TestCase):
    def test_square_iso_beats_relative_label(self):
        from signals.binance_square.store import parse_post_time

        post = {
            "published_iso": "2024-06-01T10:00:00+08:00",
            "time_label": "3小时",
            "raw": "hello",
        }
        dt = parse_post_time(post)
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2024)
        self.assertEqual(dt.month, 6)

    def test_tweet_normalize_strips_relative(self):
        from signals.publish_time import normalize_tweet_item_times

        item = normalize_tweet_item_times(
            {
                "tweet_id": "1",
                "created_at": "Wed Oct 10 20:19:24 +0000 2018",
                "time_label": "5 hours ago",
            }
        )
        self.assertIn("2018", item["created_at"])
        self.assertNotIn("hours", str(item.get("time_label") or ""))


class TestIncrementalStop(unittest.TestCase):
    def test_filter_newest_until_known(self):
        from signals.incremental import filter_newest_until_known, tweet_id_from_item

        items = [
            {"tweet_id": "n1"},
            {"tweet_id": "n2"},
            {"tweet_id": "old1"},
            {"tweet_id": "old2"},
        ]
        known = {"old1", "old2", "n2"}

        def is_known(tid: str) -> bool:
            return tid in known

        kept, stop = filter_newest_until_known(
            items,
            id_fn=tweet_id_from_item,
            is_known=is_known,
            enabled=True,
        )
        self.assertEqual([x["tweet_id"] for x in kept], ["n1"])
        self.assertTrue(stop)

    def test_all_known_page_stops(self):
        from signals.incremental import filter_newest_until_known, tweet_id_from_item

        items = [{"tweet_id": "a"}, {"tweet_id": "b"}]
        kept, stop = filter_newest_until_known(
            items,
            id_fn=tweet_id_from_item,
            is_known=lambda t: True,
            enabled=True,
        )
        self.assertEqual(kept, [])
        self.assertTrue(stop)

    def test_list_api_stops_on_known(self):
        from signals import x_api

        since = datetime(2010, 1, 1, tzinfo=timezone.utc)
        page = json.loads((FIXTURES / "x_list_timeline.json").read_text(encoding="utf-8"))

        class FakeClient:
            def fetch_timeline_page(self, operation, variables):
                return x_api.parse_timeline_payload(page)

        calls = {"n": 0}

        def fake_fetch(operation, variables):
            calls["n"] += 1
            return FakeClient().fetch_timeline_page(operation, variables)

        class FC:
            def fetch_timeline_page(self, operation, variables):
                calls["n"] += 1
                return x_api.parse_timeline_payload(page)

        with mock.patch("signals.x_api.session_ready", return_value=True), mock.patch(
            "signals.x_api.XApiClient", return_value=FC()
        ):
            res = x_api.fetch_list_timeline_api(
                "2088443239435215337",
                since=since,
                max_tweets=10,
                realtime_incremental=True,
                is_known=lambda t: t == "1001",
            )
        self.assertTrue(res.get("success"))
        self.assertEqual(calls["n"], 1)
        ids = [x["tweet_id"] for x in res.get("items") or []]
        self.assertNotIn("1001", ids)


class TestBinanceBapi(unittest.TestCase):
    def test_row_to_post_detail_times(self):
        from signals.binance_square.bapi import row_to_post

        row = {
            "contentId": "303702474979186",
            "firstReleaseTime": 1700000000000,
            "bodyTextOnly": "BTC test",
            "title": "t",
        }
        post = row_to_post(row, profile_slug="demo")
        self.assertEqual(post["content_id"], "303702474979186")
        self.assertIn("2023", post["published_iso"])

    def test_fetch_content_detail_mock(self):
        from signals.binance_square import bapi

        payload = {
            "code": "000000",
            "data": {
                "contentId": "99",
                "firstReleaseTime": 1700000000000,
                "bodyTextOnly": "hello",
            },
        }

        with mock.patch.object(bapi, "_http_json", return_value=payload):
            detail = bapi.fetch_content_detail("99")
        self.assertEqual(detail.get("content_id"), "99")
        self.assertTrue(detail.get("published_iso"))

    def test_time_detail_enrich(self):
        from signals.binance_square.time_detail import enrich_posts_time_from_detail

        posts = [{"content_id": "99", "raw": "x", "time_label": "3小时"}]
        with mock.patch(
            "signals.binance_square.time_detail.fetch_content_detail",
            return_value={"published_iso": "2024-06-01T12:00:00+08:00", "raw": "x"},
        ):
            out = enrich_posts_time_from_detail(posts, limit=2)
        self.assertEqual(out[0].get("published_iso"), "2024-06-01T12:00:00+08:00")


if __name__ == "__main__":
    unittest.main()
