# coding=utf-8
"""
博客阅读器使用示例
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from reader import analyze_blog, analyze_article, read_blog


def example_read_blog():
    """示例：仅读取博客文章"""
    print("=" * 60)
    print("示例：读取博客文章")
    print("=" * 60)
    
    # 替换为你要分析的博客 URL
    blog_url = "https://example.com/blog"
    
    articles = read_blog(blog_url, max_articles=5)
    
    print(f"\n成功读取 {len(articles)} 篇文章：\n")
    for i, article in enumerate(articles, 1):
        print(f"{i}. {article.get('title', '未知标题')}")
        print(f"   URL: {article.get('url', '')}")
        if article.get('content'):
            preview = article['content'][:100].replace('\n', ' ')
            print(f"   内容预览: {preview}...")
        print()


def example_analyze_article():
    """示例：分析单篇文章"""
    print("=" * 60)
    print("示例：分析单篇文章")
    print("=" * 60)
    
    # 示例文章数据
    article = {
        'title': 'Python 异步编程入门',
        'content': """
        Python 异步编程是现代 Python 开发中的重要技能。本文介绍了 asyncio 库的基本使用方法。
        
        异步编程的核心是使用 async/await 关键字。通过 async def 定义异步函数，使用 await 等待异步操作完成。
        
        异步编程的优势在于可以高效处理 I/O 密集型任务，避免线程切换的开销。
        
        在实际应用中，我们需要理解事件循环、协程、任务等概念，才能更好地使用异步编程。
        """,
        'url': 'https://example.com/article/1'
    }
    
    analysis = analyze_article(article)
    
    if analysis['success']:
        print(f"\n文章标题: {article['title']}")
        print(f"\n摘要:")
        print(analysis['summary'])
        print(f"\n质量评估:")
        for key, value in analysis['quality'].items():
            print(f"  {key}: {value}/10")
        print(f"\n完整分析:")
        print(analysis.get('full_analysis', '')[:500] + "...")
    else:
        print(f"分析失败: {analysis.get('error', '未知错误')}")


def example_analyze_blog():
    """示例：分析整个博客"""
    print("=" * 60)
    print("示例：分析整个博客")
    print("=" * 60)
    
    # 替换为你要分析的博客 URL
    blog_url = "https://example.com/blog"
    
    print(f"\n正在分析博客: {blog_url}")
    print("这可能需要一些时间，请耐心等待...\n")
    
    result = analyze_blog(blog_url, max_articles=5)
    
    if result['success']:
        print(f"\n[成功] 分析完成")
        print(f"博客地址: {result['blog_url']}")
        print(f"分析文章数: {result['articles_count']}")
        
        print("\n--- 博主定位 ---")
        profile = result.get('blogger_profile', {})
        if profile.get('full_analysis'):
            print(profile['full_analysis'])
        
        print("\n--- 整体质量评估 ---")
        quality = result.get('overall_quality', {})
        if quality:
            for key, value in quality.items():
                print(f"{key}: {value}/10")
        else:
            print("（质量评估信息在完整分析中）")
        
        print("\n--- 文章分析详情（前3篇） ---")
        for i, article in enumerate(result.get('articles', [])[:3], 1):
            print(f"\n{i}. {article.get('title', '未知标题')}")
            analysis = article.get('analysis', {})
            if analysis.get('summary'):
                print(f"   摘要: {analysis['summary'][:100]}...")
            if analysis.get('quality'):
                print(f"   质量: {analysis['quality']}")
    else:
        print(f"\n[失败] {result.get('error', '未知错误')}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='博客阅读器使用示例')
    parser.add_argument('--example', type=str, choices=['read', 'analyze-article', 'analyze-blog'], 
                       default='read', help='运行哪个示例')
    
    args = parser.parse_args()
    
    if args.example == 'read':
        example_read_blog()
    elif args.example == 'analyze-article':
        example_analyze_article()
    elif args.example == 'analyze-blog':
        example_analyze_blog()

