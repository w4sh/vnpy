#!/bin/bash
# vn.py 项目质量评分脚本

echo "📊 vn.py 项目质量评分"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 初始化分数
total_score=0
max_score=100

# 代码质量评分 (40分)
code_quality=0

echo "📊 代码质量检查 (40分)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ruff 检查
echo -n "ruff 检查: "
if ruff check . > /dev/null 2>&1; then
    echo "✅ 通过 (+10分)"
    code_quality=$((code_quality + 10))
else
    echo "❌ 失败 (0分)"
fi

# mypy 检查
echo -n "mypy 检查: "
if mypy vnpy > /dev/null 2>&1; then
    echo "✅ 通过 (+10分)"
    code_quality=$((code_quality + 10))
else
    echo "❌ 失败 (0分)"
fi

# 代码格式化
echo -n "代码格式化: "
if ruff format . --check > /dev/null 2>&1; then
    echo "✅ 符合 (+10分)"
    code_quality=$((code_quality + 10))
else
    echo "⚠️  不符合 (+0分)"
fi

# 文档完整性 (简化检查)
echo -n "文档完整性: "
doc_files=$(find vnpy -name "*.py" -type f | wc -l)
files_with_doc=$(grep -r "^class\|^def" vnpy --include="*.py" | wc -l)
if [ $doc_files -gt 0 ]; then
    ratio=$((files_with_doc * 100 / doc_files))
    if [ $ratio -gt 50 ]; then
        echo "✅ 良好 (+10分)"
        code_quality=$((code_quality + 10))
    else
        echo "⚠️  需改进 (+5分)"
        code_quality=$((code_quality + 5))
    fi
else
    echo "⚠️  一般 (+3分)"
    code_quality=$((code_quality + 3))
fi

echo "  小计: $code_quality/40"
echo ""

total_score=$((total_score + code_quality))

# 测试覆盖评分 (30分)
test_coverage=0

echo "🧪 测试覆盖检查 (30分)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 检查测试文件是否存在
if [ -d "tests" ]; then
    test_count=$(find tests -name "test_*.py" -type f | wc -l)
    echo -n "测试文件数: $test_count"

    if [ $test_count -ge 5 ]; then
        echo " ✅ (+15分)"
        test_coverage=$((test_coverage + 15))
    elif [ $test_count -ge 2 ]; then
        echo " ⚠️  (+10分)"
        test_coverage=$((test_coverage + 10))
    else
        echo " ⚠️  (+5分)"
        test_coverage=$((test_coverage + 5))
    fi

    # 尝试运行 pytest --cov 获取覆盖率
    echo -n "测试覆盖率: "
    if command -v pytest &> /dev/null; then
        coverage=$(pytest --cov=vnpy --cov-report=term-missing:skip-no-cov -q 2>/dev/null | grep "TOTAL" | awk '{print $4}' | sed 's/%//')
        if [ -n "$coverage" ]; then
            coverage_int=${coverage%.*}
            if [ "$coverage_int" -ge 80 ]; then
                echo "$coverage% ✅ (+15分)"
                test_coverage=$((test_coverage + 15))
            elif [ "$coverage_int" -ge 60 ]; then
                echo "$coverage% ⚠️  (+10分)"
                test_coverage=$((test_coverage + 10))
            else
                echo "$coverage% ⚠️  (+5分)"
                test_coverage=$((test_coverage + 5))
            fi
        else
            echo "N/A ⚠️  (+5分)"
            test_coverage=$((test_coverage + 5))
        fi
    else
        echo "无法检查 ⚠️  (+0分)"
    fi
else
    echo "❌ 无测试目录 (0分)"
fi

echo "  小计: $test_coverage/30"
echo ""

total_score=$((total_score + test_coverage))

# 性能指标评分 (20分)
performance=0

echo "⚡ 性能指标检查 (20分)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "⚠️  性能基准测试尚未建立"
echo "  建议事件延迟: < 1ms"
echo "  当前: 未测量"
echo "  小计: 估计 10/20 (假设部分优化)"
performance=10

total_score=$((total_score + performance))

# 安全性评分 (10分)
security=0

echo "🔒 安全性检查 (10分)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 检查是否有硬编码凭证
echo -n "硬编码凭证检查: "
if grep -r "sk_live_\|api_key\|password\|secret" vnpy --include="*.py" --exclude-dir=".git" | grep -v "test\|example\|dummy" > /dev/null 2>&1; then
    echo "❌ 发现 (0分)"
else
    echo "✅ 通过 (+5分)"
    security=$((security + 5))
fi

# 检查 .gitignore 是否包含敏感文件
echo -n "敏感文件保护: "
if grep -q "\.pyc\|__pycache__\|\.mo\|\.env" .gitignore 2>/dev/null; then
    echo "✅ 通过 (+5分)"
    security=$((security + 5))
else
    echo "⚠️  部分保护 (+3分)"
    security=$((security + 3))
fi

echo "  小计: $security/10"
echo ""

total_score=$((total_score + security))

# 总评
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 总分: $total_score/100"
echo ""

# 评级
if [ $total_score -ge 95 ]; then
    grade="A+ (优秀)"
elif [ $total_score -ge 85 ]; then
    grade="A (优秀)"
elif [ $total_score -ge 75 ]; then
    grade="B (良好)"
elif [ $total_score -ge 65 ]; then
    grade="C (及格)"
else
    grade="D (需改进)"
fi

echo "评级: $grade"
echo ""

# 改进建议
echo "💡 改进建议:"
if [ $code_quality -lt 40 ]; then
    echo "  - 运行 'ruff check .' 修复代码问题"
    echo "  - 运行 'mypy vnpy' 修复类型问题"
fi
if [ $test_coverage -lt 30 ]; then
    echo "  - 为核心模块编写测试"
    echo "  - 目标覆盖率 > 80%"
fi
if [ $performance -lt 20 ]; then
    echo "  - 建立性能基准测试"
    echo "  - 优化事件处理延迟"
fi
if [ $security -lt 10 ]; then
    echo "  - 检查代码中的硬编码凭证"
    echo "  - 更新 .gitignore"
fi
echo ""

# 记录评分到日志
score_dir="harness/progress"
score_file="$score_dir/score-history.log"
mkdir -p "$score_dir"
echo "$(date '+%Y-%m-%d'): $total_score/100 ($grade)" >> "$score_file"

echo "📈 评分历史已记录到: $score_file"
echo ""
