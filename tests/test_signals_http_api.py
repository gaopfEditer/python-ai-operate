# coding=utf-8
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestFetchSourceLabeling(unittest.TestCase):
    def test_normalize_and_square_mapping(self):
        from signals.fetch_source import (
            FETCH_CDP,
            FETCH_COOKIE_API,
            fetch_source_for_item,
            normalize_fetch_source,
            square_post_source_to_fetch_source,
        )

        self.assertEqual(normalize_fetch_source("x_api"), FETCH_COOKIE_API)
        self.assertEqual(normalize_fetch_source("cdp"), FETCH_CDP)
        self.assertEqual(square_post_source_to_fetch_source("bapi_profile"), FETCH_COOKIE_API)
        self.assertEqual(square_post_source_to_fetch_source("profile_cdp"), FETCH_CDP)
        post = {"source": "profile_cdp", "content_id": "1"}
        self.assertEqual(fetch_source_for_item(post, ""), FETCH_CDP)

    def test_binance_enrich_card_uses_yaml_profile_name(self):
        from signals.push import enrich_card_channel

        card = {
            "author": "@square-creator-446e63a9fd9ef",
            "user_handle": "square-creator-446e63a9fd9ef",
            "list_id": "binance:square-creator-446e63a9fd9ef",
            "source_mode": "binance_square",
            "created_at": "2026-11-01T12:00:00+08:00",
        }
        out = enrich_card_channel(card, {})
        name = (out.get("channel") or {}).get("channelName") or ""
        self.assertNotIn("未映射", name)
        self.assertEqual(name, "格里芬院长")

    def test_square_post_to_card_carries_fetch_source(self):
        from signals.binance_square.cards_sync import square_post_to_card
        from signals.fetch_source import FETCH_COOKIE_API

        card = square_post_to_card(
            {
                "content_id": "9001",
                "href": "https://www.binance.com/en/square/post/9001",
                "raw": "hi",
                "source": "bapi_profile",
                "fetch_source": FETCH_COOKIE_API,
            }
        )
        self.assertEqual(card.get("fetch_source"), FETCH_COOKIE_API)

    def test_append_fetch_route_log_redacts_secrets(self):
        import tempfile
        from pathlib import Path

        from signals import fetch_source as fs_mod

        with tempfile.TemporaryDirectory() as td:
            fs_mod._LOG_PATH = Path(td) / "routes.jsonl"
            fs_mod.append_fetch_route_log(
                {
                    "platform": "x_list",
                    "cookie_api": {"ok": False, "reason": "auth_token=supersecret123456"},
                    "final_fetch_source": fs_mod.FETCH_CDP,
                    "sample_count": 0,
                }
            )
            line = fs_mod._LOG_PATH.read_text(encoding="utf-8")
            self.assertNotIn("supersecret", line)
            self.assertIn("redacted", line)


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


class TestBinanceRealtime(unittest.TestCase):
    def test_parse_profile_posts_fixture(self):
        from signals.binance_square.bapi import _parse_list_payload

        data = json.loads((FIXTURES / "binance_profile_posts.json").read_text(encoding="utf-8"))
        posts = _parse_list_payload(data)
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0]["content_id"], "9001")
        self.assertIn("2023", posts[0].get("published_iso") or "")

    def test_resolve_uid_fixture(self):
        from signals.binance_square import bapi

        payload = json.loads((FIXTURES / "binance_user_client.json").read_text(encoding="utf-8"))
        with mock.patch.object(bapi, "_http_json", return_value=payload):
            uid = bapi.resolve_square_uid("yanchibit")
        self.assertEqual(uid, "TestSquareUid123")

    def test_incremental_skips_known_pinned(self):
        from signals.incremental import filter_newest_until_known, square_id_from_post

        items = [
            {"content_id": "8001", "is_pinned": True},
            {"content_id": "8009"},
            {"content_id": "8008"},
        ]

        kept, stop = filter_newest_until_known(
            items,
            id_fn=square_id_from_post,
            is_known=lambda c: c in ("8001", "8008"),
            enabled=True,
            skip_known_if_pinned=True,
        )
        self.assertEqual([x["content_id"] for x in kept], ["8009"])
        self.assertTrue(stop)


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


