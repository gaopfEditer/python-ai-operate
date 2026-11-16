# coding=utf-8
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.task_os_live_watch_sync import window_for_slot

HKT = ZoneInfo("Asia/Hong_Kong")


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


if __name__ == "__main__":
    unittest.main()