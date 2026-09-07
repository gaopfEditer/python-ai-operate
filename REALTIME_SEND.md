# 实时发送 CLI

`realtime_send.py` 提供命令行界面的「实时发送」功能：从 `news_mornitor` 获取事件列表 → 交互选择 → AI 生成摘要 → CDP 推送到指定平台。

---

## 快速开始

```bash
# Windows PowerShell（推荐加 -X utf8 正常显示中文）
python -X utf8 realtime_send.py

# Linux / macOS
python realtime_send.py
```

---

## 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--list` | 只列出事件，不发送 | - |
| `--send N` | 直接发送第 N 条（列完自动进入确认） | - |
| `--channel` | news_mornitor 频道过滤，如 `twitter`、`huxiu` | `all` |
| `--min-star` | 最低星级过滤 | `1` |
| `--limit` | 最多获取事件数 | `30` |
| `--platform` | 指定平台，逗号分隔；省略则交互选择 | 交互 |
| `--cdp` | CDP 调试地址 | `127.0.0.1:9223` |
| `--text` | 直接指定发布文本，跳过 AI 摘要 | AI 摘要 |
| `--dry-run` | CDP 填完内容后不点发布（预览） | - |
| `--wait N` | 发布前等待 N 秒（适合定时场景） | `0` |

---

## 常用场景

### 查看事件列表

```bash
# 查看所有频道
python -X utf8 realtime_send.py --list

# 只看 twitter 频道、星级 >= 3
python -X utf8 realtime_send.py --list --channel twitter --min-star 3

# 最多返回 10 条
python -X utf8 realtime_send.py --list --limit 10
```

### 交互式发送

```bash
# 列出事件后，交互选择要发送的条目和平台
python -X utf8 realtime_send.py

# 列出后直接发送第 3 条（平台交互选择）
python -X utf8 realtime_send.py --send 3
```

### 一键发送（无需交互）

```bash
# 发送第 3 条到 OKX
python -X utf8 realtime_send.py --send 3 --platform okx

# 同时发到多个平台
python -X utf8 realtime_send.py --send 3 --platform okx,binance_square

# 指定文本、跳过 AI 摘要
python -X utf8 realtime_send.py --send 3 --platform okx --text "BTC 突破 10 万！"

# 预览模式（CDP 填完不点发布）
python -X utf8 realtime_send.py --send 3 --platform okx --dry-run
```

### 定时场景

```bash
# 等待 60 秒后发送（配合 cron / Windows 任务计划程序）
python -X utf8 realtime_send.py --send 1 --platform okx --wait 60
```

---

## 平台说明

| 平台 ID | 显示名 | 说明 |
|---------|--------|------|
| `okx` | OKX星球 | `https://www.okx.com/cn/orbit` |
| `binance_square` | 币安广场 | `https://www.binance.com/zh-CN/square` |
| `x_cdp` | X (Twitter) | `https://x.com/compose/post` |

> `x` 与 `x_cdp` 等效，内部统一映射为 `x_cdp`。

### 平台来源优先级

1. **优先**：`config/config.yaml` → `publish.default_platforms`（逗号分隔）
2. **退而**：`config/config.yaml` → `publish.platforms` 中 `enabled: true` 的条目
3. **均无**：交互询问

---

## 前置条件

### 1. news_mornitor 服务

```bash
# 启动 news_mornitor（默认端口 8770）
python -m allnews_mornitor

# 已启动后，需执行至少一次抓取（在界面点「抓取」或触发 scheduler）
```

> 若 news_mornitor 未启动，CLI 会报 `[!] No events fetched` 并退出。

### 2. Chrome CDP 会话

CDP 发布需要 Chrome 以**远程调试模式**启动，并已登录目标平台：

```bash
# macOS 示例
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9223 \
  --user-data-dir="$HOME/chrome-cdp-profile"

# Windows 示例
# chrome.exe --remote-debugging-port=9223 --user-data-dir="D:\chrome-cdp-profile"
```

> CLI 默认连接 `127.0.0.1:9223`，可用 `--cdp` 改地址。

### 3. AI（可选，省略则用原始描述）

摘要生成依赖 `utils.ai_client`（DeepSeek / Ollama / Qwen），`config.yaml` 中配置后自动使用。不可用时自动回退到 `description` 字段前 300 字。

---

## 输出日志示例

```
============================================================
  实时发送 CLI
============================================================

  从 http://127.0.0.1:8770 获取事件（频道=all，星级>=1）...
  WARNING  v1/events 返回 503，尝试 batch/last
  INFO     从 batch/last 获取 5 条

  共 5 条事件：

  [ 1] *   twitter        [bullish] 特朗普发推表示支持加密...
       BTC 再度走强，突破关键阻力位...

  ...

  正在生成摘要（AI）...

  摘要预览：
  --------------------------------------------------
  BTC 再度走强，突破关键阻力位...
  --------------------------------------------------

  确认发布？直接回车确认，输入新文本替换：

  CDP: 127.0.0.1:9223
  Dry-run: False

  ------------------------------------------------------------
  开始发布...

  INFO     -> 发布到 OKX星球 (okx) ...
  INFO         [OK] OKX星球
                https://www.okx.com/cn/orbit/post/xxx

  ------------------------------------------------------------
  结果：1/1 成功

    [OK] success  OKX星球
```

---

## 与 Console UI 的关系

| | Console 实时发送 | CLI realtime_send.py |
|---|---|---|
| 数据源 | news_mornitor (:8770) | news_mornitor (:8770) |
| 摘要 | AI + 可手动编辑 | AI + 可手动编辑 / `--text` 直传 |
| 发送 | 队列 + 定时 | 直接发送 / `--wait` 定时 |
| 配图 | 前端 Gemini 生图 | 需提前生成，路径放 `--text` 外部 |
| 适用 | 人工审阅、少量多平台 | 定时任务、脚本集成、管道调用 |

两者共用 `public/platforms/` 下的同一个 CDP publisher 实现，逻辑完全一致。
