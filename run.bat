@echo off
chcp 65001 >nul
title PDF Compress

echo ============================================
echo   PDF Compress v2.0
echo ============================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.9+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 自动安装依赖
python -c "import flask" >nul 2>&1 || (
    echo 正在安装依赖，请稍候...
    python -m pip install flask pikepdf Pillow -q
)

:: 创建上传目录
if not exist "uploads" mkdir "uploads"

:: 启动
echo 启动服务...
start http://127.0.0.1:5050
python app.py
pause
