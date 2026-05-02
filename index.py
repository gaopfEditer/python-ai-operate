# coding=utf-8
"""
TrendRadar 主入口
启动所有功能的统一入口
"""

import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from main.scheduler import WorkflowScheduler


def main():
    """主入口函数"""
    parser = argparse.ArgumentParser(description='TrendRadar 主程序')
    parser.add_argument(
        '--mode',
        type=str,
        choices=['full', 'crawler', 'create', 'public', 'comment', 'scheduler'],
        default='scheduler',
        help='执行模式: full(完整工作流), crawler(仅爬取), create(仅创作), public(仅发布), comment(仅评论), scheduler(调度器)'
    )
    parser.add_argument(
        '--crawler',
        action='store_true',
        help='启用爬虫模块'
    )
    parser.add_argument(
        '--create',
        action='store_true',
        help='启用创作模块'
    )
    parser.add_argument(
        '--public',
        action='store_true',
        help='启用发布模块'
    )
    parser.add_argument(
        '--comment',
        action='store_true',
        help='启用评论模块'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🚀 TrendRadar 主程序")
    print("=" * 60)
    print(f"\n执行模式: {args.mode}\n")
    
    if args.mode == 'scheduler':
        # 使用调度器模式
        scheduler = WorkflowScheduler()
        
        # 如果指定了具体模块，则只执行指定模块
        if args.crawler or args.create or args.public or args.comment:
            scheduler.run_full_workflow(
                enable_crawler=args.crawler if args.crawler else False,
                enable_create=args.create if args.create else False,
                enable_public=args.public if args.public else False,
                enable_comment=args.comment if args.comment else False
            )
        else:
            # 默认执行完整工作流
            scheduler.run_full_workflow()
    
    elif args.mode == 'full':
        # 完整工作流
        scheduler = WorkflowScheduler()
        scheduler.run_full_workflow(
            enable_crawler=True,
            enable_create=True,
            enable_public=True,
            enable_comment=False
        )
    
    elif args.mode == 'crawler':
        # 仅爬取
        from crawler.index import main as crawler_main
        crawler_main()
    
    elif args.mode == 'create':
        # 仅创作
        from create.index import main as create_main
        create_main()
    
    elif args.mode == 'public':
        # 仅发布
        from public.index import main as public_main
        public_main()
    
    elif args.mode == 'comment':
        # 仅评论
        from comment.index import main as comment_main
        comment_main()
    
    print("\n✅ 程序执行完成\n")


if __name__ == "__main__":
    main()

