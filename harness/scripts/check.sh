#!/bin/bash
# vn.py 项目质量检查脚本
# 运行所有质量护栏检查

set -e  # 遇到错误立即退出

echo "🔍 vn.py 质量护栏检查"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Layer 1: 代码质量检查
echo "📊 Layer 1: 代码质量检查"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 格式化检查
echo "✨ 检查代码格式..."
ruff format . --check > /dev/null 2>&1 || {
    echo "⚠️  代码格式不符合，正在自动格式化..."
    ruff format .
    echo "✅ 代码已自动格式化"
}

# ruff 检查
echo "🔍 运行 ruff 检查..."
if ! ruff check .; then
    echo "❌ ruff 检查失败"
    echo "请运行 'ruff check .' 查看详细错误"
    exit 1
fi
echo "✅ ruff 检查通过"

# mypy 类型检查
echo "🔬 运行 mypy 类型检查..."
if ! mypy vnpy; then
    echo "❌ mypy 检查失败"
    echo "请运行 'mypy vnpy' 查看详细错误"
    exit 1
fi
echo "✅ mypy 检查通过"

echo ""

# Layer 2: 测试检查
echo "🧪 Layer 2: 测试检查"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "🔍 运行快速测试..."
if ! pytest tests/ -m "not slow" --no-cov -q; then
    echo "❌ 测试失败"
    echo "请运行 'pytest tests/' 查看详细错误"
    exit 1
fi
echo "✅ 测试通过"

echo ""

# Layer 3: 构建验证
echo "📦 Layer 3: 构建验证"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "🔍 检查构建配置..."
if ! uv build --check > /dev/null 2>&1; then
    echo "❌ 构建检查失败"
    echo "请检查 pyproject.toml 配置"
    exit 1
fi
echo "✅ 构建检查通过"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 所有质量护栏检查通过!"
echo ""

# 显示项目状态
echo "📊 项目状态:"
echo "  Python 版本: $(python3 --version)"
echo "  Ruff 版本: $(ruff --version)"
echo "  Mypy 版本: $(mypy --version)"
echo "  Pytest 版本: $(pytest --version | head -1)"
echo ""
