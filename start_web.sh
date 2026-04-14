#!/bin/bash
# vn.py Web应用启动脚本

echo "=========================================="
echo "  vn.py 量化交易Web界面启动脚本"
echo "=========================================="
echo ""

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "❌ 错误: 找不到虚拟环境"
    echo "请先在项目根目录运行: python3 -m venv venv"
    exit 1
fi

# 激活虚拟环境
echo "📦 激活虚拟环境..."
source venv/bin/activate

# 检查Flask安装
echo "🔍 检查依赖包..."
if ! python -c "import flask" 2>/dev/null; then
    echo "📥 安装Flask依赖..."
    pip install -r web_app/requirements.txt
fi

# 检查数据目录
if [ ! -d "lab_data/daily" ]; then
    echo "❌ 错误: 找不到数据目录"
    echo "请先运行数据下载脚本"
    exit 1
fi

echo "✅ 依赖检查完成"
echo ""
echo "🚀 启动Web应用..."
echo ""
echo "📱 请在浏览器中访问: http://localhost:5000"
echo "🛑 按 Ctrl+C 停止服务"
echo ""
echo "=========================================="
echo ""

# 启动Flask应用
cd web_app
python app.py