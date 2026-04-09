# coding=utf-8
"""
编排入口：爬取 → AI 提炼话题 → 创作
真实逻辑见 pipeline/index.py
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from pipeline.index import main

__all__ = ["main"]

if __name__ == "__main__":
    main()
