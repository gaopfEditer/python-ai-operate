# 币安 Square 实时抓取（bapi + Cookie）

## 路径

- 后台：`signals/binance_square/cycle_watcher.py` → `run_binance_square_fetch(realtime_incremental=True)`
- 默认 **博主主页 bapi 分页**，不依赖 CDP 滚动
- **Cookie 主路径**：每次抓取（或短 TTL 内）从已登录 Chrome **远程调试** 读取 `binance.com` Cookie，立即调用 bapi；**无需**先跑 bootstrap 脚本
- 可选 `output/signals/binance_square_session.json` 仅作 **指纹头补充**（`device-info` 等）或 CDP 不可用时的回退
- CDP 滚动仅回退：`BINANCE_SQUARE_USE_CDP=1` 或 bapi 完全无数据且未设 `BINANCE_SQUARE_API_ONLY=1`

## 用户只需

1. Chrome 用 `--remote-debugging-port=9223`（或与 `config/binance_square_signals.yaml` / 控制台 CDP 一致的端口）启动，**保持已登录 binance.com**（建议曾打开过 Square 时间线）。
2. `python console.py` → 列表信号 → 币安广场，开 **周期抓取** 或 **实时 · 立即抓取**。

日志示例：

- `Square 会话：已从 CDP（127.0.0.1:9223）读取 Cookie（N 项），立即走 bapi`
- `Square 实时：跳过热榜，仅抓配置博主 bapi`
- `命中已存帖，停止翻页`
- `原文已入库 … 信号解析排队中（后台）`
- `bapi 补全发帖时间（detail firstReleaseTime）`

若 CDP 失败：

- `Square 会话：CDP（…）读取失败 — …`（不会打印 Cookie 值）
- 随后尝试本地 session 文件 / `BNC_CSRF`、`BNC_UUID` 环境变量

## 抓取路径标签与周期日志

卡片字段 `fetch_source`（`cookie+api` | `cdp`）与每轮抓取 JSONL 日志说明见 [signals_fetch_routes.md](./signals_fetch_routes.md)。

## X / 列表信号（同一机制）

- 抓取开始时从 CDP 读取 `x.com` 的 **auth_token + ct0**；GraphQL 调用前会尝试从已打开标签的 `sessionStorage` / `performance` 捕获 **queryId**，不足时在后台 **导航到列表/首页** 等待 live 请求（不依赖仅内置默认 id）
- 若仍无 queryId：在 Chrome **打开 X 首页、列表或博主页** 让页面发 GraphQL 请求后重跑（或安装 `tools/chrome-x-toolkit` 扩展）
- 出站 HTTP 默认代理顺序 **7891 → 7890**（Mac Clash mixed-port 常见为 7891）；可设 `AI_OPERATE_HTTP_PROXIES=http://127.0.0.1:7891`；短暂 SSL/连接失败会有界重试
- 可选 `output/signals/x_api_session.json` 补充缺失 queryId 或作回退
- 信号 **LLM 解析默认后台队列**，不阻塞抓取（`SIGNALS_BLOCKING_LLM=1` 恢复同步）
- `SIGNALS_X_USE_CDP=1` 强制滚动回退

## 联调 smoke（可选）

```bash
export SIGNALS_HTTP_SMOKE=1
export SMOKE_BS_PROFILE=yanchibit   # config 里启用的博主 id
python scripts/smoke_signals_http.py
```

需本机 Chrome 远程调试已登录；**不要**把 session 文件提交 git。

## 环境变量

| 变量 | 含义 |
|------|------|
| `SIGNALS_SESSION_CDP_TTL` | CDP Cookie 内存缓存秒数（默认 `120`；`0` = 每次抓取都读 CDP） |
| `SIGNALS_SESSION_CDP_DISABLE=1` | 禁用运行时 CDP，仅用文件/环境变量 |
| `BINANCE_SQUARE_SESSION_FILE` | 可选指纹/回退 session 路径 |
| `BNC_CSRF` / `BNC_UUID` | 临时覆盖 cookie |
| `SIGNALS_BLOCKING_LLM=1` | 恢复抓取循环内同步 LLM（默认关闭=后台队列） |
| `SIGNALS_ANALYZE_TIMEOUT` | 后台单条 AI 上限秒数（默认 `25`） |
| `SIGNALS_ANALYZE_CONCURRENCY` | 信号解析并发（默认 `2`，最大 `4`） |
| `BINANCE_SQUARE_API_ONLY=1` | 禁止 CDP 回退 |
| `X_COOKIES_FILE` / `X_AUTH_TOKEN` / `X_CT0` | X 回退会话 |
| `SIGNALS_X_USE_CDP=1` | 强制 X CDP 滚动 |

## 可选工具（非必需流程）

`scripts/bootstrap_binance_session_from_cdp.py` / `bootstrap_x_session_from_cdp.py` 仍可将 Cookie **写入本地文件** 供离线或补充指纹头；正常运行 Console **不需要**执行它们。
