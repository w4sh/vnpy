# VnPy 测试指南

本目录包含 vnpy 项目的所有测试代码。

## 测试组织

```
tests/
├── conftest.py              # 共享的 pytest fixtures 和配置
├── data/                    # 测试数据文件
├── test_alpha101.py         # Alpha101 因子测试
└── test_trader_objects.py   # 核心交易对象单元测试(示例)
```

## 运行测试

### 基本命令

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_trader_objects.py

# 运行特定测试类
pytest tests/test_trader_objects.py::TestTickData

# 运行特定测试函数
pytest tests/test_trader_objects.py::TestTickData::test_create_tick

# 显示详细输出
pytest -v

# 显示打印输出
pytest -s
```

### 高级命令

```bash
# 并行运行测试(加快速度)
pytest -n auto

# 生成覆盖率报告
pytest --cov=vnpy --cov-report=html

# 只运行单元测试
pytest -m unit

# 跳过慢速测试
pytest -m "not slow"

# 跳过集成测试
pytest -m "not integration"

# 快速测试(非慢速,无覆盖率)
pytest -m "not slow" --no-cov -q
```

## 编写测试

### 测试文件命名

- 测试文件名以 `test_` 开头
- 测试类名以 `Test` 开头
- 测试函数名以 `test_` 开头

### 测试示例

```python
"""
测试 vnpy.trader.object 模块
"""
import pytest
from datetime import datetime
from vnpy.trader.object import TickData


class TestTickData:
    """测试 TickData 对象"""

    def test_create_tick(self):
        """测试创建 TickData 对象"""
        tick = TickData(
            gateway_name="CTP",
            symbol="IF2501",
            exchange="CFFEX",
            datetime=datetime(2025, 1, 10, 9, 30, 0),
            last_price=3500.0,
        )

        assert tick.symbol == "IF2501"
        assert tick.last_price == 3500.0

    @pytest.mark.unit
    def test_tick_vt_symbol(self):
        """测试 vt_symbol 属性"""
        tick = TickData(
            gateway_name="CTP",
            symbol="IF2501",
            exchange="CFFEX",
            datetime=datetime.now(),
        )

        assert tick.vt_symbol == "IF2501.CFFEX"
```

### 使用 Fixtures

```python
# 在 conftest.py 中定义共享 fixtures
@pytest.fixture
def sample_tick():
    """提供示例 TickData 对象"""
    return TickData(
        gateway_name="CTP",
        symbol="IF2501",
        exchange="CFFEX",
        datetime=datetime.now(),
        last_price=3500.0,
    )

# 在测试中使用
def test_tick_price(sample_tick):
    assert sample_tick.last_price == 3500.0
```

### 测试标记

使用 pytest 标记来分类测试:

```python
@pytest.mark.unit
def test_fast_unit_test():
    """快速单元测试"""
    pass

@pytest.mark.integration
def test_integration_test():
    """集成测试"""
    pass

@pytest.mark.slow
def test_slow_test():
    """慢速测试"""
    pass
```

## 测试最佳实践

1. **隔离性**: 每个测试应该独立运行,不依赖其他测试
2. **清晰性**: 测试名称应该清楚地描述测试的内容
3. **简洁性**: 测试应该简单直接,一个测试只测试一个功能
4. **可重复性**: 测试应该可以重复运行,结果一致
5. **快速性**: 单元测试应该快速运行,慢速测试标记为 `@pytest.mark.slow`

## 覆盖率目标

- 核心模块(vnpy/trader, vnpy/event): 目标覆盖率 > 80%
- Alpha 模块(vnpy/alpha): 目标覆盖率 > 70%
- 其他模块: 目标覆盖率 > 60%

查看覆盖率报告:
```bash
pytest --cov=vnpy --cov-report=html
open htmlcov/index.html  # macOS
```

## 参考资源

- [Pytest 文档](https://docs.pytest.org/)
- [Pytest 中文文档](https://www.osgeo.cn/pytest/)
