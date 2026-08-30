# 实时资讯预警 realtime_info

采集 → 过滤/防抖 →（可选 LLM）→ **本地审阅**。Telegram / X 默认关闭，先在 Console 看质量。

## 快速开始

```bash
# 1) Webhook + 轮询（OI/链上）
python realtime_info.py
# TradingView: POST http://127.0.0.1:8788/hooks/tradingview

# 2) Console 审阅台
python console.py
# 打开「资讯预警」Tab：待审列表 / 通过 / 丢弃 / 稍后再看
```

注入样例（Console 内点「注入 TV 样例」，或）：

```bash
curl -s -X POST http://127.0.0.1:8788/hooks/tradingview?skip_llm=1 \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"BTCUSDT","timeframe":"4H","side":"long","structure":"spring","message":"假跌破收回"}'
```

## 模块状态

| 模块 | 状态 | 说明 |
|------|------|------|
| D TV Webhook | 已实现 | 仅 1H/4H，同指纹 6h 防抖 |
| C OI/Funding | 已实现 | Binance 公开 REST |
| A 链上免费 | 已实现 | Etherscan + `entities.yaml`；无鲸鱼地址/无 API Key 则空跑打日志 |
| A Arkham | 空壳 | 后续可换成自有免费站爬虫 |
| B 清算 | 空壳 | 规则可单测 |
| E 解锁 | 空壳 | 规则可单测 |
| F KOL | 适配 | 需 CDP + `kol_watchlist.yaml` 启用账号 |
| Telegram / X | 空壳 | `settings.yaml` 里 `enabled: false` |

## 配置

- [`realtime_info/config/settings.yaml`](config/settings.yaml)
- [`realtime_info/config/entities.yaml`](config/entities.yaml) — 鲸鱼 / CEX 地址
- [`realtime_info/config/kol_watchlist.yaml`](config/kol_watchlist.yaml)
- 环境变量：`ETHERSCAN_API_KEY`（可选）

数据落在 `output/realtime_info/events.db`。

## 何时再开 Telegram

本地把一批事件标成 `approved`、草稿质量稳定后，再把 `telegram.enabled` 打开并实现 `bot/notify.py`。通过 ≠ 自动发推。

## 单测

```bash
python -m unittest realtime_info.tests.test_rules -v
```
