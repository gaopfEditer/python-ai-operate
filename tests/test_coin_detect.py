# coding=utf-8
import unittest

from signals.coin_detect import coin_gate_reason, extract_coins_strict, has_listed_coin


class TestCoinDetect(unittest.TestCase):
    def test_dollar_ticker(self):
        self.assertIn("BTC", extract_coins_strict("看多 $BTC 突破"))

    def test_usdt_pair(self):
        coins = extract_coins_strict("ETHUSDT 回踩做多")
        self.assertTrue(any(c == "ETH" for c in coins))

    def test_reject_plain_text(self):
        self.assertFalse(has_listed_coin("今天天气不错，聊聊宏观"))
        self.assertIn("未检测到", coin_gate_reason("宏观叙事没有币"))

    def test_contract_address(self):
        addr = "0x1234567890abcdef1234567890abcdef12345678"
        self.assertTrue(has_listed_coin(f"新盘 {addr}"))


if __name__ == "__main__":
    unittest.main()
