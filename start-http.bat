@echo off
chcp 65001 >nul

echo ============================================================
echo   TrendRadar MCP Server (HTTP 模式)
echo ============================================================
echo.

REM 检查 UV 是否已安装
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ [错误] UV 未安装
    echo 请先运行 setup-windows.bat 进行部署
    echo.
    pause
    exit /b 1
)

REM 检查依赖是否已安装（通过检查 pyproject.toml 和 .venv 或 uv 环境）
if not exist "pyproject.toml" (
    echo ❌ [错误] 未找到 pyproject.toml 文件
    echo 请确保在项目根目录运行此脚本
    echo.
    pause
    exit /b 1
)

echo [模式] HTTP (适合远程访问)
echo [地址] http://localhost:3333/mcp
echo [提示] 按 Ctrl+C 停止服务
echo.

REM 使用 uv run 自动管理虚拟环境
uv run python -m mcp_server.server --transport http --host 0.0.0.0 --port 3333

pause
