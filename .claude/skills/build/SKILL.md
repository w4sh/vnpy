---
name: build
description: 完整的构建和验证流程(清理 + 格式化 + 检查 + 类型检查 + 测试 + 构建)
---

# 完整构建和验证流程

执行 vn.py 项目的完整构建和验证流程,确保代码质量和构建成功。

## 流程步骤

### 1. 清理构建文件

```bash
# 清理 Python 缓存
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# 清理构建目录
rm -rf build/ dist/ *.egg-info/ 2>/dev/null || true
```

### 2. 代码格式化

```bash
# 格式化所有代码
ruff format .
```

### 3. 代码质量检查

```bash
# 运行 ruff 检查
ruff check .
```

### 4. 类型检查

```bash
# 运行 mypy 类型检查
mypy vnpy
```

### 5. 运行测试(可选)

```bash
# 快速测试(跳过慢速测试)
pytest -m "not slow" --no-cov -q

# 或运行完整测试
pytest --cov=vnpy
```

### 6. 构建项目

```bash
# 使用 uv 构建
uv build

# 或使用标准构建
python -m build
```

## 一键执行脚本

### 完整验证(推荐用于 PR 前)

```bash
#!/bin/bash
set -e  # 遇到错误立即退出

echo "🧹 清理构建文件..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
rm -rf build/ dist/ *.egg-info/ 2>/dev/null || true

echo "✨ 格式化代码..."
ruff format .

echo "🔍 代码质量检查..."
ruff check .

echo "🔬 类型检查..."
mypy vnpy

echo "🧪 运行测试..."
pytest -m "not slow" --no-cov -q

echo "📦 构建项目..."
uv build

echo "✅ 构建成功!"
```

### 快速验证(跳过测试)

```bash
#!/bin/bash
set -e

echo "🧹 清理..."
rm -rf build/ dist/ *.egg-info/

echo "✨ 格式化..."
ruff format .

echo "🔍 检查..."
ruff check .
mypy vnpy

echo "📦 构建..."
uv build

echo "✅ 快速验证完成!"
```

## 使用场景

### 发布前验证

在创建 PR 或发布新版本前,运行完整验证:

```bash
# 完整验证流程
uv pip install -e .[alpha,dev]
# 运行上述完整验证脚本
```

### 日常开发

日常开发中可以使用快速验证:

```bash
# 快速验证(跳过测试)
# 运行上述快速验证脚本
```

### CI/CD 集成

在 GitHub Actions 或其他 CI 系统中:

```yaml
- name: Build and verify
  run: |
    uv pip install -e .[alpha,dev]
    ruff format .
    ruff check .
    mypy vnpy
    pytest -m "not slow" --no-cov
    uv build
```

## 故障排查

### 问题 1: ruff check 失败

**原因**: 代码不符合项目规范

**解决**:
1. 查看具体错误
2. 修复问题或添加 `# noqa` 注释(如果合理)
3. 重新运行

### 问题 2: mypy 类型检查失败

**原因**: 类型标注不完整或有误

**解决**:
1. 查看类型错误
2. 添加或修复类型标注
3. 如果是外部库问题,在 `pyproject.toml` 中添加 `ignore_missing_imports`

### 问题 3: 测试失败

**原因**: 代码有 bug 或测试需要更新

**解决**:
1. 查看失败的具体测试
2. 检查代码逻辑
3. 更新测试(如果功能变更)

### 问题 4: 构建失败

**原因**: 依赖问题或构建配置错误

**解决**:
1. 检查 `pyproject.toml` 配置
2. 确保所有依赖已安装
3. 检查构建钩子是否正常

## 构建产物

成功构建后会生成:

```
dist/
├── vnpy-4.3.0.tar.gz       # 源码包
└── vnpy-4.3.0-py3-none-any.whl  # wheel 包
```

## 验证清单

在提交代码或创建 PR 前,确保:

- [ ] 代码已格式化 (`ruff format .`)
- [ ] 通过 ruff 检查 (`ruff check .`)
- [ ] 通过类型检查 (`mypy vnpy`)
- [ ] 测试通过 (`pytest`)
- [ ] 构建成功 (`uv build`)
- [ ] 翻译文件已更新(如有修改)
- [ ] 文档已更新(如有功能变更)

## 性能优化

### 并行运行检查

```bash
# 同时运行多个检查(加快速度)
ruff check . & mypy vnpy & wait
```

### 缓存依赖

```bash
# 使用 pip 缓存加速安装
pip install --cache-dir ~/.pip-cache -e .[dev]
```

## 相关命令

```bash
# 仅构建不验证
uv build

# 验证不构建
ruff check . && mypy vnpy && pytest

# 查看构建配置
cat pyproject.toml | grep -A 10 "\[build-system\]"
```
