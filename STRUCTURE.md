# 项目结构说明

## 目录结构

```
TrendRadar/
├── index.py                 # 主入口文件，启动所有功能
├── crawler.py               # 爬虫模块入口（仅调用 crawler/index.py）
├── create.py                # 创作模块入口（仅调用 create/index.py）
├── comment.py               # 评论模块入口（仅调用 comment/index.py）
├── publish.py               # 发布模块入口（仅调用 public/index.py）
│
├── main/                    # 调度器目录
│   ├── __init__.py
│   └── scheduler.py         # 工作流调度器，串联所有模块
│
├── crawler/                 # 爬虫模块
│   ├── __init__.py
│   ├── index.py             # 爬虫核心功能（从 crawler.py 移过来）
│   ├── global_prompt.txt    # 全局提示词
│   ├── main/
│   │   └── main_prompt.txt  # 主流程提示词
│   └── platforms/           # 平台操作提示词文件夹
│       └── README.txt
│
├── create/                  # 创作模块
│   ├── __init__.py
│   ├── index.py             # 创作核心功能
│   ├── global_prompt.txt    # 全局提示词
│   ├── main/
│   │   └── main_prompt.txt  # 主流程提示词
│   └── platforms/           # 平台操作提示词文件夹
│       └── README.txt
│
├── comment/                 # 评论模块
│   ├── __init__.py
│   ├── index.py             # 评论核心功能
│   ├── global_prompt.txt    # 全局提示词
│   ├── main/
│   │   └── main_prompt.txt  # 主流程提示词
│   └── platforms/           # 平台操作提示词文件夹
│       └── README.txt
│
├── public/                  # 发布模块
│   ├── __init__.py
│   ├── index.py             # 发布核心功能
│   ├── global_prompt.txt    # 全局提示词
│   ├── main/
│   │   └── main_prompt.txt  # 主流程提示词
│   └── platforms/           # 平台操作提示词文件夹
│       └── README.txt
│
├── utils/                   # 工具模块
│   ├── __init__.py
│   └── ai_client.py         # AI客户端（千问）
│
└── config/                  # 配置文件
    └── config.yaml          # 主配置文件
```

## 设计原则

### 1. 入口文件（根目录）
- `index.py`: 主入口，可以启动所有功能
- `crawler.py`, `create.py`, `comment.py`, `publish.py`: 各模块的入口文件，仅作为入口调用模块内的 `index.py`

### 2. 核心功能（模块目录）
- 每个模块的真实功能都在各自的 `index.py` 中
- 例如：`create/index.py` 包含所有创作相关的核心功能

### 3. 调度器（main目录）
- `main/scheduler.py`: 工作流调度器，用于串联爬取、创建、发布、评论等流程
- 可以单独执行某个模块，也可以执行完整工作流

## 使用方式

### 1. 使用主入口（推荐）

```bash
# 执行完整工作流（爬取 -> 创建 -> 发布）
python index.py --mode full

# 仅执行爬虫
python index.py --mode crawler

# 仅执行创作
python index.py --mode create

# 使用调度器（默认）
python index.py --mode scheduler

# 使用调度器，只执行指定模块
python index.py --mode scheduler --crawler --create
```

### 2. 使用各模块入口

```bash
# 执行爬虫模块
python crawler.py

# 执行创作模块
python create.py

# 执行评论模块
python comment.py

# 执行发布模块
python publish.py
```

### 3. 使用调度器

```python
from main.scheduler import WorkflowScheduler

scheduler = WorkflowScheduler()

# 执行完整工作流
results = scheduler.run_full_workflow(
    enable_crawler=True,
    enable_create=True,
    enable_public=True,
    enable_comment=False
)

# 单独执行某个模块
crawler_result = scheduler.run_crawler()
create_result = scheduler.run_create(hot_data)
```

### 4. 直接调用模块功能

```python
# 调用创作模块
from create.index import generate_content

hot_data = {
    'title': 'AI技术新突破',
    'content': '人工智能技术取得重大进展...',
    'keywords': ['AI', '技术']
}

result = generate_content(hot_data, platform='微博', content_type='微博')
```

## 工作流程

### 完整工作流

```
1. 爬虫模块 (crawler/index.py)
   ↓ 输出热点数据
   
2. 创作模块 (create/index.py)
   ↓ 输出创作内容
   
3. 发布模块 (public/index.py)
   ↓ 发布到各平台
   
4. 评论模块 (comment/index.py) [可选]
   ↓ 对重点文章进行评论
```

### 调度器流程

调度器 (`main/scheduler.py`) 负责：
- 按顺序执行各个模块
- 处理模块间的数据传递
- 记录执行日志
- 错误处理和重试

## 模块说明

### 爬虫模块 (crawler)
- **入口**: `crawler.py` → `crawler/index.py`
- **功能**: 从各平台抓取热点数据
- **输出**: 结构化的热点数据

### 创作模块 (create)
- **入口**: `create.py` → `create/index.py`
- **功能**: 基于热点数据生成原创内容
- **依赖**: 需要爬虫模块的输出
- **输出**: 创作的内容

### 发布模块 (public)
- **入口**: `publish.py` → `public/index.py`
- **功能**: 将创作的内容发布到各平台
- **依赖**: 需要创作模块的输出
- **输出**: 发布结果和链接

### 评论模块 (comment)
- **入口**: `comment.py` → `comment/index.py`
- **功能**: 对重点文章进行自动评论
- **依赖**: 需要爬虫模块的输出（文章列表）
- **输出**: 评论内容和链接

## 提示词文件

每个模块都包含提示词文件：
- `global_prompt.txt`: 全局提示词，定义模块的通用规则
- `main/main_prompt.txt`: 主流程提示词，定义完整业务流程
- `platforms/`: 平台特定提示词文件夹

这些提示词文件会被AI模型（千问）使用，用于生成内容和评论。

## 注意事项

1. **路径问题**: 所有模块的 `index.py` 都需要正确设置项目根目录路径
2. **导入问题**: 使用相对导入时，确保 `__init__.py` 文件存在
3. **数据传递**: 模块间的数据传递需要在调度器中实现
4. **错误处理**: 每个模块都应该有完善的错误处理机制

## 后续开发

- [ ] 完善模块间的数据传递机制
- [ ] 添加数据持久化（数据库或文件）
- [ ] 实现定时任务调度
- [ ] 添加监控和日志系统
- [ ] 完善错误处理和重试机制

