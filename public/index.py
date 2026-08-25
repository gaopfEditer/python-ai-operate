# coding=utf-8
"""
发布模块核心功能
用于将创作的内容发布到各个平台
"""

import logging
import re
import sys
import yaml
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
    tags: Optional[str] = None,
    use_cdp: bool = False,
    debugger_url: Optional[str] = None,
    media_paths: Optional[List[str]] = None,
    submit: bool = True,
) -> Dict:
    """
    发布内容到指定平台

    Args:
        content: 内容字典，包含 title / content；社交平台可无 title
        platform_ids: 平台ID列表，如果为None则使用配置的默认平台
        tags: 标签（可选，逗号分隔）
        use_cdp: 是否复用已启动的 Chrome CDP 调试会话
        debugger_url: CDP 地址，如 127.0.0.1:9222；为空则读配置
        media_paths: 本地图片/视频绝对路径列表
        submit: False 时只填内容不点发布（干跑）
    """
    config = load_publish_config()
    if use_cdp and not debugger_url:
        debugger_url = (
            config.get("debugger_url")
            or config.get("cdp_debugger_url")
            or "127.0.0.1:9222"
        )

    if not config.get('enable', True):
        return {
            'success': False,
            'error': '发布功能未启用',
            'results': []
        }

    if platform_ids is None:
        default_platforms = config.get('default_platforms', '')
        if default_platforms:
            platform_ids = [p.strip() for p in default_platforms.split(',') if p.strip()]
        else:
            return {
                'success': False,
                'error': '未指定发布平台',
                'results': []
            }

    media = list(media_paths or content.get("media_paths") or [])
    results = []
    shared_driver = None
    needs_cdp = use_cdp or any(
        (get_platform_config(pid) or {}).get("type")
        in ("x", "twitter", "binance_square", "okx", "bitget")
        for pid in platform_ids
    )
    if needs_cdp and debugger_url:
        try:
            from public.platforms.cdp_common import connect_cdp

            shared_driver = connect_cdp(debugger_url)
        except Exception as e:
            logger.warning("共享 CDP 连接失败，将按平台各自连接: %s", e)
            shared_driver = None

    try:
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

            platform_type = (platform_config.get('type') or '').lower()
            platform_name = platform_config.get('name', platform_id)

            logger.info(f"正在发布到平台: {platform_name} ({platform_id})")

            if platform_type == 'typecho':
                from public.platforms.typecho_publisher import TypechoPublisher

                publisher = TypechoPublisher(
                    login_url=platform_config.get('login_url', ''),
                    write_url=platform_config.get('write_url', ''),
                    username=platform_config.get('username', ''),
                    password=platform_config.get('password', ''),
                    headless=config.get('headless', False),
                    debugger_url=debugger_url if use_cdp else None,
                )
                result = publisher.publish(
                    title=content.get('title', ''),
                    content=content.get('content', ''),
                    tags=tags or content.get('tags', '')
                )
            elif platform_type in ('x', 'twitter'):
                from public.platforms.x_publisher import XPublisher

                publisher = XPublisher(
                    debugger_url=debugger_url or "127.0.0.1:9222",
                    compose_url=platform_config.get(
                        'compose_url', 'https://x.com/compose/post'
                    ),
                    close_driver=False,
                )
                if shared_driver is not None:
                    publisher.driver = shared_driver
                result = publisher.publish(
                    text=content.get('content', '') or content.get('text', ''),
                    media_paths=media,
                    submit=submit,
                    title=content.get('title', ''),
                )
            elif platform_type in ('binance_square', 'binance', 'square', 'okx', 'bitget'):
                from public.platforms.binance_square_publisher import (
                    BinanceSquarePublisher,
                )

                publisher = BinanceSquarePublisher(
                    debugger_url=debugger_url or "127.0.0.1:9222",
                    square_url=platform_config.get(
                        'square_url',
                        'https://www.binance.com/zh-CN/square',
                    ),
                    close_driver=False,
                    wait_sec=float(platform_config.get('wait_sec', 8) or 8),
                    media_upload_wait=float(
                        platform_config.get('media_upload_wait', 25) or 25
                    ),
                    platform_id=platform_id,
                    platform_name=platform_name,
                )
                if shared_driver is not None:
                    publisher.driver = shared_driver
                result = publisher.publish(
                    text=content.get('content', '') or content.get('text', ''),
                    media_paths=media,
                    submit=submit,
                    title=content.get('title', ''),
                )
            else:
                result = {
                    'success': False,
                    'error': f'不支持的平台类型: {platform_type}',
                }

            result['platform'] = platform_id
            result['platform_name'] = platform_name
            results.append(result)
    finally:
        # 不 quit 共享 driver，保留用户已登录的 Chrome
        shared_driver = None

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
    parser.add_argument('--platforms', type=str, help='平台ID列表，用逗号分隔（如：x,binance_square）')
    parser.add_argument('--tags', type=str, help='标签，用逗号分隔')
    parser.add_argument('--media', type=str, action='append', default=[], help='媒体路径，可多次指定')
    parser.add_argument('--cdp', type=str, default='', help='CDP 地址，如 127.0.0.1:9222')
    parser.add_argument('--dry-run', action='store_true', help='只填内容不点发布')
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
    elif args.title or args.content:
        content['title'] = args.title or ''
        content['content'] = args.content or ''
    elif args.media:
        content['title'] = ''
        content['content'] = ''
    else:
        print("\n[错误] 请提供正文/媒体（--file 或 --content / --media）\n")
        parser.print_help()
        return

    platform_ids = None
    if args.platforms:
        platform_ids = [p.strip() for p in args.platforms.split(',') if p.strip()]

    media = []
    for m in args.media or []:
        media.extend([p.strip() for p in re.split(r'[,;\n]+', m) if p.strip()])

    print(f"\n正在发布: {content.get('title') or '(无标题)'}")
    print("=" * 60)

    result = publish_content(
        content=content,
        platform_ids=platform_ids,
        tags=args.tags,
        use_cdp=bool(args.cdp) or True,
        debugger_url=args.cdp or None,
        media_paths=media,
        submit=not args.dry_run,
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

