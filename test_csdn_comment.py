# coding=utf-8
"""测试CSDN评论功能"""

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

from comment.index import comment_on_csdn

def main():
    print("=" * 60)
    print("测试CSDN评论功能")
    print("=" * 60)
    print("\n")
    
    keyword = "前端Vue3与Vue2响应式区别和底层原理"
    
    print(f"搜索关键词: {keyword}")
    print("正在搜索相关热门文章并添加评论...")
    print("=" * 60)
    
    result = comment_on_csdn(
        keyword=keyword,
        comment_limit=3,
        style="口语化"
    )
    
    # 显示结果
    print("\n评论结果：")
    print("=" * 60)
    
    if result.get('success') is None:
        # 如果返回错误信息
        print(f"[错误] {result.get('error', '未知错误')}")
        if 'results' in result:
            print(f"找到文章: {len(result['results'])} 篇")
    else:
        total = result.get('total', 0)
        success_count = result.get('success_count', 0)
        print(f"总计: {total} 篇文章")
        print(f"成功: {success_count} 篇")
        print(f"失败: {total - success_count} 篇")
        print("\n详细信息：")
        
        for r in result.get('results', []):
            article = r.get('article', {})
            title = article.get('title', '未知')
            url = article.get('url', '')
            
            if r.get('success'):
                print(f"  [成功] {title}")
                if r.get('comment'):
                    print(f"    评论: {r['comment']}")
                if url:
                    print(f"    链接: {url}")
            else:
                print(f"  [失败] {title}")
                if r.get('error'):
                    print(f"    错误: {r['error']}")
    
    print("\n")


if __name__ == "__main__":
    main()

