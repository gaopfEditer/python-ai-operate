# 千问AI模型使用说明

## 配置千问API Key

### 1. 获取API Key

1. 访问 [阿里云DashScope控制台](https://dashscope.console.aliyun.com/)
2. 注册/登录账号
3. 创建API Key
4. 复制API Key

### 2. 配置到项目

编辑 `config/config.yaml` 文件，在 `ai.qwen` 配置项中填入你的API Key：

```yaml
ai:
  qwen:
    api_key: "你的API Key"  # 在这里填入你的千问API Key
    api_endpoint: "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    model: "qwen-turbo"  # 可选：qwen-turbo, qwen-plus, qwen-max, qwen-max-longcontext
    temperature: 0.7  # 温度参数，控制输出随机性（0-1）
    max_tokens: 2000  # 最大生成token数
    timeout: 30  # 请求超时时间（秒）
    enable: true  # 是否启用千问模型
```

### 3. 模型选择

- **qwen-turbo**：快速响应，适合一般内容生成
- **qwen-plus**：平衡性能和效果
- **qwen-max**：最佳效果，适合高质量内容
- **qwen-max-longcontext**：支持长文本上下文

## 使用方式

### 在创作模块中使用

```python
from utils.ai_client import get_qwen_client

client = get_qwen_client()

# 生成内容
result = client.generate(
    prompt="基于以下热点数据生成一篇文章：...",
    system_prompt="你是一个专业的内容创作者...",
    temperature=0.7,
    max_tokens=2000
)

if result['success']:
    print(result['content'])
else:
    print(f"生成失败：{result['error']}")
```

### 在评论模块中使用

```python
from utils.ai_client import get_qwen_client

client = get_qwen_client()

# 生成评论
result = client.generate(
    prompt="基于以下文章生成一条评论：...",
    system_prompt="你是一个专业的评论者...",
    temperature=0.8,
    max_tokens=500
)

if result['success']:
    print(result['content'])
```

### 使用提示词文件

```python
from utils.ai_client import get_qwen_client

client = get_qwen_client()

# 使用提示词文件生成内容
result = client.generate_with_prompt_file(
    prompt_file="create/global_prompt.txt",
    user_input="热点数据：..."
)
```

## 模块集成

### 创作模块（create.py）

创作模块已集成千问调用，可以通过以下方式使用：

```python
from create import generate_content

hot_data = {
    'title': 'AI技术新突破',
    'content': '人工智能技术取得重大进展...',
    'keywords': ['AI', '技术', '突破']
}

result = generate_content(
    hot_data=hot_data,
    platform='微博',
    content_type='微博'
)

if result['success']:
    print("生成的内容：")
    print(result['content'])
```

### 评论模块（comment.py）

评论模块已集成千问调用，可以通过以下方式使用：

```python
from comment import generate_comment

article = {
    'title': 'AI技术新突破',
    'content': '人工智能技术取得重大进展...'
}

result = generate_comment(
    article=article,
    platform='微博',
    comment_type='正面'
)

if result['success']:
    print("生成的评论：")
    print(result['content'])
```

## 提示词文件说明

### 全局提示词（global_prompt.txt）

每个模块的 `global_prompt.txt` 文件定义了该模块的通用规则和功能说明。当调用千问模型时，这些提示词会自动作为系统提示词加载。

### 主流程提示词（main/main_prompt.txt）

主流程提示词定义了完整的业务流程，包括如何使用AI模型生成内容。

### 平台提示词（platforms/{platform}_prompt.txt）

可以为不同平台创建特定的提示词文件，用于生成符合平台规范的内容。

## 错误处理

如果API调用失败，系统会返回包含错误信息的字典：

```python
{
    'success': False,
    'content': '',
    'error': '错误信息',
    'usage': {}
}
```

常见错误：
- **API Key未配置**：检查 config.yaml 中的 api_key 配置
- **API Key无效**：确认API Key是否正确
- **网络错误**：检查网络连接和API端点
- **请求超时**：增加 timeout 配置值

## 注意事项

1. **API Key安全**：不要将包含API Key的配置文件提交到公开仓库
2. **Token消耗**：注意控制 max_tokens 参数，避免不必要的token消耗
3. **请求频率**：遵守API调用频率限制，避免被限流
4. **内容审核**：AI生成的内容需要人工审核，确保符合平台规范
5. **成本控制**：不同模型的定价不同，根据需求选择合适的模型

## 示例配置

```yaml
ai:
  qwen:
    api_key: "sk-xxxxxxxxxxxxxxxxxxxxx"
    api_endpoint: "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    model: "qwen-turbo"
    temperature: 0.7
    max_tokens: 2000
    timeout: 30
    enable: true
```

## 更多信息

- [通义千问官方文档](https://help.aliyun.com/zh/model-studio/)
- [DashScope控制台](https://dashscope.console.aliyun.com/)
- [API参考文档](https://help.aliyun.com/zh/model-studio/developer-reference/api-details-9)

