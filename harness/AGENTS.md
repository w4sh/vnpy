# VeighNa (vn.py) - Agent 开发指南

**项目类型**: Python 量化交易系统开发框架
**技术栈**: Python 3.10-3.13, PySide6, NumPy, Pandas, Polars, ta-lib
**开发模式**: Harness Engineering v3-Lite

---

## 项目概述

VeighNa 是基于 Python 的开源量化交易系统开发框架，采用事件驱动引擎架构，支持多网关、多策略的量化交易。

### 核心模块
- `vnpy/event` - 事件驱动引擎
- `vnpy/trader` - 核心交易平台
- `vnpy/alpha` - AI量化策略模块
- `vnpy/web` - Web服务模块

### 技术特性
- **GUI框架**: PySide6 (Qt6)
- **数据处理**: NumPy, Pandas, Polars
- **技术分析**: ta-lib
- **包管理**: uv (超快Python包管理器)
- **代码质量**: ruff + mypy
- **测试框架**: pytest

---

## Agent 工作原则

### 核心原则

1. **增量工作**: 每次只处理一个功能或修复
2. **自我验证**: 完成前必须运行 `/check` 和相关测试
3. **留下痕迹**: 更新 `harness/progress/log.md` 并创建 git commit
4. **干净状态**: 会话结束时代码应可合并到主分支

### 必须遵循

- ✅ 不确定就问，不要猜测
- ✅ 从代码库提取模式，不要发明
- ✅ 空白比幻觉好，不知道就说不知道
- ✅ 每次代码变更后运行 `ruff format .`
- ✅ 犯错后更新 `harness/feedback/mistakes.md`
- ✅ 遇到新问题添加到 `harness/context/pitfalls.md`

### 严格禁止

- ❌ 依赖对话记忆，必须读取文件
- ❌ 跳过代码检查 (ruff + mypy)
- ❌ 绕过架构约束
- ❌ 创建与代码库无关的文档
- ❌ 犯同样的错误两次
- ❌ 修改 `pyproject.toml` 中的版本锁定 (如 PySide6==6.8.2.1)

---

## 开发工作流

### 每次会话开始

```bash
# 1. 查看当前进度
cat harness/progress/log.md

# 2. 查看待处理任务
cat tasks.json | jq '.tasks[] | select(.status == "pending")'

# 3. 运行环境检查
./scripts/check.sh

# 4. 选择一个任务开始工作
```

### 开发过程中

```bash
# 编写代码
ruff format .                    # 格式化
ruff check .                     # 检查
mypy vnpy                        # 类型检查
pytest -m "not slow" --no-cov    # 快速测试

# 遇到问题时
记录到 harness/feedback/mistakes.md
```

### 任务完成

```bash
# 1. 最终验证
./scripts/check.sh
./scripts/score.sh

# 2. 更新进度
# 更新 tasks.json 中任务状态
# 更新 harness/progress/log.md

# 3. 提交代码
git add .
git commit -m "feat: 完成功能描述"

# 4. 更新反馈系统
如遇到新问题，添加到 harness/context/pitfalls.md
```

---

## 关键约束

### 架构约束

**事件驱动**: 必须使用 `vnpy.event.EventEngine` 进行模块通信
**类型安全**: 所有公共API必须有完整类型标注
**数据不可变**: `TickData`, `OrderData` 等数据对象不可变
**异步处理**: 网关调用必须异步，避免阻塞主线程

### 代码风格

**遵循 ruff 配置**: 自动格式化，忽略 E501
**严格类型检查**: mypy disallow_untyped_defs
**文档字符串**: 公共API必须有文档字符串
**命名规范**: 遵循 PEP 8，使用蛇形命名

### 依赖管理

**版本锁定**: PySide6, ta-lib 等关键依赖版本锁定
**uv 优先**: 使用 uv 作为包管理器
**自定义镜像**: ta-lib 必须从 https://pypi.vnpy.com 安装

---

## 质量护栏

### 必须通过的检查

```bash
# 代码质量
ruff check .          # 必须无错误
mypy vnpy             # 必须无错误

# 测试
pytest tests/         # 核心测试必须通过

# 构建
uv build              # 必须成功
```

### 性能要求

- 事件延迟: < 1ms
- 数据处理: 优化 Polars/Pandas 使用
- 内存使用: 避免不必要的数据复制

### 安全要求

- API密钥: 不提交到代码库
- 输入验证: 所有外部输入必须验证
- 错误处理: 不暴露敏感信息

---

## 特殊注意事项

### ta-lib 安装

```bash
# 必须从自定义镜像安装
uv pip install ta-lib==0.6.4 --index=https://pypi.vnpy.com --system
```

### 翻译文件

```bash
# 重新生成翻译
vnpy/trader/locale/generate_mo.bat   # Windows
msgfmt *.po -o *.mo                   # Linux/macOS
```

### 本地化编译

项目使用 Babel 进行国际化管理，`.po` 文件需要编译成 `.mo` 文件。

---

## 常见命令

### 开发相关

```bash
# 安装依赖
uv pip install -e .[alpha,dev]

# 运行检查
ruff check .
mypy vnpy

# 运行测试
pytest -m "not slow" --no-cov
pytest --cov=vnpy

# 构建项目
uv build

# 代码格式化
ruff format .
```

### 技能快捷方式

```bash
/check           # 运行所有代码质量检查
/ta-lib          # 安装 ta-lib
/locale          # 生成翻译文件
/build           # 完整构建验证
```

---

## 进度追踪

**当前版本**: 4.3.0
**主分支**: master
**PR策略**: 直接提交到主分支 (小型团队)

### 查看进度

```bash
cat harness/progress/log.md
cat tasks.json
./scripts/score.sh
```

---

## 核心理念

> **Agent 不遵循指令，Agent 在系统中运行**

**Harness Engineering 定义了那个系统。**

---

## 参考资源

- **项目文档**: https://www.vnpy.com/docs
- **论坛**: https://www.vnpy.com/forum
- **GitHub**: https://github.com/vnpy/vnpy
- **Python 3.13**: https://docs.python.org/3.13/
- **PySide6**: https://doc.qt.io/qtforpython/