class TestCdpSessionLoader(unittest.TestCase):
    def test_merge_supplemental_headers_keeps_cdp_cookies(self):
        from signals.binance_square.session import merge_supplemental_headers

        primary = {
            "cookies": {"csrftoken": "from_cdp"},
            "headers": {"csrftoken": "from_cdp"},
            "cookie_header": "csrftoken=from_cdp",
        }
        file_sess = {
            "cookies": {"csrftoken": "from_file"},
            "headers": {"device-info": "fp-token", "csrftoken": "from_file"},
            "cookie_header": "csrftoken=from_file",
        }
        merged = merge_supplemental_headers(primary, file_sess)
        self.assertEqual(merged["cookies"]["csrftoken"], "from_cdp")
        self.assertEqual(merged["headers"]["device-info"], "fp-token")

    def test_pull_binance_from_cdp_mock(self):
        from signals import cdp_session_loader as loader

        fake_pages = [{"webSocketDebuggerUrl": "ws://fake"}]

        class FakeClient:
            def __init__(self, ws):
                pass

            def call(self, method, params=None):
                if method == "Network.getCookies":
                    return {
                        "cookies": [
                            {"name": "csrftoken", "value": "abc"},
                            {"name": "bnc-uuid", "value": "u1"},
                        ]
                    }
                return {}

            def close(self):
                pass

        with mock.patch.object(loader, "_http_json_on_host", return_value=fake_pages), mock.patch(
            "allnews_mornitor.cdp_browser._CdpClient", FakeClient
        ):
            sess, err = loader.pull_binance_session_from_cdp("127.0.0.1:9223")
        self.assertEqual(err, "")
        self.assertIn("csrftoken=abc", sess.get("cookie_header") or "")

    def test_refresh_falls_back_to_file_when_cdp_fails(self):
        from signals import cdp_session_loader as loader
        from signals.binance_square.session import load_binance_session

        logs: list = []
        with mock.patch.object(loader, "pull_binance_session_from_cdp", return_value=(None, "no chrome")), mock.patch.object(
            loader, "_cdp_disabled", return_value=False
        ), mock.patch(
            "signals.binance_square.session.load_binance_session",
            return_value={"cookies": {"csrftoken": "f"}, "headers": {}, "cookie_header": "csrftoken=f"},
        ):
            loader.clear_session_cache()
            out = loader.refresh_binance_session_from_cdp(
                debugger_url="127.0.0.1:9223", progress=logs.append
            )
        self.assertTrue(out)
        self.assertTrue(any("回退" in x for x in logs))


