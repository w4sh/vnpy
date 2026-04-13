# 质量护栏 (Guardrails)

vn.py 项目的自动化质量保证系统。

## 三层护栏系统

### Layer 1: 架构护栏
**目标**: 防止违反核心架构原则

**检查内容**:
- 事件驱动架构使用
- 数据对象不可变性
- 异步网关调用
- 类型安全

**验证命令**:
```bash
# 架构检查脚本
bash scripts/checks/arch-check.sh
```

---

### Layer 2: 代码质量护栏
**目标**: 确保代码质量和一致性

**检查内容**:
- ruff 代码检查 (0 错误)
- mypy 类型检查 (0 错误)
- 代码格式化
- 文档字符串完整性

**验证命令**:
```bash
ruff check .         # 必须通过
mypy vnpy            # 必须通过
ruff format .        # 自动格式化
```

---

### Layer 3: 熵对抗 (Entropy Fighting)
**目标**: 防止代码腐化和技术债务累积

**检查内容**:
- 未使用的导入
- 重复代码
- 死代码
- 过长的函数
- 复杂度指标

**验证命令**:
```bash
# 熵对抗脚本
bash scripts/entropy-fight.sh
```

---

## 自动化检查脚本

### check.sh - 主检查脚本

```bash
#!/bin/bash
set -e

echo "🔍 运行质量护栏检查..."

# Layer 1: 代码质量
echo "📊 Layer 1: 代码质量检查"
ruff format . --check
ruff check .
mypy vnpy

# Layer 2: 测试
echo "🧪 Layer 2: 测试检查"
pytest tests/ -m "not slow" --no-cov -q

# Layer 3: 构建验证
echo "📦 Layer 3: 构建检查"
uv build --check

echo "✅ 所有检查通过!"
```

---

## 质量评分系统

### 评分标准 (0-100)

#### 代码质量 (40分)
- ruff 检查通过: 10分
- mypy 检查通过: 10分
- 代码格式化: 10分
- 文档完整性: 10分

#### 测试覆盖 (30分)
- 核心模块覆盖率 > 80%: 15分
- 其他模块覆盖率 > 60%: 10分
- 所有测试通过: 5分

#### 性能指标 (20分)
- 事件延迟 < 1ms: 10分
- 数据处理优化: 10分

#### 安全性 (10分)
- 无硬编码凭证: 5分
- 输入验证完整: 5分

### 查看评分

```bash
./scripts/score.sh
```

输出示例:
```
📊 vn.py 项目质量评分
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
代码质量:     35/40 (✓)
测试覆盖:     25/30 (✓)
性能指标:     18/20 (✓)
安全性:       8/10  (✓)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
总分:         86/100

评级: A (优秀)
```

---

## 持续改进循环

### 错误追踪流程

```
1. Agent 犯错
   ↓
2. 记录到 harness/feedback/mistakes.md
   ↓
3. 添加到 harness/context/pitfalls.md
   ↓
4. 创建检查脚本 (如需要)
   ↓
5. 防止再犯
```

### 改进记录

```
1. 发现问题
   ↓
2. 记录到 harness/feedback/improvements.md
   ↓
3. 更新文档和规范
   ↓
4. 提升质量
```

---

## 门禁规则

### Pre-commit 门禁

```bash
#!/bin/bash
# .git/hooks/pre-commit

# 快速检查
ruff format .
ruff check .
mypy vnpy

# 如果失败，阻止提交
if [ $? -ne 0 ]; then
    echo "❌ 质量检查失败，请修复后再提交"
    exit 1
fi
```

### PR 门禁

```yaml
# .github/workflows/pr-check.yml
name: PR Quality Check

on: [pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run checks
        run: |
          pip install -e .[dev]
          ruff check .
          mypy vnpy
          pytest tests/
```

---

## 质量趋势追踪

### 每周评分

```bash
# 记录每周评分
./scripts/score.sh >> harness/progress/weekly-scores.log
```

### 改进指标

- 代码质量趋势: ↗️ 提升 / ↘️ 下降 / ➡️ 稳定
- 测试覆盖率趋势: ↗️ / ↘️ / ➡️
- 性能指标趋势: ↗️ / ↘️ / ➡️

---

## 失败后的行动

### 当检查失败时

1. **查看具体错误**
   ```bash
   ruff check . --output-format=full
   mypy vnpy --show-traceback
   ```

2. **修复问题**
   - 根据错误信息修复
   - 参考 `harness/context/pitfalls.md`

3. **重新检查**
   ```bash
   ./scripts/check.sh
   ```

4. **记录错误** (如果是新问题)
   - 添加到 `harness/feedback/mistakes.md`
   - 更新 `harness/context/pitfalls.md`

---

## 护栏配置

### ruff 配置
```toml
[tool.ruff]
target-version = "py310"

[tool.ruff.lint]
select = ["B", "E", "F", "UP", "W"]
ignore = ["E501"]

[tool.ruff.format]
indent-style = "space"
quote-style = "double"
```

### mypy 配置
```toml
[tool.mypy]
python_version = "3.10"
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
```

---

## 监控和告警

### 质量下降告警

```python
# scripts/quality_monitor.py
def check_quality_trend():
    """检查质量趋势"""
    scores = load_weekly_scores()
    if scores[-1] < scores[-2] * 0.95:
        send_alert("⚠️ 质量下降!")
```

### 技术债务告警

```python
def check_debt():
    """检查技术债务"""
    debt_ratio = calculate_debt_ratio()
    if debt_ratio > 0.3:
        send_alert("⚠️ 技术债务过高!")
```

---

## 问责制度

### 质量责任人

- **架构护栏**: engineering-software-architect
- **代码质量**: engineering-code-reviewer
- **测试覆盖**: testing-api-tester
- **性能优化**: engineering-senior-developer

### 定期审查

- **每周**: 查看评分趋势
- **每月**: 审查错误日志
- **每季度**: 更新护栏规则

---

## 评分目标

### 当前目标
- **总分**: > 85 分
- **代码质量**: > 35 分
- **测试覆盖**: > 25 分
- **性能指标**: > 18 分
- **安全性**: > 8 分

### 理想目标
- **总分**: > 95 分
- **代码质量**: 40/40
- **测试覆盖**: 30/30
- **性能指标**: 20/20
- **安全性**: 10/10

---

## 参考资源

- [Harness Engineering](https://openai.com/index/harness-engineering/)
- [质量门禁](https://martinfowler.com/articles/quality-gates.html)
- [持续集成](https://www.continuousintegration.com/)
