#!/usr/bin/env bash
# 安装 0/8/12/16/20 点 task-os 实时关注同步（本机 launchd）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
SCRIPT="${ROOT}/scripts/task_os_live_watch_sync.py"
PLIST="$HOME/Library/LaunchAgents/com.maotouying.task-os-live-watch.plist"
mkdir -p "$HOME/Library/LaunchAgents"
if [[ ! -x "$PY" ]]; then
  echo "请先创建 venv: cd $ROOT && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.maotouying.task-os-live-watch</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$SCRIPT</string>
    <string>--push</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>0</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>16</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>20</integer><key>Minute</key><integer>0</integer></dict>
  </array>
  <key>StandardOutPath</key>
  <string>$HOME/Library/Logs/task-os-live-watch.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/Library/Logs/task-os-live-watch.err.log</string>
</dict>
</plist>
EOF
echo "已写入 $PLIST"
echo "加载: launchctl load $PLIST"