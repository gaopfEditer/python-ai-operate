# 信号抓取路径标签（fetch_source）

列表信号与币安 Square 在入库卡片时会写入 `fetch_source`，Console 卡片脚注会显示 `来源:cookie+api` 或 `来源:cdp`。

| 值 | 含义 |
|---|---|
| `cookie+api` | HTTP GraphQL（X）或 bapi（Square），Cookie 可能由 CDP **一次性**引导，但数据来自 API |
| `cdp` | CDP 页面滚动 / DOM 抽取回退 |

## 周期联调日志

每次 X 列表/KOL 实时或 Square 抓取结束，会追加一行 JSON 到：

`logs/signals_fetch_routes.jsonl`

字段说明（无 Cookie/Token 原文）：

- `platform`: `x_list` / `x_user` / `binance_square`
- `attempted_routes`: 本周期尝试过的路径
- `cookie_api`: `{ "ok": true/false, "reason": "..." }` — cookie+api 是否成功及失败原因摘要
- `final_fetch_source`: 本周期主要使用的路径
- `sample_count`: 样本条数（帖/推文）
- `items_by_fetch_source`（Square）: 各路径帖子计数

查看最近记录：

```bash
tail -n 20 logs/signals_fetch_routes.jsonl
```

联调 smoke 仍见 `docs/binance_square_realtime.md`（`SIGNALS_HTTP_SMOKE=1`）。
