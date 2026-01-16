# coding=utf-8
"""
博客阅读器模块入口
仅作为入口，真实功能在 reader/index.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 导入模块的真实功能
from reader.index import analyze_blog, analyze_article, read_blog

# 导出函数供外部调用
__all__ = ['analyze_blog', 'analyze_article', 'read_blog']

if __name__ == "__main__":
    from reader.index import main
    main()











