# coding=utf-8
"""
博客阅读器模块
用于阅读和分析博客网站内容
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导出主要功能
from reader.index import analyze_blog, analyze_article, read_blog

__all__ = ['analyze_blog', 'analyze_article', 'read_blog']











