# coding=utf-8
import importlib.util
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "cdp_common_testmod",
    _root / "public" / "platforms" / "cdp_common.py",
)
_cdp = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_cdp)
multiline_content_preserved = _cdp.multiline_content_preserved
prepare_x_compose_text = _cdp.prepare_x_compose_text
x_editor_line_structure_ok = _cdp.x_editor_line_structure_ok


class TestXComposeText(unittest.TestCase):
    def test_prepare_preserves_blank_lines(self):
        raw = "第一行\n\n第三行"
        out = prepare_x_compose_text(raw)
        self.assertEqual(out, "第一行\n\n第三行")

    def test_multiline_rejects_collapsed(self):
        exp = "行一\n行二"
        got = "行一行二"
        self.assertFalse(multiline_content_preserved(got, exp))

    def test_multiline_accepts_inner_breaks(self):
        exp = "行一\n行二"
        got = "行一\n行二"
        self.assertTrue(multiline_content_preserved(got, exp))

    def test_structure_ok_requires_line_count(self):
        exp = "A\nB\nC"
        self.assertTrue(x_editor_line_structure_ok("A\nB\nC", exp))
        self.assertFalse(x_editor_line_structure_ok("ABC", exp))
        self.assertFalse(x_editor_line_structure_ok("A\nB", exp))


if __name__ == "__main__":
    unittest.main()
