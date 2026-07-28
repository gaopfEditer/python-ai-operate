# coding=utf-8
"""TrendRadar 控制台入口。"""

import sys
from pathlib import Path

# 必须最先处理 Windows GBK 控制台，否则任意 emoji print 都会直接崩
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.stdio_encoding import ensure_utf8_stdio

ensure_utf8_stdio()

from console.app import main

if __name__ == "__main__":
    main()
