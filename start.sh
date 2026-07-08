#!/bin/bash

echo "=========================================="
echo "  StyleMind v2 - AI对话式PPT生成"
echo "=========================================="
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到 Python3，请先安装 Python 3.10+"
    exit 1
fi

# 检查依赖
echo "[1/3] 检查依赖..."
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

source venv/bin/activate

# 安装依赖
echo "[2/3] 安装依赖..."
pip install -q -r requirements.txt
if [ $? -ne 0 ]; then
    echo "[错误] 依赖安装失败"
    exit 1
fi

# 启动
echo "[3/3] 启动服务..."
echo ""
echo "请稍候，正在启动..."
echo ""

python app.py
