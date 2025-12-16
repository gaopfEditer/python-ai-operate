# TrendRadar 工作流程说明

## 文件夹结构

项目已创建以下四个主要模块文件夹，每个模块都包含完整的提示词体系：

```
TrendRadar/
├── crawler/          # 爬虫模块
│   ├── global_prompt.txt      # 全局提示词
│   ├── platforms/             # 平台操作提示词文件夹
│   │   └── README.txt         # 平台提示词说明
│   └── main/                  # 主流程文件夹
│       └── main_prompt.txt    # 主流程提示词
│
├── create/           # 创作模块
│   ├── global_prompt.txt      # 全局提示词
│   ├── platforms/             # 平台操作提示词文件夹
│   │   └── README.txt         # 平台提示词说明
│   └── main/                  # 主流程文件夹
│       └── main_prompt.txt    # 主流程提示词
│
├── comment/          # 评论模块
│   ├── global_prompt.txt      # 全局提示词
│   ├── platforms/             # 平台操作提示词文件夹
│   │   └── README.txt         # 平台提示词说明
│   └── main/                  # 主流程文件夹
│       └── main_prompt.txt    # 主流程提示词
│
└── public/           # 发布模块
    ├── global_prompt.txt      # 全局提示词
    ├── platforms/             # 平台操作提示词文件夹
    │   └── README.txt         # 平台提示词说明
    └── main/                  # 主流程文件夹
        └── main_prompt.txt    # 主流程提示词
```

## 工作流程串联

### 完整流程

```
1. 爬虫模块 (crawler)
   ↓ 输出热点数据
   
2. 创作模块 (create)
   ↓ 输出创作内容
   
3. 发布模块 (public)
   ↓ 发布到各平台
   
4. 评论模块 (comment)
   ↓ 对重点文章进行评论
```

### 详细流程说明

#### 第一步：数据爬取 (crawler)
- **输入**：配置文件、目标平台列表
- **处理**：
  - 使用 `crawler/global_prompt.txt` 了解爬虫通用规则
  - 使用 `crawler/platforms/{platform}_prompt.txt` 获取平台特定规则
  - 使用 `crawler/main/main_prompt.txt` 执行完整爬取流程
- **输出**：结构化的热点数据（JSON格式）

#### 第二步：内容创作 (create)
- **输入**：来自爬虫模块的热点数据
- **处理**：
  - 使用 `create/global_prompt.txt` 了解创作通用规则
  - 使用 `create/platforms/{platform}_prompt.txt` 获取平台内容格式要求
  - 使用 `create/main/main_prompt.txt` 执行完整创作流程
- **输出**：高质量原创内容（包含标题、正文、标签等）

#### 第三步：内容发布 (public)
- **输入**：来自创作模块的内容
- **处理**：
  - 使用 `public/global_prompt.txt` 了解发布通用规则
  - 使用 `public/platforms/{platform}_prompt.txt` 获取平台发布规则
  - 使用 `public/main/main_prompt.txt` 执行完整发布流程
- **输出**：发布链接、发布状态、数据统计

#### 第四步：评论互动 (comment)
- **输入**：来自爬虫模块的重点文章列表
- **处理**：
  - 使用 `comment/global_prompt.txt` 了解评论通用规则
  - 使用 `comment/platforms/{platform}_prompt.txt` 获取平台评论规则
  - 使用 `comment/main/main_prompt.txt` 执行完整评论流程
- **输出**：评论链接、评论效果数据

## 提示词文件使用指南

### 全局提示词 (global_prompt.txt)
- **用途**：定义模块的通用规则、核心功能和输入输出要求
- **使用时机**：模块初始化时加载，作为基础规则

### 平台提示词 (platforms/{platform}_prompt.txt)
- **用途**：定义特定平台的操作规则和格式要求
- **使用时机**：处理特定平台任务时加载
- **创建方式**：根据实际需要创建，如 `weibo_prompt.txt`、`zhihu_prompt.txt` 等

### 主流程提示词 (main/main_prompt.txt)
- **用途**：定义完整的业务流程，包括步骤、集成点和错误处理
- **使用时机**：执行完整流程时使用，串联各个步骤

## 后续开发建议

1. **平台提示词扩展**
   - 在 `platforms/` 文件夹中为每个目标平台创建具体的提示词文件
   - 参考 `README.txt` 中的命名规范和文件结构

2. **流程优化**
   - 根据实际运行情况，优化各模块的 `main_prompt.txt`
   - 添加更多的错误处理和重试机制

3. **数据流转**
   - 定义统一的数据格式，确保模块间数据传递顺畅
   - 建立数据验证机制

4. **监控和日志**
   - 为每个模块添加日志记录
   - 建立流程监控机制，跟踪每个步骤的执行状态

## 使用示例

### 执行完整流程
```python
# 1. 爬取数据
from crawler.main import main as crawler_main
data = crawler_main()

# 2. 创作内容
from create.main import main as create_main
content = create_main(data)

# 3. 发布内容
from public.main import main as public_main
result = public_main(content)

# 4. 评论互动
from comment.main import main as comment_main
comment_main(data)
```

### 单独执行某个模块
```python
# 只执行爬虫模块
from crawler.main import main as crawler_main
crawler_main()
```

## 注意事项

- 所有提示词文件都是文本格式，便于AI读取和理解
- 可以根据实际需求修改和扩展提示词内容
- 建议定期更新提示词，优化流程效果
- 注意保护账号信息和敏感数据

