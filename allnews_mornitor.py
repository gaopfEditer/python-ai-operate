# coding=utf-8
"""AllNews Monitor 入口（对标 console.py）。"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.stdio_encoding import ensure_utf8_stdio

ensure_utf8_stdio()

from allnews_mornitor.app import main

if __name__ == "__main__":
    main()
