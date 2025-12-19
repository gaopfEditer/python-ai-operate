# coding=utf-8
"""
创建和发布调度器
用于按照 topic.js 列表创建文章并发布到平台
"""

import sys
import time
import re
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from create.index import generate_article_by_topic
from public.index import publish_content


class CreatePublishScheduler:
    """创建和发布调度器"""
    
    def __init__(self):
        self.project_root = project_root
        self.execution_log = []
    
    def log(self, message: str, level: str = "INFO"):
        """记录执行日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        self.execution_log.append(log_entry)
        print(log_entry)
    
    def load_topics_from_js(self) -> List[Dict]:
        """
        从 main/topic.js 文件加载主题列表
        
        Returns:
            主题列表，每个主题包含 title 和 desc
        """
        topic_file = self.project_root / "main" / "topic.js"
        
        if not topic_file.exists():
            self.log(f"主题文件不存在: {topic_file}", "WARNING")
            return []
        
        try:
            with open(topic_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析 JavaScript 对象
            topics = []
            
            # 使用正则表达式提取 top1, top2 等对象
            pattern = r'top\d+:\s*\{[^}]+\}'
            matches = re.findall(pattern, content, re.DOTALL)
            
            for match in matches:
                # 提取标题和描述
                title_match = re.search(r'title:\s*"([^"]+)"', match)
                desc_match = re.search(r'desc:\s*"([^"]*)"', match)
                
                if title_match:
                    topics.append({
                        'title': title_match.group(1),
                        'desc': desc_match.group(1) if desc_match else ''
                    })
            
            # 按 top1, top2 顺序排序
            topics.sort(key=lambda x: x['title'])
            
            self.log(f"从 topic.js 加载了 {len(topics)} 个主题", "INFO")
            return topics
            
        except Exception as e:
            self.log(f"加载主题文件失败: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            return []
    
    def check_article_exists(self, title: str) -> Optional[Path]:
        """
        检查文章是否已存在于输出目录
        
        Args:
            title: 文章标题
            
        Returns:
            如果存在，返回文件路径；否则返回 None
        """
        output_dir = self.project_root / "output" / "articles"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 在文件名中查找标题关键词
        title_keywords = title[:20]  # 取前20个字符作为关键词
        
        for file_path in output_dir.glob("*.md"):
            if title_keywords in file_path.stem:
                return file_path
        
        return None
    
    def create_and_publish_topic(self, topic: Dict, 
                                 word_count: int = 3000,
                                 style: str = "专业",
                                 platform: str = "技术博客") -> Dict:
        """
        创建并发布单个主题的文章
        
        Args:
            topic: 主题字典，包含 title 和 desc
            word_count: 目标字数
            style: 文章风格
            platform: 目标平台
            
        Returns:
            包含创建和发布结果的字典
        """
        title = topic.get('title', '')
        desc = topic.get('desc', '')
        
        self.log(f"处理主题: {title}", "INFO")
        
        result = {
            'topic': title,
            'create': None,
            'publish': None,
            'success': False
        }
        
        # 1. 检查文章是否已存在
        existing_file = self.check_article_exists(title)
        if existing_file:
            self.log(f"文章已存在: {existing_file.name}，跳过创建", "INFO")
            # 读取已有文章内容
            try:
                with open(existing_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 提取文章正文（去掉元数据）
                    if '---' in content:
                        content = content.split('---', 1)[1].strip()
                    
                result['create'] = {
                    'success': True,
                    'content': content,
                    'file_path': str(existing_file)
                }
            except Exception as e:
                self.log(f"读取已有文章失败: {e}", "ERROR")
                result['create'] = {'success': False, 'error': str(e)}
                return result
        else:
            # 2. 创建文章
            self.log(f"开始创建文章: {title}", "INFO")
            create_result = generate_article_by_topic(
                topic=title,
                requirements=desc,
                platform=platform,
                content_type="技术文章",
                word_count=word_count,
                style=style
            )
            
            result['create'] = create_result
            
            if not create_result.get('success'):
                self.log(f"文章创建失败: {create_result.get('error', '未知错误')}", "ERROR")
                return result
            
            # 保存文章到文件
            output_dir = self.project_root / "output" / "articles"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{title[:30]}.md"
            output_path = output_dir / filename
            
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(f"# {title}\n\n")
                    f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    f.write(f"**平台**: {platform}\n\n")
                    f.write(f"**类型**: 技术文章\n\n")
                    if desc:
                        f.write(f"**要求**: {desc}\n\n")
                    f.write("---\n\n")
                    f.write(create_result['content'])
                
                self.log(f"文章已保存: {output_path.name}", "SUCCESS")
                result['create']['file_path'] = str(output_path)
            except Exception as e:
                self.log(f"保存文章失败: {e}", "ERROR")
                result['create']['error'] = f"保存失败: {str(e)}"
                return result
        
        # 3. 发布文章
        if result['create'] and result['create'].get('success'):
            self.log(f"开始发布文章: {title}", "INFO")
            
            # 如果是从文件读取的，需要提取内容
            content_text = result['create']['content']
            if result['create'].get('file_path'):
                # 如果提供了文件路径，可以尝试从文件读取
                try:
                    file_path = Path(result['create']['file_path'])
                    if file_path.exists():
                        with open(file_path, 'r', encoding='utf-8') as f:
                            file_content = f.read()
                            # 提取正文（去掉元数据）
                            if '---' in file_content:
                                content_text = file_content.split('---', 1)[1].strip()
                            else:
                                # 如果没有分隔符，去掉标题行
                                lines = file_content.split('\n')
                                content_text = '\n'.join(lines[1:]) if len(lines) > 1 else file_content
                except Exception as e:
                    self.log(f"从文件读取内容失败，使用已有内容: {e}", "WARNING")
            
            publish_result = publish_content(
                content={
                    'title': title,
                    'content': content_text
                }
            )
            
            result['publish'] = publish_result
            
            if publish_result.get('success'):
                self.log(f"文章发布成功: {title}", "SUCCESS")
                result['success'] = True
            else:
                self.log(f"文章发布失败: {publish_result.get('error', '未知错误')}", "ERROR")
        
        return result
    
    def run_workflow(self, 
                    word_count: int = 3000,
                    style: str = "专业",
                    platform: str = "技术博客") -> Dict:
        """
        执行创建和发布工作流
        按照 topic.js 中的主题列表，依次创建和发布文章
        
        Args:
            word_count: 目标字数
            style: 文章风格
            platform: 目标平台
            
        Returns:
            包含所有执行结果的字典
        """
        self.log("=" * 60)
        self.log("开始执行创建和发布工作流（按 topic.js 列表）")
        self.log("=" * 60)
        
        # 加载主题列表
        topics = self.load_topics_from_js()
        
        if not topics:
            self.log("未找到主题列表，工作流终止", "ERROR")
            return {
                'success': False,
                'error': '未找到主题列表',
                'total': 0,
                'success_count': 0,
                'results': []
            }
        
        self.log(f"共找到 {len(topics)} 个主题，开始处理...", "INFO")
        
        results = []
        success_count = 0
        
        # 按顺序处理每个主题
        for i, topic in enumerate(topics, 1):
            self.log(f"\n[{i}/{len(topics)}] 处理主题: {topic['title']}", "INFO")
            self.log("-" * 60)
            
            result = self.create_and_publish_topic(
                topic=topic,
                word_count=word_count,
                style=style,
                platform=platform
            )
            
            results.append(result)
            
            if result['success']:
                success_count += 1
            
            # 每个主题之间稍作延迟
            if i < len(topics):
                time.sleep(2)
        
        self.log("\n" + "=" * 60)
        self.log(f"创建和发布工作流执行完成")
        self.log(f"总计: {len(topics)} 个主题")
        self.log(f"成功: {success_count} 个")
        self.log(f"失败: {len(topics) - success_count} 个")
        self.log("=" * 60)
        
        return {
            'success': success_count > 0,
            'total': len(topics),
            'success_count': success_count,
            'results': results
        }
    
    def get_logs(self) -> List[str]:
        """获取执行日志"""
        return self.execution_log


def main():
    """创建和发布调度器主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='TrendRadar 创建和发布调度器')
    parser.add_argument('--words', type=int, default=3000, help='目标字数')
    parser.add_argument('--style', type=str, default='专业', help='文章风格')
    parser.add_argument('--platform', type=str, default='技术博客', help='目标平台')
    
    args = parser.parse_args()
    
    scheduler = CreatePublishScheduler()
    
    print("=" * 60)
    print("TrendRadar 创建和发布调度器")
    print("=" * 60)
    print("\n功能：按照 topic.js 列表创建文章并发布到平台")
    print("=" * 60)
    
    results = scheduler.run_workflow(
        word_count=args.words,
        style=args.style,
        platform=args.platform
    )
    
    print("\n执行结果：")
    print("=" * 60)
    for i, result in enumerate(results.get('results', []), 1):
        topic = result.get('topic', '未知')
        status = "[成功]" if result.get('success') else "[失败]"
        print(f"  [{i}] {status} {topic}")
        if result.get('publish') and result['publish'].get('url'):
            print(f"      发布链接: {result['publish']['url']}")
    print("\n")


if __name__ == "__main__":
    main()





