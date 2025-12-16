# coding=utf-8
"""
发布模块核心功能
用于将创作的内容发布到各个平台
"""

import sys
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_publish_config() -> Dict:
    """加载发布配置"""
    config_path = project_root / "config" / "config.yaml"
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config.get('publish', {})
    except Exception as e:
        logger.error(f"加载发布配置失败: {e}")
        return {}


def get_platform_config(platform_id: str) -> Optional[Dict]:
    """获取指定平台的配置"""
    config = load_publish_config()
    platforms = config.get('platforms', [])
    for platform in platforms:
        if platform.get('id') == platform_id:
            return platform
    return None


def publish_content(
    content: dict,
    platform_ids: Optional[List[str]] = None,
    tags: Optional[str] = None
) -> Dict:
    """
    发布内容到指定平台
    
    Args:
        content: 内容字典，包含title（标题）、content（正文）等
        platform_ids: 平台ID列表，如果为None则使用配置的默认平台
        tags: 标签（可选，逗号分隔）
        
    Returns:
        包含发布结果的字典
    """
    config = load_publish_config()
    
    if not config.get('enable', True):
        return {
            'success': False,
            'error': '发布功能未启用',
            'results': []
        }
    
    # 确定要发布的平台
    if platform_ids is None:
        default_platforms = config.get('default_platforms', '')
        if default_platforms:
            platform_ids = [p.strip() for p in default_platforms.split(',')]
        else:
            return {
                'success': False,
                'error': '未指定发布平台',
                'results': []
            }
    
    results = []
    
    for platform_id in platform_ids:
        platform_config = get_platform_config(platform_id)
        if not platform_config:
            results.append({
                'platform': platform_id,
                'success': False,
                'error': f'平台配置不存在: {platform_id}'
            })
            continue
        
        if not platform_config.get('enabled', True):
            results.append({
                'platform': platform_id,
                'success': False,
                'error': f'平台未启用: {platform_id}'
            })
            continue
        
        platform_type = platform_config.get('type', '')
        platform_name = platform_config.get('name', platform_id)
        
        logger.info(f"正在发布到平台: {platform_name} ({platform_id})")
        
        # 根据平台类型选择发布器
        if platform_type == 'typecho':
            from public.platforms.typecho_publisher import TypechoPublisher
            
            publisher = TypechoPublisher(
                login_url=platform_config.get('login_url', ''),
                write_url=platform_config.get('write_url', ''),
                username=platform_config.get('username', ''),
                password=platform_config.get('password', ''),
                headless=config.get('headless', False)
            )
            
            result = publisher.publish(
                title=content.get('title', ''),
                content=content.get('content', ''),
                tags=tags or content.get('tags', '')
            )
            
            result['platform'] = platform_id
            result['platform_name'] = platform_name
            results.append(result)
        else:
            results.append({
                'platform': platform_id,
                'platform_name': platform_name,
                'success': False,
                'error': f'不支持的平台类型: {platform_type}'
            })
    
    # 统计结果
    success_count = sum(1 for r in results if r.get('success', False))
    total_count = len(results)
    
    return {
        'success': success_count > 0,
        'total': total_count,
        'success_count': success_count,
        'results': results
    }


def list_platforms() -> List[Dict]:
    """列出所有可用的发布平台"""
    config = load_publish_config()
    platforms = config.get('platforms', [])
    return [
        {
            'id': p.get('id'),
            'name': p.get('name'),
            'enabled': p.get('enabled', True),
            'type': p.get('type')
        }
        for p in platforms
    ]


def main():
    """
    发布功能主入口
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='TrendRadar 发布模块')
    parser.add_argument('--file', type=str, help='文章文件路径（Markdown格式）')
    parser.add_argument('--title', type=str, help='文章标题')
    parser.add_argument('--content', type=str, help='文章内容')
    parser.add_argument('--platforms', type=str, help='平台ID列表，用逗号分隔（如：typecho）')
    parser.add_argument('--tags', type=str, help='标签，用逗号分隔')
    parser.add_argument('--list', action='store_true', help='列出所有可用平台')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("TrendRadar 发布模块")
    print("=" * 60)
    
    # 列出平台
    if args.list:
        print("\n可用发布平台：")
        platforms = list_platforms()
        for p in platforms:
            status = "已启用" if p['enabled'] else "已禁用"
            print(f"  • {p['name']} ({p['id']}) - {status}")
        print("\n")
        return
    
    # 准备内容
    content = {}
    
    if args.file:
        # 从文件读取
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"\n[错误] 文件不存在: {args.file}\n")
            return
        
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        # 尝试解析Markdown，提取标题和内容
        lines = file_content.split('\n')
        if lines[0].startswith('#'):
            content['title'] = lines[0].lstrip('#').strip()
            content['content'] = '\n'.join(lines[1:]).strip()
        else:
            content['title'] = file_path.stem
            content['content'] = file_content
    elif args.title and args.content:
        content['title'] = args.title
        content['content'] = args.content
    else:
        print("\n[错误] 请提供文章内容（使用--file或--title+--content）\n")
        parser.print_help()
        return
    
    # 确定平台
    platform_ids = None
    if args.platforms:
        platform_ids = [p.strip() for p in args.platforms.split(',')]
    
    # 发布
    print(f"\n正在发布文章: {content['title']}")
    print("=" * 60)
    
    result = publish_content(
        content=content,
        platform_ids=platform_ids,
        tags=args.tags
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
            print(f"  ✓ {platform_name}: 发布成功")
            if r.get('url'):
                print(f"    文章链接: {r['url']}")
        else:
            print(f"  ✗ {platform_name}: 发布失败")
            if r.get('error'):
                print(f"    错误: {r['error']}")
    
    print("\n")


if __name__ == "__main__":
    main()