class TestAnalyzeTimeout(unittest.TestCase):
    def test_analyze_times_out_and_uses_heuristic(self):
        import time
        from signals.analyze import analyze_tweet_signal

        def slow_ai(**kwargs):
            time.sleep(2.0)
            return {"has_trade_signal": False, "provider": "slow", "coins": [], "direction": "unknown"}

        with mock.patch(
            "signals.analyze.analyze_tweet_signal_ai_only", side_effect=slow_ai
        ):
            sig = analyze_tweet_signal(text="做多 BTC", author="t", timeout_sec=0.3)
        self.assertTrue(str(sig.get("provider") or "").startswith("timeout:"))
        self.assertIn("BTC", sig.get("coins") or [])

    def test_skip_llm_for_non_trade_text(self):
        from signals.analyze import analyze_tweet_signal, should_skip_ai_llm

        self.assertTrue(should_skip_ai_llm("今天天气不错", has_images=False))
        self.assertFalse(should_skip_ai_llm("做多 BTC 突破", has_images=False))
        with mock.patch("signals.analyze.analyze_tweet_signal_ai_only") as gen:
            gen.return_value = {"provider": "ai", "has_trade_signal": False, "coins": []}
            sig = analyze_tweet_signal(text="随手转发一条动态", author="x")
        gen.assert_not_called()
        self.assertEqual(sig.get("provider"), "heuristic:skip_llm")

    def test_deferred_parse_default(self):
        from signals.signal_parse_queue import llm_parse_is_deferred, pending_signal, signal_parse_pending

        self.assertTrue(llm_parse_is_deferred())
        self.assertTrue(signal_parse_pending(pending_signal()))
        self.assertFalse(signal_parse_pending({"provider": "deepseek", "has_trade_signal": True}))

    def test_merge_captured_query_ids(self):
        from signals.x_cdp_graphql import merge_captured_query_ids

        q = merge_captured_query_ids({"ListLatestTweetsTimeline": "FreshId123"})
        self.assertEqual(q["ListLatestTweetsTimeline"], "FreshId123")
        self.assertTrue(q.get("UserTweets"))

    def test_merge_captured_query_ids_later_layer_wins(self):
        from signals.x_cdp_graphql import merge_captured_query_ids
        from signals.x_session import DEFAULT_QUERY_IDS

        stale = DEFAULT_QUERY_IDS["UserByScreenName"]
        fresh = "AMIBMjtxEEATh4z8V9GtRg"
        q = merge_captured_query_ids(
            {"UserByScreenName": stale},
            {"UserByScreenName": fresh},
        )
        self.assertEqual(q["UserByScreenName"], fresh)

    def test_merge_x_supplemental_primary_wins_over_stale_file(self):
        from signals.x_session import DEFAULT_QUERY_IDS, merge_x_supplemental

        primary = {
            "auth_token": "a",
            "ct0": "c",
            "query_ids": {"UserByScreenName": "AMIBMjtxEEATh4z8V9GtRg"},
            "query_ids_captured": ["UserByScreenName"],
        }
        supplemental = {
            "auth_token": "a",
            "ct0": "c",
            "query_ids": {"UserByScreenName": DEFAULT_QUERY_IDS["UserByScreenName"]},
        }
        merged = merge_x_supplemental(primary, supplemental)
        self.assertEqual(merged["query_ids"]["UserByScreenName"], "AMIBMjtxEEATh4z8V9GtRg")

    def test_is_x_query_not_found_error(self):
        from signals.x_api import _is_x_query_not_found_error

        err = RuntimeError(
            'UserByScreenName HTTP 404: {"errors":[{"message":"Query not found","code":0}]}'
        )
        self.assertTrue(_is_x_query_not_found_error(err))
        self.assertFalse(_is_x_query_not_found_error(RuntimeError("UserByScreenName HTTP 401")))

    def test_invalidate_cached_x_query_id(self):
        import tempfile

        from signals import cdp_session_loader as loader
        loader.clear_session_cache()
        loader.patch_cached_x_session(
            {
                "auth_token": "a",
                "ct0": "c",
                "query_ids": {
                    "UserByScreenName": "dead",
                    "UserTweets": "keep",
                },
                "query_ids_captured": ["UserByScreenName", "UserTweets"],
                "cookie_header": "auth_token=a; ct0=c",
            }
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x_api_session.json"
            path.write_text(
                json.dumps(
                    {
                        "auth_token": "a",
                        "ct0": "c",
                        "query_ids": {"UserByScreenName": "dead", "UserTweets": "keep"},
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch("signals.x_session.session_file_path", return_value=path):
                loader.invalidate_cached_x_query_id("UserByScreenName")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("UserByScreenName", data.get("query_ids", {}))
            self.assertEqual(data["query_ids"]["UserTweets"], "keep")
        sess = loader.get_cached_x_session()
        self.assertNotIn("UserByScreenName", sess.get("query_ids", {}))
        self.assertEqual(sess.get("query_ids_captured"), ["UserTweets"])

    def test_refresh_session_query_ids_force_and_invalidate(self):
        from signals import cdp_session_loader as loader
        from signals.x_api import XApiClient, _refresh_session_query_ids

        loader.clear_session_cache()
        base = {
            "auth_token": "a",
            "ct0": "c",
            "query_ids": {"UserByScreenName": "dead"},
            "cookie_header": "auth_token=a; ct0=c",
        }
        client = XApiClient(session=dict(base))
        refreshed = {
            **base,
            "query_ids": {"UserByScreenName": "AMIBMjtxEEATh4z8V9GtRg"},
            "query_ids_captured": ["UserByScreenName"],
        }
        with mock.patch(
            "signals.x_api.invalidate_cached_x_query_id"
        ) as inv, mock.patch(
            "signals.x_api.ensure_x_graphql_query_ids", return_value=refreshed
        ) as ensure:
            ok = _refresh_session_query_ids(
                client,
                ("UserByScreenName",),
                invalidate_op="UserByScreenName",
            )
        self.assertTrue(ok)
        inv.assert_called_once_with("UserByScreenName")
        ensure.assert_called_once()
        self.assertEqual(
            client.session["query_ids"]["UserByScreenName"],
            "AMIBMjtxEEATh4z8V9GtRg",
        )

    def test_fetch_user_timeline_retries_once_on_query_not_found(self):
        from signals import x_api

        since = datetime(2010, 1, 1, tzinfo=timezone.utc)
        page = json.loads((FIXTURES / "x_list_timeline.json").read_text(encoding="utf-8"))
        uid_calls = {"n": 0}
        refresh_calls = {"n": 0}

        class FakeClient:
            session = {}

            def replace_session(self, session):
                self.session = dict(session)

            def user_id_by_screen_name(self, screen_name):
                uid_calls["n"] += 1
                if uid_calls["n"] == 1:
                    raise RuntimeError(
                        'UserByScreenName HTTP 404: {"errors":[{"message":"Query not found"}]}'
                    )
                return "9001"

            def fetch_timeline_page(self, operation, variables):
                return x_api.parse_timeline_payload(page)

        def fake_refresh(client, operations, **kwargs):
            refresh_calls["n"] += 1
            client.replace_session(
                {
                    "auth_token": "a",
                    "ct0": "c",
                    "query_ids": {"UserByScreenName": "fresh", "UserTweets": "fresh2"},
                    "cookie_header": "auth_token=a; ct0=c",
                }
            )
            return True

        with mock.patch("signals.x_api.session_ready", return_value=True), mock.patch(
            "signals.x_api.ensure_x_graphql_query_ids",
            return_value={"auth_token": "a", "ct0": "c"},
        ), mock.patch("signals.x_api.XApiClient", return_value=FakeClient()), mock.patch(
            "signals.x_api._refresh_session_query_ids", side_effect=fake_refresh
        ):
            res = x_api.fetch_user_timeline_api("elonmusk", since=since, max_tweets=5)
        self.assertTrue(res.get("success"))
        self.assertEqual(uid_calls["n"], 2)
        self.assertEqual(refresh_calls["n"], 1)

    def test_parse_graphql_operation_from_url(self):
        from signals.x_cdp_graphql import parse_graphql_operation_from_url

        qid, op = parse_graphql_operation_from_url(
            "https://api.x.com/graphql/RlZzktZY_9wJynoepm8ZsA/ListLatestTweetsTimeline?variables=%7B%7D"
        )
        self.assertEqual(op, "ListLatestTweetsTimeline")
        self.assertEqual(qid, "RlZzktZY_9wJynoepm8ZsA")
        qid2, op2 = parse_graphql_operation_from_url(
            "https://x.com/i/api/graphql/AbCdEf/UserTweets"
        )
        self.assertEqual(op2, "UserTweets")
        self.assertEqual(qid2, "AbCdEf")

    def test_network_capture_parses_api_x_com(self):
        from signals.x_cdp_graphql import _CdpPageGraphqlCapture

        cap = _CdpPageGraphqlCapture.__new__(_CdpPageGraphqlCapture)
        cap.query_ids = {}
        cap.authorization = ""
        cap._on_network_request(
            {
                "url": "https://api.x.com/graphql/LiveQueryId123/ListLatestTweetsTimeline",
                "headers": {"authorization": "Bearer token123"},
            }
        )
        self.assertEqual(
            cap.query_ids.get("ListLatestTweetsTimeline"),
            "LiveQueryId123",
        )
        self.assertEqual(cap.authorization, "Bearer token123")

    def test_ensure_x_graphql_query_ids_skips_when_fresh(self):
        from signals import cdp_session_loader as loader
        from signals.x_cdp_graphql import operation_query_id_is_builtin_only

        self.assertFalse(
            operation_query_id_is_builtin_only(
                {"ListLatestTweetsTimeline": "LiveCapturedId"},
                "ListLatestTweetsTimeline",
            )
        )
        loader.clear_session_cache()
        loader.patch_cached_x_session(
            {
                "auth_token": "a",
                "ct0": "c",
                "query_ids": {"ListLatestTweetsTimeline": "LiveCapturedId"},
                "cookie_header": "auth_token=a; ct0=c",
            }
        )
        with mock.patch.object(loader, "_collect_cookies_from_cdp") as ck:
            out = loader.ensure_x_graphql_query_ids(("ListLatestTweetsTimeline",))
        ck.assert_not_called()
        self.assertEqual(
            out.get("query_ids", {}).get("ListLatestTweetsTimeline"),
            "LiveCapturedId",
        )

    def test_fetch_list_calls_ensure_query_ids(self):
        from signals import x_api

        since = datetime(2010, 1, 1, tzinfo=timezone.utc)
        page = json.loads((FIXTURES / "x_list_timeline.json").read_text(encoding="utf-8"))

        class FakeClient:
            def fetch_timeline_page(self, operation, variables):
                return x_api.parse_timeline_payload(page)

        with mock.patch("signals.x_api.session_ready", return_value=True), mock.patch(
            "signals.x_api.ensure_x_graphql_query_ids", return_value={"auth_token": "a", "ct0": "b"}
        ) as ensure, mock.patch("signals.x_api.XApiClient", return_value=FakeClient()):
            res = x_api.fetch_list_timeline_api("2088443239435215337", since=since, max_tweets=5)
        self.assertTrue(res.get("success"))
        ensure.assert_called_once()


if __name__ == "__main__":
    unittest.main()
