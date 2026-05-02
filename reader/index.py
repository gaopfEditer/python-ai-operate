# coding=utf-8
"""
博客阅读器核心功能
用于阅读和分析博客网站内容
"""

import sys
import io
import re
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# 设置标准输出编码为 UTF-8（Windows 兼容）
if sys.platform == 'win32':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except:
        pass

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.ai_client import get_qwen_client

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BlogReader:
    """博客阅读器，能够适配不同 DOM 结构的博客网站"""
    
    def __init__(self, base_url: str, headers: Optional[Dict] = None):
        """
        初始化博客阅读器
        
        Args:
            base_url: 博客网站的基础 URL
            headers: 自定义请求头
        """
        self.base_url = base_url.rstrip('/')
        self.headers = headers or {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """
        获取并解析网页
        
        Args:
            url: 网页 URL
            
        Returns:
            BeautifulSoup 对象，失败返回 None
        """
        try:
            # 确保 URL 完整
            if not url.startswith('http'):
                url = urljoin(self.base_url, url)
            
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or 'utf-8'
            
            soup = BeautifulSoup(response.text, 'lxml')
            return soup
        except Exception as e:
            logger.error(f"获取网页失败 {url}: {e}")
            return None
    
    def extract_article_links(self, soup: BeautifulSoup, limit: int = 20, try_archives: bool = True) -> List[Dict]:
        """
        从博客首页或列表页提取文章链接
        
        Args:
            soup: BeautifulSoup 对象
            limit: 最大提取数量
            try_archives: 如果当前页面没找到文章，是否尝试访问 archives 页面
            
        Returns:
            文章链接列表，每个元素包含 title 和 url
        """
        articles = []
        
        # 常见的文章链接选择器（按优先级排序）
        selectors = [
            # 通用博客选择器
            'article a',
            '.post a',
            '.entry a',
            '.article a',
            '.blog-post a',
            '.post-title a',
            '.entry-title a',
            '.article-title a',
            'h2 a',
            'h3 a',
            # 列表页选择器
            '.post-list a',
            '.article-list a',
            '.blog-list a',
            # 其他常见选择器
            'main a',
            '.content a',
        ]
        
        seen_urls = set()
        
        for selector in selectors:
            if len(articles) >= limit:
                break
            
            try:
                links = soup.select(selector)
                for link in links:
                    if len(articles) >= limit:
                        break
                    
                    href = link.get('href', '')
                    if not href:
                        continue
                    
                    # 确保 URL 完整
                    if not href.startswith('http'):
                        href = urljoin(self.base_url, href)
                    
                    # 跳过已见过的 URL
                    if href in seen_urls:
                        continue
                    
                    # 获取标题文本
                    title = link.get_text(strip=True)
                    if not title or len(title) < 5:  # 标题太短可能是导航链接
                        continue
                    
                    # 过滤掉明显不是文章链接的 URL
                    skip_patterns = ['#', 'javascript:', 'mailto:', '/tag/', '/category/', '/author/', 
                                   '/page/', '/charts/', '/link/', '/comment/', '/shuoshuo/', 
                                   '/subscribe/', '/statement/', '/info/', '/about/', '/devices/', 
                                   '/rewards/', '/addlink/', '/fcircle/', '/archives/']
                    if any(skip in href.lower() for skip in skip_patterns):
                        continue
                    
                    # 优先识别文章链接模式（Hexo 风格：/posts/xxxxx/）
                    is_article = False
                    if '/posts/' in href and href.count('/') >= 3:
                        is_article = True
                    elif '/post/' in href and href.count('/') >= 3:
                        is_article = True
                    elif re.search(r'/\d{4}/\d{2}/\d{2}/', href):  # 日期格式
                        is_article = True
                    elif href.startswith('/') and len(href) > 5 and any(char.isdigit() for char in href):
                        # 包含数字的路径可能是文章
                        is_article = True
                    
                    # 如果不是明确的文章链接，跳过
                    if not is_article and href.startswith('/') and len(href) <= 10:
                        continue
                    
                    articles.append({
                        'title': title,
                        'url': href
                    })
                    seen_urls.add(href)
            except Exception as e:
                logger.debug(f"选择器 {selector} 提取失败: {e}")
                continue
        
        # 如果上面的方法都没找到，尝试更通用的方法
        if not articles:
            try:
                all_links = soup.find_all('a', href=True)
                for link in all_links:
                    if len(articles) >= limit:
                        break
                    
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    if not href or not title or len(title) < 10:
                        continue
                    
                    if not href.startswith('http'):
                        href = urljoin(self.base_url, href)
                    
                    if href in seen_urls:
                        continue
                    
                    # 更严格的过滤
                    skip_patterns = ['#', 'javascript:', 'mailto:', '/tag/', '/category/', '/author/', 
                                   '/page/', '/search', '/login', '/register', '/charts/', '/link/', 
                                   '/comment/', '/shuoshuo/', '/subscribe/', '/statement/', '/info/', 
                                   '/about/', '/devices/', '/rewards/', '/addlink/', '/fcircle/', '/archives/']
                    if any(skip in href.lower() for skip in skip_patterns):
                        continue
                    
                    # 检查是否可能是文章链接
                    is_article = False
                    if '/posts/' in href or '/post/' in href:
                        is_article = True
                    elif re.search(r'/\d{4}/\d{2}/\d{2}/', href):  # 日期格式
                        is_article = True
                    elif re.search(r'/\d{4}/|/\d+/|\.html|\.php', href):
                        is_article = True
                    elif href.startswith('/') and len(href) > 5 and any(char.isdigit() for char in href):
                        is_article = True
                    
                    if is_article:
                        articles.append({
                            'title': title,
                            'url': href
                        })
                        seen_urls.add(href)
            except Exception as e:
                logger.debug(f"通用链接提取失败: {e}")
        
        # 如果当前页面没有找到文章，尝试访问 archives 页面
        if not articles and try_archives:
            try:
                archives_url = urljoin(self.base_url, '/archives/')
                logger.info(f"当前页面未找到文章，尝试访问: {archives_url}")
                archives_soup = self.fetch_page(archives_url)
                if archives_soup:
                    # 递归调用自己，但不再尝试 archives（避免无限递归）
                    archives_articles = self.extract_article_links(archives_soup, limit=limit, try_archives=False)
                    if archives_articles:
                        articles = archives_articles
                        logger.info(f"从 archives 页面提取到 {len(articles)} 篇文章")
            except Exception as e:
                logger.debug(f"访问 archives 页面失败: {e}")
        
        logger.info(f"提取到 {len(articles)} 篇文章链接")
        return articles[:limit]
    
    def extract_article_content(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        从文章页面提取内容
        
        Args:
            soup: BeautifulSoup 对象
            
        Returns:
            包含文章信息的字典
        """
        article_data = {
            'title': '',
            'content': '',
            'author': '',
            'date': '',
            'tags': []
        }
        
        # 提取标题
        title_selectors = [
            'h1.entry-title',
            'h1.post-title',
            'h1.article-title',
            'article h1',
            '.post-header h1',
            '.entry-header h1',
            'h1'
        ]
        
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                article_data['title'] = title_elem.get_text(strip=True)
                break
        
        # 提取正文内容
        content_selectors = [
            'article .entry-content',
            'article .post-content',
            'article .article-content',
            'article .content',
            '.entry-content',
            '.post-content',
            '.article-content',
            'article',
            '.content',
            'main',
        ]
        
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                # 移除脚本和样式
                for script in content_elem(['script', 'style', 'nav', 'footer', 'header', 'aside', '.sidebar']):
                    script.decompose()
                
                # 获取文本内容
                text = content_elem.get_text(separator='\n', strip=True)
                if len(text) > 200:  # 内容足够长才认为是正文
                    article_data['content'] = text
                    break
        
        # 提取作者
        author_selectors = [
            '.author',
            '.post-author',
            '.entry-author',
            '[rel="author"]',
            '.by-author',
        ]
        
        for selector in author_selectors:
            author_elem = soup.select_one(selector)
            if author_elem:
                article_data['author'] = author_elem.get_text(strip=True)
                break
        
        # 提取日期
        date_selectors = [
            'time',
            '.date',
            '.post-date',
            '.entry-date',
            '.published',
            '[datetime]',
        ]
        
        for selector in date_selectors:
            date_elem = soup.select_one(selector)
            if date_elem:
                date_text = date_elem.get('datetime') or date_elem.get_text(strip=True)
                if date_text:
                    article_data['date'] = date_text
                    break
        
        # 提取标签
        tag_selectors = [
            '.tags a',
            '.tag a',
            '.post-tags a',
            '.entry-tags a',
            '[rel="tag"]',
        ]
        
        for selector in tag_selectors:
            tag_elems = soup.select(selector)
            if tag_elems:
                article_data['tags'] = [tag.get_text(strip=True) for tag in tag_elems]
                break
        
        return article_data
    
    def read_articles(self, article_urls: List[str], max_articles: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        读取多篇文章
        
        Args:
            article_urls: 文章 URL 列表
            max_articles: 最大读取数量
            
        Returns:
            文章数据列表
        """
        if max_articles:
            article_urls = article_urls[:max_articles]
        
        articles = []
        for i, url in enumerate(article_urls, 1):
            logger.info(f"正在读取文章 {i}/{len(article_urls)}: {url}")
            
            soup = self.fetch_page(url)
            if not soup:
                continue
            
            article_data = self.extract_article_content(soup)
            article_data['url'] = url
            
            if article_data['content']:
                articles.append(article_data)
            
            # 避免请求过快
            time.sleep(1)
        
        logger.info(f"成功读取 {len(articles)} 篇文章")
        return articles


def analyze_article(article: Dict[str, Any]) -> Dict[str, Any]:
    """
    分析单篇文章，生成摘要和质量描述
    
    Args:
        article: 文章数据字典，包含 title, content, url 等
        
    Returns:
        包含分析结果的字典
    """
    client = get_qwen_client()
    
    if not client.enable:
        return {
            'success': False,
            'error': '千问模型未启用或API Key未配置',
            'summary': '',
            'quality': {}
        }
    
    # 构建分析提示词
    content = article.get('content', '')
    title = article.get('title', '')
    
    if not content:
        return {
            'success': False,
            'error': '文章内容为空',
            'summary': '',
            'quality': {}
        }
    
    # 限制内容长度，避免 token 过多
    max_content_length = 8000
    if len(content) > max_content_length:
        content = content[:max_content_length] + "..."
    
    # 使用全局提示词和主流程提示词
    system_prompt_path = project_root / "reader" / "global_prompt.txt"
    main_prompt_path = project_root / "reader" / "main" / "main_prompt.txt"
    
    system_prompt = ""
    if system_prompt_path.exists():
        with open(system_prompt_path, 'r', encoding='utf-8') as f:
            system_prompt += f.read() + "\n\n"
    
    if main_prompt_path.exists():
        with open(main_prompt_path, 'r', encoding='utf-8') as f:
            system_prompt += f.read()
    else:
        # 如果没有提示词文件，使用默认提示词
        system_prompt += """你是一个专业的内容分析师。请仔细分析给定的博客文章，并生成以下内容：

1. **文章摘要**：用200-300字概括文章的核心内容和主要观点
2. **质量评估**：从以下维度评估文章质量（每个维度1-10分）：
   - 内容深度：文章内容的专业性和深度
   - 逻辑清晰度：文章结构的逻辑性和条理性
   - 可读性：文章表达的清晰度和易读性
   - 原创性：内容的原创性和独特性
   - 实用性：内容的实用价值和应用性
3. **主题分类**：识别文章的主要主题和领域
4. **目标受众**：分析文章的目标读者群体
5. **写作风格**：描述文章的写作风格特点

请以结构化的方式输出分析结果，使用清晰的格式。"""
    
    user_prompt = f"""请分析以下博客文章：

**标题**：{title}

**内容**：
{content}

请按照要求生成文章摘要和质量评估。"""
    
    # 调用 AI 分析
    result = client.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=0.3,  # 分析任务需要更稳定的输出
        max_tokens=2000
    )
    
    if not result.get('success'):
        return {
            'success': False,
            'error': result.get('error', '分析失败'),
            'summary': '',
            'quality': {}
        }
    
    # 解析 AI 返回的结果
    analysis_text = result.get('content', '')
    
    # 尝试提取结构化信息
    summary = ''
    quality_scores = {}
    
    # 提取摘要（通常在"摘要"或"Summary"之后）
    summary_match = re.search(r'(?:摘要|Summary)[:：]\s*(.+?)(?:\n\n|\n(?:质量|Quality|主题|Topic))', analysis_text, re.DOTALL)
    if summary_match:
        summary = summary_match.group(1).strip()
    else:
        # 如果没有找到，取前300字作为摘要
        summary = analysis_text[:300].strip()
    
    # 提取质量分数
    quality_patterns = {
        '内容深度': r'内容深度[：:]\s*(\d+)',
        '逻辑清晰度': r'逻辑清晰度[：:]\s*(\d+)',
        '可读性': r'可读性[：:]\s*(\d+)',
        '原创性': r'原创性[：:]\s*(\d+)',
        '实用性': r'实用性[：:]\s*(\d+)',
    }
    
    for key, pattern in quality_patterns.items():
        match = re.search(pattern, analysis_text)
        if match:
            try:
                quality_scores[key] = int(match.group(1))
            except:
                pass
    
    return {
        'success': True,
        'summary': summary,
        'quality': quality_scores,
        'full_analysis': analysis_text,
        'error': ''
    }


def analyze_blog(base_url: str, max_articles: int = 10) -> Dict[str, Any]:
    """
    分析整个博客，生成博主定位和整体质量评估
    
    Args:
        base_url: 博客网站的基础 URL
        max_articles: 最大分析文章数量
        
    Returns:
        包含整体分析结果的字典
    """
    logger.info(f"开始分析博客: {base_url}")
    
    reader = BlogReader(base_url)
    
    # 1. 获取博客首页
    soup = reader.fetch_page(base_url)
    if not soup:
        return {
            'success': False,
            'error': '无法访问博客首页',
            'articles': [],
            'blogger_profile': {},
            'overall_quality': {}
        }
    
    # 2. 提取文章链接
    article_links = reader.extract_article_links(soup, limit=max_articles)
    if not article_links:
        return {
            'success': False,
            'error': '未找到文章链接',
            'articles': [],
            'blogger_profile': {},
            'overall_quality': {}
        }
    
    # 3. 读取文章内容
    article_urls = [link['url'] for link in article_links]
    articles = reader.read_articles(article_urls, max_articles=max_articles)
    
    if not articles:
        return {
            'success': False,
            'error': '无法读取文章内容',
            'articles': [],
            'blogger_profile': {},
            'overall_quality': {}
        }
    
    # 4. 分析每篇文章
    analyzed_articles = []
    for article in articles:
        logger.info(f"正在分析文章: {article.get('title', '未知标题')}")
        analysis = analyze_article(article)
        
        analyzed_articles.append({
            **article,
            'analysis': analysis
        })
        
        # 避免请求过快
        time.sleep(1)
    
    # 5. 生成整体分析
    client = get_qwen_client()
    if not client.enable:
        return {
            'success': False,
            'error': '千问模型未启用或API Key未配置',
            'articles': analyzed_articles,
            'blogger_profile': {},
            'overall_quality': {}
        }
    
    # 构建整体分析提示词
    articles_summary = []
    for i, article in enumerate(analyzed_articles[:10], 1):  # 最多使用10篇文章进行分析
        title = article.get('title', '未知标题')
        summary = article.get('analysis', {}).get('summary', '')
        if summary:
            articles_summary.append(f"{i}. {title}\n   摘要：{summary}")
    
    # 使用全局提示词
    system_prompt_path = project_root / "reader" / "global_prompt.txt"
    
    system_prompt = ""
    if system_prompt_path.exists():
        with open(system_prompt_path, 'r', encoding='utf-8') as f:
            system_prompt += f.read() + "\n\n"
    
    system_prompt += """你是一个专业的博客分析师。请基于多篇博客文章的分析结果，生成以下内容：

1. **博主定位**：
   - 专业领域：博主主要关注的技术或知识领域
   - 内容风格：博主的内容创作风格和特点
   - 目标受众：博主的目标读者群体
   - 价值主张：博主提供的核心价值

2. **整体质量评估**：
   - 内容质量：整体内容的质量水平（1-10分）
   - 更新频率：根据文章时间判断更新频率
   - 专业性：内容的专业程度（1-10分）
   - 影响力：内容的影响力和传播价值（1-10分）

3. **优势与不足**：
   - 主要优势：博主和内容的优势
   - 改进建议：可以改进的方向

请以结构化的方式输出分析结果。"""
    
    user_prompt = f"""请基于以下博客文章分析结果，生成整体博主定位和质量评估：

**博客地址**：{base_url}
**分析文章数量**：{len(articles_summary)} 篇

**文章列表**：
{chr(10).join(articles_summary)}

请按照要求生成博主定位和整体质量评估。"""
    
    # 调用 AI 生成整体分析
    result = client.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=0.3,
        max_tokens=2000
    )
    
    blogger_profile = {}
    overall_quality = {}
    
    if result.get('success'):
        analysis_text = result.get('content', '')
        
        # 尝试提取结构化信息
        # 这里可以进一步解析，但为了灵活性，直接返回完整文本
        blogger_profile = {
            'full_analysis': analysis_text
        }
        
        # 提取质量分数
        quality_patterns = {
            '内容质量': r'内容质量[：:]\s*(\d+)',
            '专业性': r'专业性[：:]\s*(\d+)',
            '影响力': r'影响力[：:]\s*(\d+)',
        }
        
        for key, pattern in quality_patterns.items():
            match = re.search(pattern, analysis_text)
            if match:
                try:
                    overall_quality[key] = int(match.group(1))
                except:
                    pass
    
    return {
        'success': True,
        'blog_url': base_url,
        'articles_count': len(analyzed_articles),
        'articles': analyzed_articles,
        'blogger_profile': blogger_profile,
        'overall_quality': overall_quality,
        'error': ''
    }


