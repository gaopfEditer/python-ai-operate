# 使用创作模块生成文章

## 功能说明

创作模块现在支持两种模式：
1. **基于热点数据生成**：从爬虫模块获取热点数据，然后生成内容
2. **根据主题直接生成**：直接指定主题和要求，生成文章

## 方式一：使用命令行（推荐）

### 基本用法

```bash
# 生成关于Vue3与Vue2响应式区别和底层原理的文章
python create.py --topic "前端Vue3与Vue2响应式区别和底层原理"
```

### 完整参数

```bash
python create.py \
  --topic "前端Vue3与Vue2响应式区别和底层原理" \
  --requirements "请详细讲解Vue2和Vue3的响应式原理、区别、优缺点对比、实际应用场景和代码示例" \
  --platform "技术博客" \
  --type "技术文章" \
  --words 3000 \
  --style "专业"
```

### 参数说明

- `--topic`: 文章主题/标题（必需）
- `--requirements`: 具体要求（可选）
- `--platform`: 目标平台，如"技术博客"、"知乎"、"微信公众号"等（默认：通用）
- `--type`: 内容类型，如"技术文章"、"博客文章"、"教程"等（默认：技术文章）
- `--words`: 目标字数（默认：2000）
- `--style`: 文章风格，如"专业"、"通俗"、"学术"等（默认：专业）

## 方式二：使用Python脚本

### 示例1：生成Vue3与Vue2响应式原理文章

```python
from create.index import generate_article_by_topic

result = generate_article_by_topic(
    topic="前端Vue3与Vue2响应式区别和底层原理",
    requirements="""
请详细讲解：
1. Vue2的响应式原理（Object.defineProperty）
2. Vue3的响应式原理（Proxy）
3. 两者的区别和优缺点对比
4. 实际应用场景的选择建议
5. 代码示例和性能对比
""",
    platform="技术博客",
    content_type="技术文章",
    word_count=3000,
    style="专业"
)

if result['success']:
    print("生成的文章：")
    print(result['content'])
    
    # 保存到文件
    with open('article.md', 'w', encoding='utf-8') as f:
        f.write(f"# {topic}\n\n")
        f.write(result['content'])
else:
    print(f"生成失败：{result['error']}")
```

### 示例2：使用示例脚本

```bash
# 直接运行示例脚本
python example_generate_article.py
```

## 方式三：在调度器中使用

```python
from main.scheduler import WorkflowScheduler
from create.index import generate_article_by_topic

# 生成文章
result = generate_article_by_topic(
    topic="前端Vue3与Vue2响应式区别和底层原理",
    word_count=3000
)

if result['success']:
    # 可以继续发布
    from public.index import publish_content
    publish_content({
        'title': '前端Vue3与Vue2响应式区别和底层原理',
        'content': result['content'],
        'platform': '技术博客'
    })
```

## 输出说明

### 成功时返回

```python
{
    'success': True,
    'content': '生成的文章内容...',
    'error': '',
    'usage': {
        'input_tokens': 100,
        'output_tokens': 1500,
        'total_tokens': 1600
    }
}
```

### 失败时返回

```python
{
    'success': False,
    'content': '',
    'error': '错误信息',
    'usage': {}
}
```

## 文章保存位置

使用命令行生成的文章会自动保存到：
```
output/articles/YYYYMMDD_HHMMSS_文章主题.md
```

## 使用示例

### 示例1：生成技术文章

```bash
python create.py --topic "深入理解JavaScript闭包" --words 2500 --style "专业"
```

### 示例2：生成教程文章

```bash
python create.py \
  --topic "从零开始学习React Hooks" \
  --type "教程" \
  --words 4000 \
  --style "通俗"
```

### 示例3：生成对比分析文章

```bash
python create.py \
  --topic "TypeScript vs JavaScript：全面对比分析" \
  --requirements "请从性能、类型安全、开发体验、生态等多个维度进行对比" \
  --words 3500
```

## 注意事项

1. **API Key配置**：确保在 `config/config.yaml` 中配置了千问API Key
2. **字数控制**：实际生成的字数可能与目标字数有差异，这是正常的
3. **内容质量**：生成的内容建议人工审核和优化
4. **Token消耗**：长文章会消耗更多token，注意API配额
5. **网络连接**：需要稳定的网络连接来调用千问API

## 常见问题

### Q: 生成的文章质量如何？
A: 文章质量取决于：
- 主题的明确性
- 要求的详细程度
- 选择的模型（qwen-turbo/qwen-plus/qwen-max）
- 字数设置（太短可能不够详细，太长可能不够聚焦）

### Q: 可以生成代码示例吗？
A: 可以，在 `--requirements` 中明确要求包含代码示例即可。

### Q: 如何生成特定风格的文章？
A: 使用 `--style` 参数，可选值：
- 专业：技术性强，适合技术博客
- 通俗：易于理解，适合大众平台
- 学术：严谨规范，适合学术平台

### Q: 生成失败怎么办？
A: 检查：
1. API Key是否正确配置
2. 网络连接是否正常
3. API配额是否充足
4. 错误信息中的具体提示

## 下一步

生成文章后，你可以：
1. 使用发布模块发布到各平台
2. 使用评论模块对相关文章进行评论
3. 将文章保存到数据库或文件系统
4. 进一步编辑和优化内容

