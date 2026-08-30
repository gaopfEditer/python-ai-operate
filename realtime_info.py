# coding=utf-8
"""实时资讯入口（Webhook + 轮询）。"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.stdio_encoding import ensure_utf8_stdio

ensure_utf8_stdio()

from realtime_info.app import main

if __name__ == "__main__":
    raise SystemExit(main())
