@echo off
chcp 65001 >nul
echo ==========================================
echo   StyleMind v2 - AI对话式PPT生成
echo ==========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: 检查依赖
echo [1/3] 检查依赖...
if not exist "venv" (
    echo 创建虚拟环境...
    python -m venv venv
)

call venv\Scripts\activate

:: 安装依赖
echo [2/3] 安装依赖...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

:: 启动
echo [3/3] 启动服务...
echo.
echo 请稍候，正在启动...
echo.

python app.py

pause
