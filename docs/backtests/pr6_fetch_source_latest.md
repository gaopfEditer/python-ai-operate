# PR#6 回测：卡片拉取路径 `cookie+api` vs `cdp`

- 时间（Asia/Hong_Kong）: 2026-11-03T09:33:26.854063+08:00
- debugger: `127.0.0.1:9223`
- X list: `2088443239435215337` / Square profile: `@yanchibit`
- 约定: `cookie+api` = Cookie + HTTP(GraphQL/bapi)；`cdp` = 页面 CDP 抓取。
- 网络: CDP 直连 localhost；API 走 `http://127.0.0.1:7891`。

| platform | fetch_source | ok | count | post.source | routes | detail |
|---|---|---|---|---|---|---|
| x | `cookie+api` | False | 0 | - | x_api | route=x_api err=ListLatestTweetsTimeline HTTP 401: {"errors":[{"message":"Could not authenticate you","code":32}]}
 |
| x | `cdp` | True | 2 | - | - | keys=['success', 'list_id', 'url', 'items', 'count', 'page_seen', 'page_old'] err=None |
| binance_square | `cookie+api` | False | None | - | - | exception: HTTP 400: {"code":"000002","message":"参数非法","messageDetail":null,"data":null,"success":false} |
| binance_square | `cdp` | True | 53 | bapi_profile | profile_cdp | keys=['success', 'aborted', 'posts', 'cards_sync', 'new_count', 'parse_queued', 'skipped_known', 'total', 'routes', 'profiles', 'profile_stats', 'backfill_range', 'cutoff_hours', 'message'] err=None |

## 卡片标注缺口

- 帖子层: `source` 已有 `bapi_profile` / `profile_cdp` / `x_api` 等。
- 卡片层: `source_mode` 仍是业务模式（`list_realtime` / `binance_square`），未标 `cookie+api`|`cdp`。
- 建议: 卡片增加 `fetch_source`（或并入 `source_modes`），控制台显示「来源」。

## raw JSON

```json
[
  {
    "platform": "x",
    "fetch_source": "cookie+api",
    "ok": false,
    "count": 0,
    "detail": "route=x_api err=ListLatestTweetsTimeline HTTP 401: {\"errors\":[{\"message\":\"Could not authenticate you\",\"code\":32}]}\n",
    "sample_sources": [],
    "routes": [
      "x_api"
    ],
    "at": "2026-11-03T01:28:54.036823+00:00"
  },
  {
    "platform": "x",
    "fetch_source": "cdp",
    "ok": true,
    "count": 2,
    "detail": "keys=['success', 'list_id', 'url', 'items', 'count', 'page_seen', 'page_old'] err=None",
    "sample_sources": [
      ""
    ],
    "routes": [],
    "at": "2026-11-03T01:33:26.845251+00:00"
  },
  {
    "platform": "binance_square",
    "fetch_source": "cookie+api",
    "ok": false,
    "count": null,
    "detail": "exception: HTTP 400: {\"code\":\"000002\",\"message\":\"参数非法\",\"messageDetail\":null,\"data\":null,\"success\":false}",
    "sample_sources": [],
    "routes": [],
    "at": "2026-11-03T01:28:56.759468+00:00"
  },
  {
    "platform": "binance_square",
    "fetch_source": "cdp",
    "ok": true,
    "count": 53,
    "detail": "keys=['success', 'aborted', 'posts', 'cards_sync', 'new_count', 'parse_queued', 'skipped_known', 'total', 'routes', 'profiles', 'profile_stats', 'backfill_range', 'cutoff_hours', 'message'] err=None",
    "sample_sources": [
      "bapi_profile"
    ],
    "routes": [
      "profile_cdp"
    ],
    "at": "2026-11-03T01:32:03.800268+00:00"
  }
]
```

## 解读（本轮实测）

1. **cookie+api 均失败**（印证你的判断）  
   - X：CDP 已能读到 `auth_token/ct0`，但 GraphQL 列表返回 **401 Could not authenticate you**（缺有效 queryId / 会话与 API 不完全匹配）。  
   - Square：会话 ready（有 cookie、无指纹头），bapi **HTTP 400 参数非法**。

2. **cdp 可兜底**  
   - X：`SIGNALS_X_USE_CDP=1` 从列表页滚到 **2** 条，成功。  
   - Square：本轮深滚 **0** 条，但 `run_binance_square_fetch` 仍返回 `routes=["profile_cdp"]` 且 `sample_sources=["bapi_profile"]`、count=53 —— **来源字段互相打架**，53 更像库存/合并结果，不能当成本轮 CDP 新抓数。这正是卡片必须单独标 `fetch_source=cdp|cookie+api` 的原因。

3. **网络注意**  
   - CDP（localhost）必须绕开系统 SOCKS；对外 API 必须走 `127.0.0.1:7891`，否则 SSL EOF。

4. **产物**  
   - 回测脚本：`scripts/backtest_pr6_fetch_source.py`  
   - 报告：`docs/backtests/pr6_fetch_source_latest.md`

