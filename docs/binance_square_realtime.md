# 币安 Square 实时抓取（bapi + Cookie）

## 路径

- 后台：`signals/binance_square/cycle_watcher.py` → `run_binance_square_fetch(realtime_incremental=True)`
- 默认 **博主主页 bapi 分页**，不依赖 CDP 滚动
- CDP 仅回退：`BINANCE_SQUARE_USE_CDP=1` 或 bapi 完全无数据且未设 `BINANCE_SQUARE_API_ONLY=1`

## Mac 一次性配置

1. Chrome 登录 [binance.com](https://www.binance.com)，打开 **Square** 并随便滚动几条时间线（让浏览器带上指纹头）。
2. 启动远程调试（与 `config/binance_square_signals.yaml` 的 `debugger_url` 一致，常见 `9223`）：

   ```bash
   # 示例：按你本机 Chrome 启动方式调整
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9223
   ```

3. 导出会话（勿提交 git）：

   ```bash
   cd ~/frontend/code/1.operations/python-ai-operate   # 或本仓库根目录
   python scripts/bootstrap_binance_session_from_cdp.py --debugger 127.0.0.1:9223
   ```

   生成：`output/signals/binance_square_session.json`

4. 若 bapi 仍返回空 `data`，在 DevTools → Network 找任意 `bapi/composite` 请求，把 Request Headers 里的 `device-info`、`fvideo-id` 等复制进 session JSON 的 `headers` 字段（参见 `config/binance_square_session.example.json`）。

## 联调 smoke（可选，需真实 Cookie）

```bash
export SIGNALS_HTTP_SMOKE=1
export SMOKE_BS_PROFILE=yanchibit   # config 里启用的博主 id
python scripts/smoke_signals_http.py
```

## Console 验证

1. `python console.py`
2. **列表信号 → 币安广场**，勾选周期抓取，或点 **实时** 视图的「立即抓取」
3. 请求体会带 `realtime_incremental: true`（与周期 watcher 相同 bapi 增量路径）
4. 日志应出现：
   - `Square 实时：跳过热榜，仅抓配置博主 bapi`
   - `bapi @<slug>` 分页
   - 增量轮次：`命中已存帖，停止翻页`
   - `bapi 补全发帖时间（detail firstReleaseTime）`

## 环境变量

| 变量 | 含义 |
|------|------|
| `BINANCE_SQUARE_SESSION_FILE` | 自定义 session JSON 路径 |
| `BNC_CSRF` / `BNC_UUID` | 临时覆盖 cookie 头 |
| `BINANCE_SQUARE_USE_CDP=1` | 强制 CDP 滚动 |
| `BINANCE_SQUARE_API_ONLY=1` | 禁止 CDP 回退 |
