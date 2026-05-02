# coding=utf-8
"""
评论模块核心功能
用于使用账号对重点关注文章进行评论
"""

import sys
import time
import logging
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.ai_client import get_qwen_client

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_comment(
    article: dict, 
    platform: str = "通用", 
    comment_type: str = "正面",
    style: str = "口语化"
) -> dict:
    """
    基于文章内容生成评论
    
    Args:
        article: 文章数据字典，包含标题、内容等
        platform: 目标平台名称
        comment_type: 评论类型（正面、提问、分享等）
        
    Returns:
        包含生成评论的字典
    """
    client = get_qwen_client()
    
    # 构建用户输入
    user_input = f"""
目标平台：{platform}
评论类型：{comment_type}

文章信息：
标题：{article.get('title', '')}
内容：{article.get('content', '')[:500]}  # 限制长度避免token过多
"""
    
    # 使用全局提示词和主流程提示词
    system_prompt_path = project_root / "comment" / "global_prompt.txt"
    main_prompt_path = project_root / "comment" / "main" / "main_prompt.txt"
    
    system_prompt = ""
    if system_prompt_path.exists():
        with open(system_prompt_path, 'r', encoding='utf-8') as f:
            system_prompt += f.read() + "\n\n"
    
    if main_prompt_path.exists():
        with open(main_prompt_path, 'r', encoding='utf-8') as f:
            system_prompt += f.read()
    
    # 添加评论生成的具体要求
    style_instruction = ""
    if style == "口语化":
        style_instruction = """
5. 使用口语化表达，像真实用户在评论一样
6. 直指问题核心，不要绕弯子
7. 可以适当使用网络用语和表情符号
8. 语气自然、亲切，不要太正式
"""
    elif style == "专业":
        style_instruction = """
5. 使用专业术语，表达严谨
6. 逻辑清晰，论证充分
"""
    
    system_prompt += f"""
请生成一条{comment_type}类型的评论，要求：
1. 评论内容真实、有价值，避免垃圾评论
2. 符合{platform}平台的评论规范
3. 评论长度适中（通常50-200字）
4. 能够引发讨论或表达观点
{style_instruction}
"""
    
    # 调用千问生成评论
    result = client.generate(
        prompt=user_input,
        system_prompt=system_prompt,
        temperature=0.8,  # 评论可以稍微随机一些
        max_tokens=500
    )
    
    return result


