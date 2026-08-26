# X 工具箱 Chrome 插件

登录 X（Twitter）后，按日期批量清理推文 / 回复 / 转发 / 喜欢；在贴文详情页根据主贴与前几条评论 AI 生成回复。

## 功能

### 1. 批量清理（模拟站内 API）

- 自动拦截 X 页面 `fetch` / XHR，捕获 **Bearer Token、CSRF (ct0)、GraphQL queryId**
- 使用与 X 网页相同的 GraphQL 接口：
  - 原创 / 回复：`UserTweets` / `UserTweetsAndReplies`
  - 喜欢：`Likes`
  - 删除推文、取消转发、取消喜欢
- Popup 选择日期范围与类型 → **扫描预览** → **执行删除**（可设间隔防风控）

### 2. 评论助手（贴文详情页）

- 在 `x.com/*/status/*` 页面右下角显示 **💬** 浮钮
- 读取主贴 + 前 5 条回复作为上下文
- 调用 LLM（默认 Ollama `http://127.0.0.1:11434/v1`）生成多条候选
- 一键填入 X 回复框或复制

## 安装

1. Chrome 打开 `chrome://extensions/`
2. 开启 **开发者模式**
3. **加载已解压的扩展程序** → 选择 `tools/chrome-x-toolkit`
4. 若缺少图标，运行：
   ```bash
   cd tools/chrome-x-toolkit
   python generate_icons.py
   ```

## 使用

### 批量清理

1. 登录 [x.com](https://x.com)，随便刷几条时间线（让插件捕获 API 参数）
2. 点击插件图标 → **批量清理**
3. 选日期、勾选类型 → **扫描预览**
4. 确认列表后 → **执行删除**

> ⚠️ 删除不可恢复，建议先选 1 天小范围试跑。

### 评论生成

1. 打开任意贴文详情页（URL 含 `/status/数字`）
2. 点击右下角 **💬** → **生成评论**
3. 选择候选 → **填入回复框**

LLM 在 Popup ⚙ 设置里配置（与「评论角度助手」类似，Ollama 可留空 API Key）。

## 原理说明

| 模块 | 作用 |
|------|------|
| `inject.js` | MAIN world 钩子，捕获 Authorization / x-csrf-token / queryId |
| `x-api.js` | 用捕获凭据调用 GraphQL |
| `batch-overlay.js` | 扫描与删除进度浮层 |
| `comment-panel.js` | 详情页评论 UI |
| `background.js` | LLM 请求 |

GraphQL 的 **queryId 会随 X 更新变化**。插件优先使用你浏览时捕获到的 ID；内置 ID 仅作兜底，失效时多刷新 X 各页面即可重新捕获。

## 与 discord-collector Mock 的关系

本插件 **不依赖** 3851 Cards API；批量清理走 X 官方网页 API。  
若需测试 Cards 回测 UI，请用控制台信号页的 **Mock 静态样例 / Mock 验证任务**。

## 文件结构

```
chrome-x-toolkit/
├── manifest.json
├── inject.js          # API 参数捕获
├── x-api.js           # GraphQL 客户端
├── content.js         # 注入与消息
├── batch-overlay.js   # 批量清理 UI
├── comment-panel.js   # 评论助手 UI
├── background.js      # LLM
├── popup.html/js/css
├── panel.css
└── icons/
```

## 常见问题

**Q: 提示「未捕获 Bearer」？**  
A: 确认已登录 X，刷新首页并滚动时间线，再打开 Popup 看凭据状态。

**Q: GraphQL 返回 404 / queryId 错误？**  
A: X 更新了接口。打开「个人主页 / 喜欢」等页面让插件重新捕获 queryId。

**Q: 评论生成失败？**  
A: 检查 Ollama 是否运行：`curl http://127.0.0.1:11434/v1/models`
