# coding=utf-8
"""Cards API 实时推送门禁与 payload 单测。"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from unittest.mock import patch

from signals.push import (
    build_cards_payload,
    card_allows_cards_push,
    card_is_today,
    cards_api_message_id,
    cards_api_source_for_card,
    push_card_if_needed,
    select_cards_for_cards_push,
)
from signals.store import is_pushed, load_state, mark_pushed, save_state


def _today_card(**extra):
    now = datetime.now(timezone.utc).astimezone()
    base = {
        "tweet_id": "123456",
        "author": "@trader",
        "text": "long BTC",
        "created_at": now.isoformat(timespec="seconds"),
        "source_mode": "list_realtime",
        "signal": {"coins": ["BTC"], "direction": "long", "has_trade_signal": True},
    }
    base.update(extra)
    return base


class CardsPushGateTests(unittest.TestCase):
    def test_trade_signal_required(self):
        card = _today_card(signal={"coins": [], "direction": "long"})
        ok, reason = card_allows_cards_push(card)
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_coin_or_direction")

    def test_backfill_blocked(self):
        card = _today_card(source_mode="user_backfill")
        ok, reason = card_allows_cards_push(card)
        self.assertFalse(ok)
        self.assertEqual(reason, "backfill_source")

    def test_binance_requires_realtime_flag(self):
        card = _today_card(source_mode="binance_square", cards_push_allowed=False)
        ok, reason = card_allows_cards_push(card)
        self.assertFalse(ok)
        self.assertEqual(reason, "binance_not_realtime_ingest")

    def test_binance_realtime_allowed(self):
        card = _today_card(source_mode="binance_square", cards_push_allowed=True)
        ok, reason = card_allows_cards_push(card)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_not_today_blocked(self):
        card = _today_card(created_at="2020-01-01T12:00:00+08:00")
        self.assertFalse(card_is_today(card))
        ok, reason = card_allows_cards_push(card)
        self.assertFalse(ok)
        self.assertEqual(reason, "not_today")

    def test_select_filters(self):
        ok_card = _today_card(tweet_id="a")
        bad = _today_card(tweet_id="b", source_mode="user_backfill")
        chosen, rejected = select_cards_for_cards_push([ok_card, bad])
        self.assertEqual(len(chosen), 1)
        self.assertEqual(chosen[0]["tweet_id"], "a")
        self.assertEqual(len(rejected), 1)


class CardsPayloadTests(unittest.TestCase):
    def test_message_id_prefix(self):
        x = _today_card(source_mode="list_realtime", tweet_id="99")
        bs = _today_card(source_mode="binance_square", tweet_id="88", cards_push_allowed=True)
        self.assertEqual(cards_api_message_id(x), "x-99")
        self.assertEqual(cards_api_message_id(bs), "bs-88")

    def test_source_per_platform(self):
        bs = _today_card(source_mode="binance_square", cards_push_allowed=True)
        self.assertEqual(cards_api_source_for_card(bs), "binance_square")
        payload = build_cards_payload(bs)
        self.assertEqual(payload["source"], "binance_square")
        self.assertLessEqual(len(payload["sourceType"]), 32)


class PushIdempotencyTests(unittest.TestCase):
    def test_only_success_marks_pushed(self):
        state = load_state()
        state["pushed_tweet_ids"] = []
        state["push_log"] = []
        save_state(state)
        mark_pushed(["tid1"], status="skipped_non_trade")
        self.assertFalse(is_pushed("tid1"))
        mark_pushed(["tid1"], status="ok")
        self.assertTrue(is_pushed("tid1"))

    @patch("signals.push.post_card")
    def test_push_card_skipped_non_trade_not_marked(self, mock_post):
        mock_post.return_value = {"success": True, "response": {"card": {"id": 1}}}
        state = load_state()
        state["pushed_tweet_ids"] = []
        save_state(state)
        card = _today_card(signal={"coins": [], "direction": "unknown"})
        r = push_card_if_needed(
            card,
            cfg={
                "cards_api": {"enabled": True, "base_url": "http://127.0.0.1:1"},
                "default_channel": {"channelId": "api", "channelName": "t"},
                "channels": {},
            },
        )
        self.assertTrue(r.get("skipped"))
        self.assertEqual(r.get("reason"), "missing_coin_or_direction")
        self.assertFalse(is_pushed("123456"))
        mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
