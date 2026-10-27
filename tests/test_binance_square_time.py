# coding=utf-8
import unittest
from datetime import datetime, timedelta, timezone

from signals.binance_square.crawl import _chunk_has_known_non_pinned
from signals.binance_square.store import (
    merge_square_post_times_from_prior,
    parse_post_time,
    sanitize_time_label,
)


class TestBinanceSquareTime(unittest.TestCase):
    def test_sanitize_strips_engagement(self):
        raw = "2小时前 · 1.2k 点赞 · 88 评论"
        self.assertEqual(sanitize_time_label(raw), "2小时前")

    def test_sanitize_minutes(self):
        self.assertEqual(sanitize_time_label("15分钟前"), "15分钟前")

    def test_parse_relative(self):
        now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
        post = {"time_label": "2小时前", "published_iso": ""}
        dt = parse_post_time(post)
        self.assertIsNotNone(dt)
        # parse_post_time uses real now; only check label path via _parse_time_label indirectly
        from signals.binance_square.store import _parse_time_label

        dt2 = _parse_time_label("2小时前", now=now)
        self.assertEqual(dt2, now - timedelta(hours=2))

    def test_prefer_iso_over_relative(self):
        now = datetime.now(timezone.utc)
        iso = (now - timedelta(hours=5)).isoformat()
        post = {"time_label": "刚刚", "published_iso": iso}
        dt = parse_post_time(post)
        self.assertIsNotNone(dt)
        self.assertLess(abs((dt - now + timedelta(hours=5)).total_seconds()), 120)

    def test_merge_keeps_prior_time(self):
        old_iso = "2026-05-10T08:00:00+08:00"
        prior = [
            {
                "content_id": "123",
                "href": "https://www.binance.com/zh-CN/square/post/123",
                "published_iso": old_iso,
                "time_label": "5月10日",
            }
        ]
        new_row = [
            {
                "content_id": "123",
                "href": "https://www.binance.com/zh-CN/square/post/123",
                "published_iso": "",
                "time_label": "刚刚",
                "raw": "updated body",
            }
        ]
        out = merge_square_post_times_from_prior(prior, new_row)
        self.assertEqual(out[0]["published_iso"], old_iso)
        self.assertEqual(out[0]["time_label"], "5月10日")

    def test_scroll_stop_skips_pinned_known(self):
        chunk = [
            {"content_id": "1", "is_pinned": True},
            {"content_id": "2", "is_pinned": False},
            {"content_id": "3", "is_pinned": False},
        ]
        known = {"1", "3"}
        self.assertEqual(_chunk_has_known_non_pinned(chunk, known), "3")


if __name__ == "__main__":
    unittest.main()
