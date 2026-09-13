# CDP 发布 HTTP API

控制台对外提供的发布接口：外部传入**正文**和**图片（可多张）**，本机已登录的 Chrome（CDP）发到币安广场 / OKX / Bitget / Gate / X。

默认地址：`http://127.0.0.1:8787`  
跨网段调用请启动时加 `--host 0.0.0.0`，并用令牌。

```bash
python console.py --host 0.0.0.0 --port 8787
```

发布前请确认 Chrome 已用 `--remote-debugging-port=9222` 启动，并登录目标平台。同一时刻只会跑一个发布任务（CDP 串行）。

---

## 鉴权

`config/config.yaml` 的 `publish.api_token` 或环境变量 `PUBLISH_API_TOKEN`。

- **未配置**：不校验（只适合本机）
- **已配置**：请求必须带令牌，任选一种：

```http
Authorization: Bearer <token>
X-Publish-Token: <token>
```

或查询参数 `?token=<token>`。

---

## 平台 ID

| id | 名称 |
|---|---|
| `binance_square` | 币安广场 |
| `okx` | OKX 星球 |
| `bitget` | Bitget 洞察 |
| `gate` | Gate 广场 |
| `x` | X / Twitter |

不传 `platforms` 时，使用配置里的 `publish.default_platforms`。

```http
GET /api/v1/publish/platforms
```

```json
{
  "success": true,
  "platforms": [
    {"id": "gate", "name": "Gate 广场", "enabled": true, "type": "gate"}
  ]
}
```

---

## 发布 `POST /api/v1/publish`

正文或图片至少其一。默认**异步**：立刻返回 `job_id`，再轮询任务。

### 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `text` / `content` | string | 正文 |
| `title` | string | 可选。Bitget 会写入标题 |
| `platforms` | string[] 或逗号串 | 如 `["gate","okx"]` 或 `"gate,okx"` |
| `images` | 见下 | 多图：URL / Base64 / data URI |
| `media_files` | object[] | 与控制台相同：`{name, data_b64}` |
| `media_paths` | string[] | 本机已有文件的绝对路径 |
| `submit` | bool | 默认 `true`。`false` 只填不点发布 |
| `async` | bool | 默认 `true`。`false` 则阻塞直到发完 |
| `debugger_url` | string | 可选，默认配置 `127.0.0.1:9222` |
| `tags` | string | 可选 |

`images` 每一项可以是：

- `"https://example.com/a.png"`
- `{"url": "https://example.com/a.png"}`
- `{"name": "a.png", "data_b64": "<base64>"}`
- `"data:image/png;base64,..."`

最多 12 张，单张不超过 12MB。也可用 `multipart/form-data` 直接传文件，字段名 `images` / `image` / `files` / `media` 均可。

---

## 异步（推荐）

CDP 发布通常要几十秒，外部调用请用异步，避免 HTTP 超时。

```bash
curl -sS -X POST http://127.0.0.1:8787/api/v1/publish \
  -H "Content-Type: application/json" \
  -d '{
    "text": "正文内容",
    "platforms": ["gate"],
    "images": ["https://example.com/cover.png"]
  }'
```

响应：

```json
{
  "success": true,
  "job_id": "a1b2c3d4e5f6...",
  "status": "queued",
  "poll": "/api/v1/publish/jobs/a1b2c3d4e5f6..."
}
```

### 查询任务 `GET /api/v1/publish/jobs/{job_id}`

`job.status`：

- `queued` / `running`：进行中
- `done`：至少有一个平台成功，`job.result` 为发布结果
- `error`：失败，看 `job.message` 或 `job.result.error`

任务存在进程内存里，**重启控制台会丢**。

---

## 同步

适合本机脚本、超时设得很长的客户端。

```bash
curl -sS -X POST http://127.0.0.1:8787/api/v1/publish \
  -H "Content-Type: application/json" \
  -d '{
    "text": "正文内容",
    "platforms": ["okx", "gate"],
    "async": false,
    "submit": true,
    "images": [
      {"name": "1.png", "data_b64": "iVBORw0KGgoAAAANSUhEUgAA..."}
    ]
  }'
```

成功时 `success` 为 true，`results` 按平台列出。

---

## 表单上传文件

