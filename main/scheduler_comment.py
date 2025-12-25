# coding=utf-8
"""
爬取和评论调度器
用于爬取热点数据并在相关文章下进行评论
"""

import sys
import time
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from crawler.index import main as crawler_main
from comment.index import comment_on_csdn


class CrawlerCommentScheduler:
    """爬取和评论调度器"""
    
    def __init__(self):
        self.project_root = project_root
        self.execution_log = []
    
    def log(self, message: str, level: str = "INFO"):
        """记录执行日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        self.execution_log.append(log_entry)
        print(log_entry)
    
    def run_crawler(self) -> Dict:
        """
        执行爬虫模块
        
        Returns:
            包含执行结果的字典
        """
        self.log("开始执行爬虫模块...")
        try:
            crawler_main()
            self.log("爬虫模块执行完成", "SUCCESS")
            return {'success': True, 'message': '爬虫执行成功'}
        except Exception as e:
            self.log(f"爬虫模块执行失败: {e}", "ERROR")
            return {'success': False, 'error': str(e)}
    
    def run_comment(self, keyword: str, comment_limit: int = 3, style: str = "口语化") -> Dict:
        """
        执行评论模块
        
        Args:
            keyword: 搜索关键词
            comment_limit: 评论文章数量限制
            style: 评论风格
            
        Returns:
            包含评论结果的字典
        """
        self.log(f"开始执行评论模块（关键词: {keyword}）...")
        try:
            result = comment_on_csdn(
                keyword=keyword,
                comment_limit=comment_limit,
                style=style
            )
            
            if result.get('success'):
                self.log(f"评论模块执行完成，成功评论 {result.get('success_count', 0)} 篇文章", "SUCCESS")
            else:
                self.log(f"评论模块执行失败: {result.get('error', '未知错误')}", "ERROR")
            
            return result
        except Exception as e:
            self.log(f"评论模块执行失败: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            return {
                'success': False,
                'error': str(e),
                'total': 0,
                'success_count': 0,
                'results': []
            }
    
    def run_workflow(self, keyword: str, comment_limit: int = 3, style: str = "口语化") -> Dict:
        """
        执行爬取和评论工作流（一体流程）
        
        Args:
            keyword: 搜索关键词（用于评论）
            comment_limit: 评论文章数量限制
            style: 评论风格
            
        Returns:
            包含所有执行结果的字典
        """
        self.log("=" * 60)
        self.log("开始执行爬取和评论工作流")
        self.log("=" * 60)
        
        results = {
            'crawler': None,
            'comment': None,
            'success': True
        }
        
        # 1. 爬虫
        self.log("步骤1: 执行爬虫模块...")
        crawler_result = self.run_crawler()
        results['crawler'] = crawler_result
        if not crawler_result['success']:
            results['success'] = False
            self.log("爬虫执行失败，跳过评论步骤", "WARNING")
            return results
        
        # 2. 评论（基于关键词搜索相关文章）
        self.log(f"步骤2: 执行评论模块（关键词: {keyword}）...")
        comment_result = self.run_comment(
            keyword=keyword,
            comment_limit=comment_limit,
            style=style
        )
        results['comment'] = comment_result
        if not comment_result.get('success'):
            results['success'] = False
        
        self.log("=" * 60)
        self.log(f"爬取和评论工作流执行完成，总体状态: {'成功' if results['success'] else '部分失败'}")
        self.log("=" * 60)
        
        return results
    
    def get_logs(self) -> List[str]:
        """获取执行日志"""
        return self.execution_log


def main():
    """爬取和评论调度器主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='TrendRadar 爬取和评论调度器')
    parser.add_argument('--keyword', type=str, required=True, help='评论关键词（必需）')
    parser.add_argument('--comment-limit', type=int, default=3, help='评论文章数量限制')
    parser.add_argument('--style', type=str, default='口语化', help='评论风格（口语化、专业）')
    
    args = parser.parse_args()
    
    scheduler = CrawlerCommentScheduler()
    
    print("=" * 60)
    print("TrendRadar 爬取和评论调度器")
    print("=" * 60)
    print("\n功能：爬取热点数据并在CSDN上评论相关文章")
    print("=" * 60)
    
    results = scheduler.run_workflow(
        keyword=args.keyword,
        comment_limit=args.comment_limit,
        style=args.style
    )
    
    print("\n执行结果：")
    print("=" * 60)
    print(f"  爬虫: {'[成功]' if results['crawler'] and results['crawler']['success'] else '[失败]'}")
    if results.get('comment'):
        comment_result = results['comment']
        print(f"  评论: 总计 {comment_result.get('total', 0)} 篇，成功 {comment_result.get('success_count', 0)} 篇")
        print("\n  详细信息：")
        for r in comment_result.get('results', []):
            article = r.get('article', {})
            title = article.get('title', '未知')
            status = "[成功]" if r.get('success') else "[失败]"
            print(f"    {status} {title}")
            if r.get('comment'):
                print(f"      评论: {r['comment'][:50]}...")
    print("\n")


if __name__ == "__main__":
    main()








