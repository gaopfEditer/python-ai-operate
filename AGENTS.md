# TrendRadar Agent 提示

本仓库控制台为 **零构建** 的 `console/` 单页 + `console/app.py` API。

优化前端或其配套后端时：

1. 优先阅读 `.cursor/rules/console-overview.mdc`
2. 改 UI → `console-frontend.mdc`
3. 改 API/Job → `console-backend.mdc`
4. 找文件归属 → `console-domain-map.mdc`

入口：`python console.py`（默认端口 8787）。改 `app.js`/`app.css` 都必须 bump `index.html` 中的 `?v=`（JS 和 CSS 各有自己的版本号，缺一不可，只改其中一个会导致浏览器用旧缓存）。改 Python 后重启 console，并避免多进程占用同端口。

币安 Square 博主帖默认 **HTTP(bapi)+Cookie**（`profile_fetch_mode: bapi`，见 `config/binance_square_signals.yaml`）；9223 Chrome 需登录币安。推特抓取复用 **Signals 专用 CDP 后台页签**（`signals_cdp_target_id`）。
