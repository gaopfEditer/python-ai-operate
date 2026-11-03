# coding=utf-8
import errno
import socket
import unittest
import urllib.error
import urllib.request
from unittest import mock

from signals.http_proxy import (
    parse_vpn_proxy_list,
    should_use_vpn_proxy,
    urlopen,
)


class TestHttpProxyHelpers(unittest.TestCase):
    def test_should_skip_localhost(self):
        self.assertFalse(should_use_vpn_proxy("http://127.0.0.1:9223/json"))
        self.assertFalse(should_use_vpn_proxy("http://localhost:8787/api"))
        self.assertTrue(should_use_vpn_proxy("https://x.com/i/api/graphql/foo/Bar"))

    def test_parse_env_override(self):
        with mock.patch.dict("os.environ", {"AI_OPERATE_HTTP_PROXIES": "http://a:1,http://b:2"}):
            self.assertEqual(parse_vpn_proxy_list(), ["http://a:1", "http://b:2"])


class TestHttpProxyFallback(unittest.TestCase):
    def test_falls_back_on_connection_refused(self):
        req = urllib.request.Request("https://example.com/test")
        refused = urllib.error.URLError(ConnectionRefusedError(errno.ECONNREFUSED, "refused"))
        ok_resp = object()

        open_calls = []

        def fake_opener(proxy):
            def open_fn(r, timeout=None):
                open_calls.append(proxy)
                if proxy == "http://127.0.0.1:7890":
                    raise refused
                return ok_resp

            opener = mock.Mock()
            opener.open = open_fn
            return opener

        with mock.patch("signals.http_proxy.parse_vpn_proxy_list", return_value=["http://127.0.0.1:7890", "http://127.0.0.1:7891"]), mock.patch(
            "signals.http_proxy._proxy_opener", side_effect=fake_opener
        ):
            out = urlopen(req, timeout=5)
        self.assertIs(out, ok_resp)
        self.assertEqual(open_calls, ["http://127.0.0.1:7890", "http://127.0.0.1:7891"])

    def test_local_uses_direct_opener(self):
        req = urllib.request.Request("http://127.0.0.1:9223/json/version")
        sentinel = object()
        direct = mock.Mock()
        direct.open.return_value = sentinel
        with mock.patch("signals.http_proxy._direct_opener", return_value=direct):
            out = urlopen(req, timeout=3)
        self.assertIs(out, sentinel)
        direct.open.assert_called_once()


if __name__ == "__main__":
    unittest.main()
