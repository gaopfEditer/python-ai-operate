# task-os「实时关注」同步

将本机 **推特 / 币安广场信号**、**CDP 与控制台发布**、**Bitget 自动下单**、**vpn_guard 状态** 增量写入 [task-os](https://github.com/gaopfEditer/task-os) 的 `data/live_watch.json`，由看板 **「实时关注」** 页展示。

## 时点（Asia/Shanghai）

| 时刻 | 内容 |
|------|------|
| 0 / 8 / 12 / 16 / 20 | 信号时段汇总、发布汇总、Bitget |
| 12 / 20 | 额外一条 VPN 汇总 |

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
- 每个窗口只写 **一条** 汇总，`id` 形如 `sig:summary:12:2026-11-17`，`category` 仍为 `signal`。
- 标题例：`信号汇总 · 08:00–12:00 · 4 条`。没有符合条件的信号时正文就是「本时段无信号」。读库失败时标题写「读取失败」，不会写成无信号。
- 数据源仍是 `output/signals/cards.db`，按 `updated_at` / `parsed_at` 或 `created_at` 落在窗口内。征集可以继续实时跑，只是不再把单条 `sig:binance_square:…` 写入 live_watch。
- 纳入范围与原来一致：`important: true` 的账号，或已解析成交易信号（有币种且方向为做多/做空）。
- 正文每条一行：时间、来源（推特 / 币安广场）、账号展示名（配置里的 channelName / name，例如禹柔）、方向、一行摘要，下一行是链接。
- `meta`：`count`、`window_start`、`window_end`、`items`（`source` / `account` / `direction` / `summary` / `url` / `ts`）。
- 已经写进 `live_watch.json` 的逐条信号不会删除。`id` 相同的条目不会重复写入。

## 发布

每个窗口一条，`id` 形如 `pub:summary:12:2026-11-17`。

- 有发布时标题为 `发布 · 成功 3 / 失败 1`。正文逐条写平台、标题、链接、成功或失败原因、时间。
- `meta.success_count`、`meta.fail_count`、`meta.items`（`name` / `ok` / `error` / `time`，并带上 `title` / `url`）。
- 数据源：`output/publish_logs/publish_YYYY-MM-DD.log` 的 `platform_ok` / `platform_fail` / `cdp_connect_fail`（同一 `job_id` 的 `run_end` 只在没有逐平台记录时用来计数），以及 `output/publish_history.db` 里窗口内的非草稿记录（`title`、`results_json` 的 `platform` / `name` / `success` / `error` / `url`）。同一任务的日志和历史库会合并，不用历史库里的「成功」盖掉日志里的失败。
- 日志文件不存在时先查 `publish_history.db`。历史库有记录就按记录写，并注明日志文件缺失。
- 两边都读过且窗口内没有发布：标题 `发布 · 当日无发布记录`。
- 日志文件不存在，历史库也不存在或读失败：标题 `发布 · 发布日志缺失`，`success_count` 为 0，正文说明不能判断成败、不记为成功。不再只留一条本机绝对路径。

## Bitget

- 优先 `GET {collector_api_base}/api/discord/signal-cards`，从卡片 `parsed.bitgetOrder` 取窗口内自动下单。
- 回退：`discord-collector/data/bitget-order-history.json` 中非 `manual` 来源。

## VPN

仍只在 12 / 20 点写入一条，`id` 为 `vpn:{slot}:{date}`。

- `config/task_os_live_watch.yaml` 的 `vpn_state_json`（默认 `~/Library/Logs/vpn-guard/state.json`）和同目录 `vpn_log_dir` 里的 `*.json` / `*.jsonl` / `*.log`。
- 快照字段（有则用）：`last_health.ok`、`owner`、`node` / `current_node` / `node_name`、`client` / `current_client` / `app`、`ip` / `exit_ip` / `current_ip` / `public_ip`、`sites` / `site_status`、顶层 `fail_since`。
- 事件字段（有则用）：`event` / `type` / `kind`、`ts`、`reason`、`duration_sec`（或 `duration_minutes`、`down_at`+`up_at`）、`from_node`、`to_node`、`switched_clash`、`ok`。断开类：`disconnect` / `timeout` / `high_latency` / `断开` / `超时` / `高延迟`。切换类：`switch` / `切换`。重启类：`restart` / `重启`。站点名会归一成 ChatGPT、YouTube、X、币安广场。
- 按日汇总字段（没有逐条事件时才用来计数）：`disconnects`、`unstable_minutes`、`blocks`、`switch_success`，放在 `today` / `days` / `daily`。
- 标题例：`VPN Guard · OK · gsycloud · 断开20次 / 不稳定13.4分钟`。次数或时长算不出来就不写进标题。
- 正文用中文写截止时间（Asia/Shanghai）、断开与不稳定时长、当前客户端/节点/出口 IP、四站通断、断开分布、切换与是否切过 Clash、是否重启、节点时段、屏蔽后换到哪里、近三日同时段对比。没有的段落写「不可用」。
- `meta`：`ok`、`owner`、`disconnects`、`unstable_minutes`、`current_client`、`current_node`、`current_ip`、`site_status`、`switches`、`unavailable`。

## 自测

```bash
cd frontend/code/1.operations/python-ai-operate
python3 -m unittest tests.test_task_os_live_watch_sync -v
.venv/bin/python scripts/task_os_live_watch_sync.py --slot 12 --dry-run
```

`--dry-run` 只打印将写入的条目，不改 `live_watch.json`。正式写入发生在下一个 0/8/12/16/20 点；VPN 仍只在 12 点和 20 点。

Mac 上生效：在仓库拉取这段改动后，重启正在跑的 TrendRadar Console（调度器在 `python console.py` 进程里）。若还装了 launchd `com.maotouying.task-os-live-watch`，它每次整点会新开进程，拉完代码即可，不必 `launchctl` 重载。不要覆盖本机未提交的 `config/binance_square_signals.yaml`。