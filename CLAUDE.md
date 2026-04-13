# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

VeighNa (vnpy) 是基于 Python 的开源量化交易系统开发框架。使用 Python 3.10-3.13 (推荐 3.13)。

## 包管理和安装

使用 `uv` 作为包管理器(超快的 Python 包安装器):

```bash
# 安装项目(含 alpha 和 dev 依赖)
uv pip install -e .[alpha,dev]

# 安装 ta-lib(特殊配置,必须从自定义镜像安装)
uv pip install ta-lib==0.6.4 --index=https://pypi.vnpy.com --system
```

**重要**: ta-lib 必须从 `https://pypi.vnpy.com` 镜像安装,版本锁定为 0.6.4。

## 代码质量

代码必须完全符合 ruff 配置要求。项目使用严格的类型检查和代码规范。

### 代码检查
```bash
# 运行 ruff 检查
ruff check .

# 类型检查
mypy vnpy
```

### 格式化
```bash
# 格式化所有代码
ruff format .
```

**注意**: ruff 配置忽略 E501(行长度限制),但不影响其他检查规则。

## 测试

项目使用 pytest 作为测试框架,位于 `tests/` 目录。

### 运行测试
```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_trader_objects.py

# 运行特定测试函数
pytest tests/test_trader_objects.py::TestTickData::test_create_tick

# 运行测试并生成覆盖率报告
pytest --cov=vnpy --cov-report=html

# 并行运行测试(加快速度)
pytest -n auto

# 只运行单元测试(跳过集成测试)
pytest -m "not integration"

# 跳过慢速测试
pytest -m "not slow"
```

### 测试组织
- `tests/conftest.py`: 共享的 pytest fixtures 和配置
- `tests/test_alpha101.py`: Alpha101 因子测试
- `tests/test_trader_objects.py`: 核心交易对象单元测试(示例)

### 测试标记
- `@pytest.mark.unit`: 单元测试(快速,隔离)
- `@pytest.mark.integration`: 集成测试(可能较慢,需要外部依赖)
- `@pytest.mark.slow`: 慢速测试(运行时间较长)

## 项目结构

核心框架采用模块化设计:
- `vnpy/event`: 事件驱动引擎
- `vnpy/trader`: 核心交易平台
- `vnpy/alpha`: AI量化策略模块(4.0+版本)
- `vnpy/web`: Web服务模块

## 特殊注意事项

### 本地化编译
如需重新生成翻译文件:
```bash
# Windows
vnpy/trader/locale/generate_mo.bat
```

### 依赖版本锁定
关键依赖使用具体版本锁定:
- PySide6==6.8.2.1 (Qt6 GUI框架)
- 其他依赖见 pyproject.toml

### 平台兼容性
- 支持 Windows/Linux/macOS
- 某些模块针对 Windows 优化
- CI 环境使用 windows-latest

## 核心技术栈

- **GUI**: PySide6 (Qt6)
- **数据处理**: NumPy, Pandas, Polars
- **技术分析**: ta-lib
- **可视化**: PyQtGraph, Plotly
- **日志**: Loguru
- **AI/ML**: PyTorch, LightGBM, scikit-learn (alpha模块)
