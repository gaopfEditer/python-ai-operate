@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo ============================================================
echo   TrendRadar Console 一键启动
echo ============================================================
echo.
echo   页面: http://127.0.0.1:8787/
echo   功能: 资讯获取 / 历史缓存 / Prompt 创作 / CDP 发布
echo.
echo   若使用 CDP 发布，请先另开终端启动 Chrome：
echo   chrome.exe --remote-debugging-port=9222 --user-data-dir="D:\chrome-cdp-profile"
echo.
echo   按 Ctrl+C 停止服务
echo ============================================================
echo.

where uv >nul 2>&1
if %errorlevel% equ 0 (
  uv run python console.py --host 127.0.0.1 --port 8787
) else (
  python console.py --host 127.0.0.1 --port 8787
)

pause