def comment_on_csdn(keyword: str, comment_limit: int = 3, style: str = "口语化") -> dict:
    """
    在CSDN上搜索文章并添加评论
    
    Args:
        keyword: 搜索关键词
        comment_limit: 评论文章数量限制
        style: 评论风格（口语化、专业）
        
    Returns:
        包含评论结果的字典
    """
    import yaml
    
    # 加载配置
    config_path = project_root / "config" / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    comment_config = config.get('comment', {})
    csdn_config = None
    for platform in comment_config.get('platforms', []):
        if platform.get('id') == 'csdn':
            csdn_config = platform
            break
    
    if not csdn_config or not csdn_config.get('enabled'):
        return {
            'success': False,
            'error': 'CSDN平台未配置或未启用',
            'results': []
        }
    
    username = csdn_config.get('username', '')
    password = csdn_config.get('password', '')
    
    if not username or not password:
        return {
            'success': False,
            'error': 'CSDN账号未配置',
            'results': []
        }
    
    from comment.platforms.csdn_commenter import CSDNCommenter
    
    commenter = CSDNCommenter(
        username=username,
        password=password,
        headless=comment_config.get('headless', False)
    )
    
    # 初始化浏览器
    if not commenter._init_driver():
        return {
            'success': False,
            'error': '浏览器驱动初始化失败',
            'total': 0,
            'success_count': 0,
            'results': []
        }
    
    # 登录
    if not commenter._login():
        commenter.driver.quit()
        return {
            'success': False,
            'error': '登录失败',
            'total': 0,
            'success_count': 0,
            'results': []
        }
    
    # 搜索文章
    articles = commenter.search_articles(keyword, limit=comment_limit)
    
    if not articles:
        commenter.driver.quit()
        return {
            'success': False,
            'error': '未找到相关文章',
            'total': 0,
            'success_count': 0,
            'results': []
        }
    
    # 为每篇文章生成评论并发布
    results = []
    client = get_qwen_client()
    
    for article in articles:
        logger.info(f"正在为文章生成评论: {article['title']}")
        
        # 获取文章内容（如果URL可用，可以访问获取更多内容）
        article_content = article.get('content', '')
        if not article_content:
            article_content = f"关于{keyword}的技术文章"
        
        # 生成评论
        comment_result = generate_comment(
            article={
                'title': article['title'],
                'content': article_content
            },
            platform='CSDN',
            comment_type='正面',
            style=style
        )
        
        if not comment_result.get('success'):
            results.append({
                'article': article,
                'success': False,
                'error': f"生成评论失败: {comment_result.get('error', '')}",
                'comment': ''
            })
            continue
        
        comment_text = comment_result.get('content', '').strip()
        
        # 发布评论
        publish_result = commenter.add_comment(article['url'], comment_text)
        publish_result['article'] = article
        publish_result['comment'] = comment_text
        results.append(publish_result)
        
        time.sleep(2)  # 评论间隔
    
    commenter.driver.quit()
    
    success_count = sum(1 for r in results if r.get('success', False))
    
    return {
        'success': success_count > 0,
        'total': len(results),
        'success_count': success_count,
        'results': results
    }


def main():
    """
    评论功能主入口
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='TrendRadar 评论模块')
    parser.add_argument('--keyword', type=str, help='搜索关键词')
    parser.add_argument('--platform', type=str, default='csdn', help='平台ID')
    parser.add_argument('--limit', type=int, default=3, help='评论文章数量')
    parser.add_argument('--style', type=str, default='口语化', help='评论风格（口语化、专业）')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("TrendRadar 评论模块")
    print("=" * 60)
    
    client = get_qwen_client()
    if not client.enable:
        print("\n[警告] 千问模型未启用或API Key未配置")
        print("请在 config/config.yaml 中配置 ai.qwen.api_key")
        print("\n")
        return
    
    print("\n[成功] 千问模型已就绪")
    print("\n功能说明：")
    print("  • 账号管理和登录")
    print("  • 重点关注文章筛选")
    print("  • 自动评论功能（使用通义千问生成评论）")
    print("  • 评论内容生成")
    print("  • 多平台评论支持（CSDN、微博、知乎、贴吧等）")
    print("\n")
    
    # 如果提供了关键词，执行搜索和评论
    if args.keyword:
        if args.platform == 'csdn':
            print(f"正在搜索并评论CSDN文章: {args.keyword}")
            print("=" * 60)
            
            result = comment_on_csdn(
                keyword=args.keyword,
                comment_limit=args.limit,
                style=args.style
            )
            
            print("\n评论结果：")
            print("=" * 60)
            print(f"总计: {result['total']} 篇文章")
            print(f"成功: {result['success_count']} 篇")
            print(f"失败: {result['total'] - result['success_count']} 篇")
            print("\n详细信息：")
            
            for r in result['results']:
                article = r.get('article', {})
                title = article.get('title', '未知')
                if r.get('success'):
                    print(f"  [成功] {title}")
                    if r.get('comment'):
                        print(f"    评论: {r['comment'][:50]}...")
                else:
                    print(f"  [失败] {title}")
                    if r.get('error'):
                        print(f"    错误: {r['error']}")
            
            print("\n")
        else:
            print(f"暂不支持平台: {args.platform}")
    else:
        print("提示：使用 --keyword 参数可以搜索并评论文章")
        print("示例：python comment.py --keyword 'Vue3响应式原理' --limit 3 --style 口语化")
        print("\n")


if __name__ == "__main__":
    main()