```bash
curl -sS -X POST http://127.0.0.1:8787/api/v1/publish \
  -F "text=正文内容" \
  -F "platforms=gate,binance_square" \
  -F "images=@/path/to/a.png" \
  -F "images=@/path/to/b.jpg"
```

---

## Python 示例

```python
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8787"
TOKEN = ""  # 若配置了 api_token 则填上


def api(method, path, data=None):
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


created = api("POST", "/api/v1/publish", {
    "text": "外部接口发一条",
    "platforms": ["gate"],
    "images": ["https://example.com/cover.png"],
})
job_id = created["job_id"]
while True:
    info = api("GET", f"/api/v1/publish/jobs/{job_id}")
    status = info["job"]["status"]
    if status in ("done", "error"):
        print(json.dumps(info, ensure_ascii=False, indent=2))
        break
    time.sleep(2)
```

---

## 返回约定

- 业务成败看 JSON 的 `success`，不要只看 HTTP 状态。
- 异步创建任务成功是 HTTP 200 + `job_id`，真正发没发出去要看任务的 `done` / `error`。
- 并发发布会返回 `429`：`另一个发布任务正在进行，请稍候再试`。
- 令牌错误：`401`。

---

## 注意

1. 本机 Chrome 必须已登录对应平台，接口本身不会帮你登录。
2. 会复用已打开的同站点页签，不会每个任务新开标签。
3. 图片会先落到 `output/publish_cache/`，再交给 CDP。
4. 旧接口 `POST /api/publish` 仍给控制台用；外部请走 `/api/v1/publish`。

---

## 交易信号一键发布 `POST /api/v1/trade-signal/publish`

给 discord-collector `/telegram` 建卡链路用：根据**方向 / 币种 / 叙事**做 AI 短评，CDP 打开 OI 形态图截取 `.pattern-chart-body`，再调用上文的发布能力。

默认异步。鉴权与 `/api/v1/publish` 相同（`PUBLISH_API_TOKEN`）。

### 字段

| 字段 | 说明 |
|---|---|
| `symbol` | 必填，如 `ETH` / `ETHUSDT` |
| `direction` | 必填，`long`/`short` 或 `多`/`空` |
| `narrative` / `body` | 信号原文（叙事） |
| `event` | `entry`（开仓）/ `update`（补 TP/SL）/ `take_profit` / `stop_loss` |
| `entry` / `targets` / `stopLoss` | 价位 |
| `platforms` | 同发布接口；缺省用 `publish.default_platforms` 或 env `TRADE_SIGNAL_PUBLISH_PLATFORMS` |
| `oi_url` | 可选。默认等价打开 `http://127.0.0.1:5178/oi?symbol=…`，截图实际导航到嵌入页 `http://127.0.0.1:8765/#/patterns?symbol=…`（跨域 iframe 无法直接截壳层） |
| `skip_ai` / `skip_screenshot` / `skip_publish` | 调试用 |
| `async` | 默认 `true` |

```bash
curl -sS -X POST http://127.0.0.1:8787/api/v1/trade-signal/publish \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "ETH",
    "direction": "short",
    "event": "entry",
    "entry": "2505-2515",
    "targets": ["2495", "2485"],
    "stopLoss": "2525",
    "narrative": "【群】ETH 空 #prom …",
    "platforms": ["gate"]
  }'
```

轮询：`GET /api/v1/trade-signal/jobs/{job_id}`。

### discord-collector 开关

```env
TRADE_SIGNAL_AI_PUBLISH=1
TRADE_SIGNAL_AI_PUBLISH_URL=http://127.0.0.1:8787
TRADE_SIGNAL_AI_PUBLISH_PLATFORMS=gate,okx
```

Telegram 来源卡片在 `archiveCard`（新建 / 合并补 TP·SL）后会异步 POST 本接口。

### 环境变量（python-ai-operate）

| 变量 | 默认 | 说明 |
|---|---|---|
| `OI_CHART_URL` | `http://127.0.0.1:5178/oi` | 壳层入口（文档语义） |
| `OI_EMBED_URL` | `http://127.0.0.1:8765` | 实际截图页 |
| `OI_CHART_SELECTOR` | `.pattern-chart-body` | 截图 CSS |
| `CDP_DEBUGGER_URL` | 同抓取 CDP | 截图用 Chrome |
| `TRADE_SIGNAL_PUBLISH_PLATFORMS` | 配置 default | 发布平台 |
