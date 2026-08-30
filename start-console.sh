#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo "  TrendRadar Console 一键启动"
echo "============================================================"
echo ""
echo "  页面: http://127.0.0.1:8787/"
echo "  功能: 列表信号 / 灵感碰撞 / Prompt 创作 / CDP 发布"
echo ""
echo "  若使用 CDP 发布，请先启动 Chrome："
echo "  Google\\ Chrome --remote-debugging-port=9222 --user-data-dir=\"\$HOME/chrome-cdp-profile\""
echo ""
echo "  按 Ctrl+C 停止服务"
echo "============================================================"
echo ""

if command -v uv >/dev/null 2>&1; then
  uv run python console.py --host 127.0.0.1 --port 8787
else
  python3 console.py --host 127.0.0.1 --port 8787
fi
