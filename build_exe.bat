@echo off
chcp 65001 >nul
title PDF Compress - Windows 构建打包

echo ============================================
echo   PDF Compress - Windows 自包含打包构建
echo   目标：生成无需安装任何依赖的文件夹
echo ============================================
echo.

:: ── 检查 Python ──────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.9+
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时务必勾选 "Add Python to PATH"
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo   Python: %%v

:: ── 查找 Ghostscript ─────────────────────────────────────────
echo.
echo [1/5] 查找 Ghostscript...

set GS_FOUND=0
set GS_BIN_DIR=

:: 检查 PATH
where gswin64c.exe >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%i in ('where gswin64c.exe') do set GS_BIN_DIR=%%~dpi
    set GS_FOUND=1
    echo   找到: PATH ^(gswin64c^)
    goto :gs_done
)

where gswin32c.exe >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%i in ('where gswin32c.exe') do set GS_BIN_DIR=%%~dpi
    set GS_FOUND=1
    echo   找到: PATH ^(gswin32c^)
    goto :gs_done
)

:: 检查常见安装位置
for %%b in ("C:\Program Files\gs\gs10.07.1\bin" "C:\Program Files\gs\gs10.07.0\bin" "C:\Program Files\gs\gs10.06.0\bin" "C:\Program Files (x86)\gs\gs10.07.1\bin") do (
    if exist "%%~b\gswin64c.exe" (
        set GS_BIN_DIR=%%~b
        set GS_FOUND=1
        echo   找到: %%~b
        goto :gs_done
    )
    if exist "%%~b\gswin32c.exe" (
        set GS_BIN_DIR=%%~b
        set GS_FOUND=1
        echo   找到: %%~b
        goto :gs_done
    )
)

echo   [警告] 未找到 Ghostscript - 打包后将仅使用 pikepdf 引擎
echo   如需内嵌 Ghostscript，请先安装: https://ghostscript.com/releases/gsdnld.html
echo   安装后重新运行本脚本即可自动发现并打包
echo.

:gs_done
if %GS_FOUND% equ 1 (
    echo   Ghostscript 将内嵌到打包中
)

:: ── 准备 Ghostscript 内嵌目录 ─────────────────────────────────
if exist gs_bundle rmdir /s /q gs_bundle
mkdir gs_bundle

if %GS_FOUND% equ 1 (
    echo.
    echo [2/5] 复制 Ghostscript 二进制文件...

    :: 复制主要文件
    for %%f in (gswin64c.exe gswin32c.exe gswin64.exe gswin32.exe) do (
        if exist "%GS_BIN_DIR%\%%f" (
            copy /y "%GS_BIN_DIR%\%%f" gs_bundle\ >nul
            echo   %%f
        )
    )

    :: 复制 DLL 文件
    for %%f in (gsdll64.dll gsdll32.dll) do (
        if exist "%GS_BIN_DIR%\%%f" (
            copy /y "%GS_BIN_DIR%\%%f" gs_bundle\ >nul
            echo   %%f
        )
    )

    :: 尝试复制其他可能需要的 DLL
    for %%f in (libgs-16.dll libgs.dll) do (
        if exist "%GS_BIN_DIR%\%%f" (
            copy /y "%GS_BIN_DIR%\%%f" gs_bundle\ >nul
            echo   %%f
        )
    )

    if not exist "gs_bundle\gswin64c.exe" if not exist "gs_bundle\gswin32c.exe" (
        echo   [警告] 未找到 Ghostscript 可执行文件，将跳过内嵌
        rmdir /s /q gs_bundle
        set GS_FOUND=0
    )
)

:: ── 安装 Python 依赖 ─────────────────────────────────────────
echo.
echo [3/5] 安装 Python 依赖...
python -m pip install flask pikepdf Pillow pyinstaller -q 2>&1
if %errorlevel% neq 0 (
    echo   [警告] pip 安装失败，尝试使用镜像源...
    python -m pip install flask pikepdf Pillow pyinstaller -q -i https://pypi.tuna.tsinghua.edu.cn/simple
)
echo   依赖安装完成

:: ── 清理旧构建 ───────────────────────────────────────────────
echo.
echo [4/5] 清理旧构建...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "PDF-Compress.spec" del /q "PDF-Compress.spec"

:: ── PyInstaller 打包 ──────────────────────────────────────────
echo [5/5] PyInstaller 打包中（约 2-5 分钟）...

:: 基础命令
set PYI_CMD=pyinstaller --onedir --name "PDF-Compress" --add-data "templates;templates" --add-data "static;static" --collect-all pikepdf --hidden-import pikepdf --hidden-import PIL._imaging --clean app.py

:: 如果有 Ghostscript 二进制，添加到打包
if %GS_FOUND% equ 1 (
    echo   内嵌 Ghostscript 引擎...
    set PYI_CMD=%PYI_CMD% --add-binary "gs_bundle\*;gs"
)

%PYI_CMD%

if %errorlevel% neq 0 (
    echo.
    echo [错误] 打包失败，请检查上方的错误输出
    pause
    exit /b 1
)

:: ── 生成启动器 ───────────────────────────────────────────────
(
echo @echo off
echo chcp 65001 ^>nul
echo title PDF Compress
echo echo 启动中...
echo echo.
echo start http://127.0.0.1:5050
echo start "" "%%~dp0PDF-Compress.exe"
) > "dist\PDF-Compress\启动.bat"

:: ── 清理临时文件 ─────────────────────────────────────────────
if exist gs_bundle rmdir /s /q gs_bundle

:: ── 完成 ─────────────────────────────────────────────────────
echo.
echo ============================================
echo   构建完成！
echo.
echo   输出: dist\PDF-Compress\
echo.
if %GS_FOUND% equ 1 (
    echo   引擎: pikepdf + Ghostscript ^(内嵌^)
) else (
    echo   引擎: pikepdf
    echo   提示: 目标电脑可安装 Ghostscript 获得更好压缩效果
)
echo.
echo   部署: 将 PDF-Compress 文件夹复制到任意 Windows 电脑
echo          双击 "启动.bat" 即可使用，无需安装任何东西
echo ============================================
echo.
echo 按任意键打开输出目录...
pause >nul
start "" "dist\PDF-Compress"
