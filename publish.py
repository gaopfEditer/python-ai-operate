# coding=utf-8
"""
发布模块入口
仅作为入口，真实功能在 public/index.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 导入模块的真实功能
from public.index import main, publish_content

# 导出函数供外部调用
__all__ = ['main', 'publish_content']

if __name__ == "__main__":
    main()