def read_blog(base_url: str, max_articles: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    读取博客文章（不进行分析）
    
    Args:
        base_url: 博客网站的基础 URL
        max_articles: 最大读取数量
        
    Returns:
        文章数据列表
    """
    reader = BlogReader(base_url)
    
    soup = reader.fetch_page(base_url)
    if not soup:
        return []
    
    article_links = reader.extract_article_links(soup, limit=max_articles or 20)
    article_urls = [link['url'] for link in article_links]
    
    articles = reader.read_articles(article_urls, max_articles=max_articles)
    return articles


def main():
    """
    博客阅读器主入口
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='TrendRadar 博客阅读器')
    parser.add_argument('--url', type=str, required=True, help='博客网站 URL')
    parser.add_argument('--max-articles', type=int, default=10, help='最大分析文章数量')
    parser.add_argument('--analyze', action='store_true', help='是否进行 AI 分析')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("TrendRadar 博客阅读器")
    print("=" * 60)
    
    client = get_qwen_client()
    if not client.enable and args.analyze:
        print("\n[警告] 千问模型未启用或API Key未配置")
        print("请在 config/config.yaml 中配置 ai.qwen.api_key")
        print("将仅读取文章，不进行 AI 分析\n")
        args.analyze = False
    
    if args.analyze:
        print(f"\n正在分析博客: {args.url}")
        print(f"最大分析文章数: {args.max_articles}")
        print("=" * 60)
        
        result = analyze_blog(args.url, max_articles=args.max_articles)
        
        if result.get('success'):
            print(f"\n[成功] 分析完成")
            print(f"博客地址: {result['blog_url']}")
            print(f"分析文章数: {result['articles_count']}")
            
            print("\n--- 博主定位 ---")
            profile = result.get('blogger_profile', {})
            if profile.get('full_analysis'):
                print(profile['full_analysis'])
            
            print("\n--- 整体质量评估 ---")
            quality = result.get('overall_quality', {})
            for key, value in quality.items():
                print(f"{key}: {value}/10")
            
            print("\n--- 文章分析详情 ---")
            for i, article in enumerate(result.get('articles', [])[:5], 1):  # 只显示前5篇
                print(f"\n{i}. {article.get('title', '未知标题')}")
                analysis = article.get('analysis', {})
                if analysis.get('summary'):
                    print(f"   摘要: {analysis['summary'][:100]}...")
                if analysis.get('quality'):
                    print(f"   质量: {analysis['quality']}")
        else:
            print(f"\n[失败] {result.get('error', '未知错误')}")
    else:
        print(f"\n正在读取博客: {args.url}")
        print("=" * 60)
        
        articles = read_blog(args.url, max_articles=args.max_articles)
        
        print(f"\n[成功] 读取到 {len(articles)} 篇文章")
        for i, article in enumerate(articles[:10], 1):
            print(f"\n{i}. {article.get('title', '未知标题')}")
            print(f"   URL: {article.get('url', '')}")
            content_preview = article.get('content', '')[:100]
            if content_preview:
                print(f"   内容预览: {content_preview}...")
    
    print("\n")


if __name__ == "__main__":
    main()

