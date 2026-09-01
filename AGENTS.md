# TrendRadar Agent 提示

本仓库控制台为 **零构建** 的 `console/` 单页 + `console/app.py` API。

优化前端或其配套后端时：

1. 优先阅读 `.cursor/rules/console-overview.mdc`
2. 改 UI → `console-frontend.mdc`
3. 改 API/Job → `console-backend.mdc`
4. 找文件归属 → `console-domain-map.mdc`

入口：`python console.py`（默认端口 8787）。改 `app.js`/`app.css` 必须 bump `index.html` 中的 `?v=`；改 Python 后重启 console，并避免多进程占用同端口。
