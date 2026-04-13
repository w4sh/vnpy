#!/bin/bash
# vn.py 开发服务器启动脚本

echo "🚀 vn.py 开发环境"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 检查 Python 版本
echo "🐍 Python 版本检查"
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 未安装"
    exit 1
fi

python_version=$(python3 --version | awk '{print $2}')
echo "  当前版本: $python_version"

# 检查是否符合要求
major=$(echo $python_version | cut -d. -f1)
minor=$(echo $python_version | cut -d. -f2)

if [ "$major" -lt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -lt 10 ]); then
    echo "  ⚠️  版本过低，需要 Python 3.10+"
    echo "  推荐使用 Python 3.13"
else
    echo "  ✅ 版本符合要求"
fi
echo ""

# 检查 uv
echo "📦 包管理器检查"
if ! command -v uv &> /dev/null; then
    echo "  ⚠️  uv 未安装"
    echo "  安装命令: curl -LsSf https://astral.sh/uv | sh"
else
    echo "  ✅ uv 已安装: $(uv --version)"
fi
echo ""

# 检查项目依赖
echo "🔍 依赖检查"
echo "  检查核心依赖..."
required_packages=("PySide6" "numpy" "pandas" "talib")
all_installed=true

for pkg in "${required_packages[@]}"; do
    if python3 -c "import $pkg" 2>/dev/null; then
        echo "    ✅ $pkg"
    else
        echo "    ❌ $pkg 未安装"
        all_installed=false
    fi
done

if [ "$all_installed" = false ]; then
    echo ""
    echo "💡 安装依赖:"
    echo "  uv pip install -e .[alpha,dev]"
    echo ""
    echo "💡 特殊: ta-lib 安装"
    echo "  uv pip install ta-lib==0.6.4 --index=https://pypi.vnpy.com --system"
fi
echo ""

# 检查代码质量工具
echo "🛠️  代码质量工具"
tools=("ruff" "mypy" "pytest")
for tool in "${tools[@]}"; do
    if command -v $tool &> /dev/null; then
        echo "  ✅ $tool"
    else
        echo "  ⚠️  $tool 未安装"
    fi
done
echo ""

# 显示待处理任务
echo "📋 待处理任务"
if [ -f "harness/tasks.json" ]; then
    pending_tasks=$(cat harness/tasks.json | jq '.tasks[] | select(.status == "pending") | .title' 2>/dev/null)
    pending_count=$(echo "$pending_tasks" | grep -c "^" 2>/dev/null || echo "0")

    if [ "$pending_count" -gt 0 ]; then
        echo "  有 $pending_count 个待处理任务:"
        echo "$pending_tasks" | head -5
        if [ "$pending_count" -gt 5 ]; then
            echo "  ... 还有 $((pending_count - 5)) 个"
        fi
    else
        echo "  ✅ 所有任务已完成"
    fi
else
    echo "  ⚠️  tasks.json 不存在"
fi
echo ""

# 显示项目状态
echo "📊 项目状态"
echo "  分支: $(git branch --show-current 2>/dev/null || echo "未知")"
echo "  最后提交: $(git log -1 --format='%h - %s' 2>/dev/null || echo "未知")"
echo "  未提交: $(git status --short 2>/dev/null | wc -l | tr -d ' ') 个文件"
echo ""

# 快捷命令
echo "⚡ 常用命令"
echo "  代码检查:     ./scripts/check.sh"
echo "  项目评分:     ./scripts/score.sh"
echo "  运行测试:     pytest tests/"
echo "  代码格式化:   ruff format ."
echo "  类型检查:     mypy vnpy"
echo ""

# Git 状态
if [ -d ".git" ]; then
    echo "🌿 Git 状态"
    git status --short 2>/dev/null || echo "  (无变化)"
    echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 开发环境就绪!"
echo ""
echo "💡 开始开发前建议:"
echo "  1. 查看 tasks.json 选择任务"
echo "  2. 查看 harness/progress/log.md 了解进度"
echo "  3. 运行 ./scripts/check.sh 确保环境正常"
echo ""
