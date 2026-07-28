# coding=utf-8
"""Windows 控制台编码兼容：避免 GBK 打印 emoji 导致崩溃。"""

from __future__ import annotations

import builtins
import logging
import sys

_PATCHED = False

_EMOJI_MAP = {
    "\u274c": "[X]",
    "\u2705": "[OK]",
    "\u26a0\ufe0f": "[!]",
    "\u26a0": "[!]",
    "\U0001f680": "[GO]",
    "\U0001f4ca": "[STAT]",
    "\U0001f4c4": "[FILE]",
    "\U0001f4dd": "[NOTE]",
    "\u2022": "-",
}


def sanitize_for_console(text: object) -> str:
    s = "" if text is None else str(text)
    for src, dst in _EMOJI_MAP.items():
        s = s.replace(src, dst)
    # 再清一遍所有非 GBK 可编码字符（保守）
    enc = getattr(sys.stdout, "encoding", None) or "gbk"
    if hasattr(sys.stdout, "_wrapped"):
        enc = getattr(sys.stdout._wrapped, "encoding", None) or enc
    try:
        s.encode(enc)
        return s
    except Exception:
        try:
            return s.encode(enc, errors="replace").decode(enc, errors="replace")
        except Exception:
            return s.encode("ascii", errors="replace").decode("ascii")


class _SafeTextIO:
    def __init__(self, wrapped):
        object.__setattr__(self, "_wrapped", wrapped)
        object.__setattr__(self, "_trendradar_safe", True)

    @property
    def encoding(self):
        return getattr(self._wrapped, "encoding", "utf-8")

    def write(self, s):
        if isinstance(s, str):
            s = sanitize_for_console(s)
        try:
            return self._wrapped.write(s)
        except UnicodeEncodeError:
            try:
                raw = sanitize_for_console(s).encode(self.encoding or "gbk", errors="replace")
                if hasattr(self._wrapped, "buffer"):
                    return self._wrapped.buffer.write(raw)
            except Exception:
                return 0
        except Exception:
            return 0

    def writelines(self, lines):
        for line in lines:
            self.write(line)

    def flush(self):
        try:
            return self._wrapped.flush()
        except Exception:
            return None

    def reconfigure(self, *args, **kwargs):
        fn = getattr(self._wrapped, "reconfigure", None)
        if callable(fn):
            return fn(*args, **kwargs)
        return None

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


class _SafeLogHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = sanitize_for_console(self.format(record))
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


def ensure_utf8_stdio() -> None:
    global _PATCHED

    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            try:
                if hasattr(stream, "reconfigure"):
                    stream.reconfigure(errors="replace")
            except Exception:
                pass

    if not getattr(sys.stdout, "_trendradar_safe", False):
        sys.stdout = _SafeTextIO(sys.stdout)
    if not getattr(sys.stderr, "_trendradar_safe", False):
        sys.stderr = _SafeTextIO(sys.stderr)

    # 接管 root logging，避免 logger 绕过 print 直接写崩
    root = logging.getLogger()
    if not getattr(root, "_trendradar_safe_log", False):
        for h in list(root.handlers):
            root.removeHandler(h)
        handler = _SafeLogHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        root._trendradar_safe_log = True  # type: ignore[attr-defined]

    if _PATCHED:
        return

    _orig_print = builtins.print

    def _safe_print(*args, **kwargs):
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        file = kwargs.get("file", sys.stdout)
        flush = kwargs.get("flush", False)
        try:
            text = sep.join(sanitize_for_console(a) for a in args) + end
            write = getattr(file, "write", None)
            if callable(write):
                write(text)
                if flush and hasattr(file, "flush"):
                    file.flush()
            else:
                _orig_print(text, end="", file=file, flush=flush)
        except Exception:
            try:
                _orig_print(
                    sanitize_for_console(" ".join(str(a) for a in args)),
                    file=sys.__stdout__,
                )
            except Exception:
                pass

    builtins.print = _safe_print
    _PATCHED = True


def safe_print(*args, **kwargs) -> None:
    ensure_utf8_stdio()
    print(*args, **kwargs)
