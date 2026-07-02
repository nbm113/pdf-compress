#!/bin/bash
# PDF 压缩服务 - 一键启动脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  📄 PDF 压缩服务"
echo "============================================"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 python3，请先安装 Python 3"
    exit 1
fi

# 自动安装依赖
echo ""
echo "📦 检查依赖..."
PIP_BIN="python3 -m pip"
PIP_MIRROR="-i https://pypi.tuna.tsinghua.edu.cn/simple"

if ! python3 -c "import flask" 2>/dev/null; then
    echo "  → 安装 Flask..."
    $PIP_BIN install $PIP_MIRROR flask --user -q
fi

if ! python3 -c "import pikepdf" 2>/dev/null; then
    echo "  → 安装 pikepdf（PDF 处理引擎）..."
    $PIP_BIN install $PIP_MIRROR pikepdf --user -q
fi

if ! python3 -c "import PIL" 2>/dev/null; then
    echo "  → 安装 Pillow（图片优化）..."
    $PIP_BIN install $PIP_MIRROR Pillow --user -q
fi

echo "✅ 依赖就绪"
echo ""

# 创建上传目录
mkdir -p "$SCRIPT_DIR/uploads"

# 启动服务
echo "🚀 启动服务..."
echo "   本地访问: http://127.0.0.1:5050"
echo "   按 Ctrl+C 停止"
echo ""

python3 app.py
