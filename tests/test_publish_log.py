# coding=utf-8
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from public import publish_log


class TestPublishLogHelpers(unittest.TestCase):
    def test_classify_failure_category(self):
        self.assertEqual(
            publish_log.classify_failure_category("Read timed out"),
            "timeout",
        )
        self.assertEqual(
            publish_log.classify_failure_category("未找到推文编辑框"),
            "selector",
        )
        self.assertEqual(
            publish_log.classify_failure_category("CDP 连接失败: refused"),
            "network",
        )
        self.assertEqual(
            publish_log.classify_failure_category("请登录 X"),
            "login",
        )

    def test_resolve_failed_step(self):
        self.assertEqual(
            publish_log.resolve_failed_step("未找到推文编辑框，请确认已登录 X", ["compose"]),
            "find_editor",
        )
        self.assertEqual(
            publish_log.resolve_failed_step("CDP 连接失败", []),
            "connect_cdp",
        )
        self.assertEqual(
            publish_log.resolve_failed_step("unknown", ["compose", "editor"]),
            "after:editor",
        )

    def test_sanitize_secrets(self):
        msg = publish_log.sanitize_message("password=supersecret token bearer abcdefghijklmnop")
        self.assertNotIn("supersecret", msg)
        self.assertIn("redacted", msg)

    def test_enrich_failure_diagnostics(self):
        class _Drv:
            current_url = "https://x.com/compose/post?token=abc"

        row = publish_log.enrich_failure_diagnostics(
            {
                "success": False,
                "error": "未找到或无法点击发帖按钮",
                "steps": ["compose", "editor", "text"],
            },
            driver=_Drv(),
        )
        self.assertEqual(row["failed_step"], "click_post")
        self.assertEqual(row["failure_category"], "selector")
        self.assertIn("x.com/compose/post", row["last_url"])
        self.assertNotIn("token=abc", row["last_url"])

    def test_log_platform_fail_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(publish_log, "_LOG_DIR", root / "publish_logs"):
                with mock.patch.object(publish_log, "_PROJECT_ROOT", root):
                    publish_log.set_trace_context(job_id="job123", content_ref="body:abc")
                    publish_log.log_platform_result(
                        platform_id="x",
                        platform_name="X / Twitter",
                        result={
                            "success": False,
                            "error": "未找到推文编辑框",
                            "steps": ["compose"],
                        },
                        elapsed_ms=1200,
                    )
                    path = publish_log.default_log_file()
                    self.assertTrue(path.exists())
                    line = path.read_text(encoding="utf-8").strip().splitlines()[-1]
                    rec = json.loads(line)
                    self.assertEqual(rec["event"], "platform_fail")
                    self.assertEqual(rec["platform"], "x")
                    self.assertEqual(rec["job_id"], "job123")
                    self.assertEqual(rec["step"], "find_editor")
                    self.assertEqual(rec["failure_category"], "selector")


if __name__ == "__main__":
    unittest.main()
