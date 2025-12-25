# coding=utf-8
"""
示例：发布文章到Typecho平台
"""

import sys
import io
from pathlib import Path

# 设置标准输出编码为UTF-8
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from public.index import publish_content

def main():
    print("=" * 60)
    print("发布文章示例")
    print("=" * 60)
    print("\n")
    
    # 示例：发布文章
    content = {
        'title': '前端Vue3与Vue2响应式区别和底层原理',
        'content': '''
# 前端Vue3与Vue2响应式区别和底层原理

## 引言

在前端开发领域，Vue.js 作为一款流行的 JavaScript 框架，因其简洁的 API 和高效的响应式系统而受到广泛欢迎。

本文将深入探讨 Vue2 和 Vue3 在响应式原理上的区别。

## Vue2 的响应式原理

Vue2 使用 Object.defineProperty 实现响应式...

## Vue3 的响应式原理

Vue3 使用 Proxy 实现响应式...

## 总结

Vue3 的响应式系统在性能、兼容性和易用性方面都有明显的优势。
'''
    }
    
    print("正在发布文章到Typecho平台...")
    print("=" * 60)
    
    result = publish_content(
        content=content,
        platform_ids=['typecho'],
        tags='Vue,前端,技术,响应式'
    )
    
    # 显示结果
    print("\n发布结果：")
    print("=" * 60)
    print(f"总计: {result['total']} 个平台")
    print(f"成功: {result['success_count']} 个")
    print(f"失败: {result['total'] - result['success_count']} 个")
    print("\n详细信息：")
    
    for r in result['results']:
        platform_name = r.get('platform_name', r.get('platform', '未知'))
        if r.get('success'):
            print(f"  [成功] {platform_name}: 发布成功")
            if r.get('url'):
                print(f"    文章链接: {r['url']}")
        else:
            print(f"  [失败] {platform_name}: 发布失败")
            if r.get('error'):
                print(f"    错误: {r['error']}")
    
    print("\n")


if __name__ == "__main__":
    main()








