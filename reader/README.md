# 博客阅读器模块

## 功能说明

博客阅读器模块能够：
1. **适配不同 DOM 结构的博客网站**：自动识别和提取文章链接和内容
2. **分析单篇文章**：生成摘要和质量描述（内容深度、逻辑清晰度、可读性、原创性、实用性）
3. **分析整个博客**：生成博主定位、整体质量评估等信息

## 使用方法

### 命令行使用

```bash
# 读取博客文章（不进行 AI 分析）
python reader.py --url https://example.com/blog --max-articles 10

# 分析博客（包含 AI 分析）
python reader.py --url https://example.com/blog --max-articles 10 --analyze
```

### 代码中使用

```python
from reader import analyze_blog, analyze_article, read_blog

# 分析整个博客
result = analyze_blog("https://example.com/blog", max_articles=10)
if result['success']:
    print(f"分析完成，共分析 {result['articles_count']} 篇文章")
    print("博主定位：", result['blogger_profile'])
    print("整体质量：", result['overall_quality'])

# 分析单篇文章
article = {
    'title': '文章标题',
    'content': '文章内容...'
}
analysis = analyze_article(article)
if analysis['success']:
    print("摘要：", analysis['summary'])
    print("质量评估：", analysis['quality'])

# 仅读取文章（不分析）
articles = read_blog("https://example.com/blog", max_articles=10)
for article in articles:
    print(article['title'])
```

## 配置要求

1. 确保在 `config/config.yaml` 中配置了 qwen 模型的 API Key
2. 安装依赖：`pip install beautifulsoup4 lxml`

## 工作原理

### 文章提取

模块使用多种常见的 CSS 选择器来适配不同的博客网站结构：
- 文章链接：`article a`, `.post a`, `.entry a`, `h2 a`, `h3 a` 等
- 文章内容：`article .entry-content`, `.post-content`, `article` 等
- 文章标题：`h1.entry-title`, `h1.post-title`, `article h1` 等

### AI 分析

使用配置的 qwen 模型进行：
- 单篇文章分析：生成摘要和质量评估
- 整体博客分析：生成博主定位和整体质量评估

## 提示词文件

- `global_prompt.txt`: 全局提示词，定义分析师的角色和基本要求
- `main/main_prompt.txt`: 主流程提示词，定义具体的分析维度和输出格式

可以修改这些文件来自定义分析行为。

