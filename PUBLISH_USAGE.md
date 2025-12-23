# 发布模块使用说明

## 功能说明

发布模块支持使用Selenium自动化浏览器操作，将文章发布到各个平台。目前已支持Typecho平台。

## 配置说明

### 1. 安装依赖

```bash
pip install selenium
```

### 2. 安装Chrome浏览器和ChromeDriver

- 安装Chrome浏览器
- 下载对应版本的ChromeDriver：https://chromedriver.chromium.org/
- 将ChromeDriver添加到系统PATH，或放在项目目录下

### 3. 配置文件

在 `config/config.yaml` 中配置发布平台：

```yaml
publish:
  enable: true  # 是否启用发布功能
  default_platforms: "typecho"  # 默认发布的平台（用逗号分隔）
  headless: false  # 是否使用无头模式（不显示浏览器）
  wait_timeout: 10  # 浏览器等待超时时间（秒）
  
  platforms:
    - id: "typecho"
      name: "Typecho博客"
      type: "typecho"
      login_url: "https://easycoin.gaopf.top/admin/"
      write_url: "https://easycoin.gaopf.top/admin/write-post.php"
      username: "admin"
      password: "1245@qq.com"
      enabled: true  # 是否启用此平台
```

## 使用方式

### 方式一：使用命令行

#### 从文件发布

```bash
# 发布Markdown文件到默认平台
python publish.py --file output/articles/Vue3与Vue2响应式原理_20251216_095448.md

# 发布到指定平台
python publish.py --file output/articles/article.md --platforms typecho

# 发布并添加标签
python publish.py --file output/articles/article.md --tags "Vue,前端,技术"
```

#### 直接指定内容

```bash
python publish.py --title "文章标题" --content "文章内容" --platforms typecho
```

#### 列出所有平台

```bash
python publish.py --list
```

### 方式二：使用Python代码

```python
from public.index import publish_content

# 发布到默认平台
result = publish_content({
    'title': '前端Vue3与Vue2响应式区别和底层原理',
    'content': '文章内容...'
})

# 发布到指定平台
result = publish_content(
    content={
        'title': '前端Vue3与Vue2响应式区别和底层原理',
        'content': '文章内容...'
    },
    platform_ids=['typecho'],
    tags='Vue,前端,技术'
)

# 查看结果
if result['success']:
    for r in result['results']:
        if r['success']:
            print(f"发布成功: {r['url']}")
        else:
            print(f"发布失败: {r['error']}")
```

### 方式三：在调度器中使用

```python
from main.scheduler import WorkflowScheduler
from create.index import generate_article_by_topic
from public.index import publish_content

# 生成文章
result = generate_article_by_topic(
    topic="前端Vue3与Vue2响应式区别和底层原理",
    word_count=3000
)

if result['success']:
    # 发布文章
    publish_result = publish_content(
        content={
            'title': '前端Vue3与Vue2响应式区别和底层原理',
            'content': result['content']
        },
        platform_ids=['typecho'],
        tags='Vue,前端,技术'
    )
```

## 平台配置

### 添加新平台

1. 在 `public/platforms/` 目录下创建平台发布器（如 `weibo_publisher.py`）
2. 实现发布器的 `publish` 方法
3. 在 `config/config.yaml` 中添加平台配置

### 多平台发布

可以同时发布到多个平台：

```yaml
publish:
  default_platforms: "typecho,weibo,zhihu"  # 多个平台用逗号分隔
```

```python
publish_content(
    content={'title': '...', 'content': '...'},
    platform_ids=['typecho', 'weibo', 'zhihu']
)
```

## 返回结果格式

```python
{
    'success': True,  # 是否至少有一个平台发布成功
    'total': 1,  # 总平台数
    'success_count': 1,  # 成功发布的平台数
    'results': [
        {
            'platform': 'typecho',
            'platform_name': 'Typecho博客',
            'success': True,
            'url': 'https://easycoin.gaopf.top/archives/123/',
            'title': '文章标题',
            'error': ''
        }
    ]
}
```

## 注意事项

1. **ChromeDriver版本**：确保ChromeDriver版本与Chrome浏览器版本匹配
2. **网络连接**：需要稳定的网络连接访问目标平台
3. **登录状态**：每次发布都会重新登录，确保账号密码正确
4. **无头模式**：如果不需要看到浏览器，可以设置 `headless: true`
5. **等待时间**：如果页面加载较慢，可以增加 `wait_timeout` 配置
6. **错误处理**：发布失败时会返回详细错误信息，便于排查问题

## 故障排查

### 问题1：找不到ChromeDriver

**解决方案**：
- 下载对应版本的ChromeDriver
- 将ChromeDriver添加到系统PATH
- 或在代码中指定ChromeDriver路径

### 问题2：登录失败

**解决方案**：
- 检查账号密码是否正确
- 检查登录URL是否正确
- 检查网络连接是否正常
- 查看浏览器控制台的错误信息

### 问题3：找不到输入框或按钮

**解决方案**：
- Typecho发布器使用了多种选择器策略，会自动尝试
- 如果仍然失败，可能需要根据实际页面结构调整选择器
- 可以设置 `headless: false` 查看浏览器操作过程

### 问题4：内容发布不完整

**解决方案**：
- 检查内容是否过长
- 检查富文本编辑器的处理逻辑
- 可能需要调整内容格式

## 扩展开发

### 创建新的平台发布器

1. 在 `public/platforms/` 目录下创建新文件（如 `weibo_publisher.py`）
2. 实现发布器类，参考 `TypechoPublisher` 的实现
3. 在 `public/index.py` 中添加平台类型的处理逻辑
4. 在配置文件中添加平台配置

示例：

```python
class WeiboPublisher:
    def __init__(self, username, password):
        self.username = username
        self.password = password
    
    def publish(self, title, content):
        # 实现发布逻辑
        pass
```







