# task-os「实时关注」同步

将本机 **推特 / 币安广场信号**、**CDP 与控制台发布**、**Bitget 自动下单**、**vpn_guard 状态** 增量写入 [task-os](https://github.com/gaopfEditer/task-os) 的 `data/live_watch.json`，由看板 **「实时关注」** 页展示。

## 时点（Asia/Shanghai）

| 时刻 | 内容 |
|------|------|
| 0 / 8 / 12 / 16 / 20 | 信号、发布、Bitget |
| 12 / 20 | 额外一条 VPN 状态 |

## 运行

```bash
cd frontend/code/1.operations/python-ai-operate
.venv/bin/python scripts/task_os_live_watch_sync.py
.venv/bin/python scripts/task_os_live_watch_sync.py --slot 12
.venv/bin/python scripts/task_os_live_watch_sync.py --dry-run
.venv/bin/python scripts/task_os_live_watch_sync.py --push   # 写 JSON 后 git commit + push task-os
```

配置：`config/task_os_live_watch.yaml`（路径、API、是否 `git_push`）。

## Console 内置（推荐）

启动 **TrendRadar Console**（`python -m console.app` 或你平时的启动方式）后，会按 `config/task_os_live_watch.yaml` 的 `scheduler_enabled: true` 在 **0 / 8 / 12 / 16 / 20** 自动同步；`git_push: true` 时写完后 push `task-os`。

**列表信号**页右上角 **「推送看板」**：立即按当前档位增量同步并 push（不必等整点）。

## 命令行 / launchd（可选）

```bash
.venv/bin/python scripts/task_os_live_watch_sync.py --push
bash scripts/install_task_os_live_watch_launchd.sh
```

VPN 仅在 12 / 20 槽写入。

## 信号规则

- 增量窗口：上一档定时点 → 当前档（例如 12 点跑时统计 8:00–12:00）。
- 数据源：`output/signals/cards.db`，按 `updated_at` / `created_at_ts` 落在窗口内。
- **重点关注**：`config/signals_channels.yaml` 与 `config/binance_square_signals.yaml` 中 `important: true` 的账号；条目带 AI/规则 `signal.summary`，交易向卡片附带币种与方向。
- 去重：条目 `id` 稳定，已存在于 `live_watch.json` 的不会重复写入。

## 发布

- `output/publish_logs/publish_*.log` 内 `platform_ok` / `platform_fail` / `run_end` 等。
- `output/publish_history.db` 中 `created_at` 在窗口内的记录（含 auto-script 经 `trade-signal/publish` 触发的 CDP 任务）。

## Bitget

- 优先 `GET {collector_api_base}/api/discord/signal-cards`，从卡片 `parsed.bitgetOrder` 取窗口内自动下单。
- 回退：`discord-collector/data/bitget-order-history.json` 中非 `manual` 来源。

## VPN

- 读取 `~/Library/Logs/vpn-guard/state.json`（`vpn_guard.py --status` 同款文件），生成可读摘要。