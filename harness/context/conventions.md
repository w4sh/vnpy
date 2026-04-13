# 编码规范 (Conventions)

vn.py 项目遵循的编码风格和最佳实践。

## 命名规范

### 文件命名
```python
# ✅ 正确: 模块使用蛇形命名
event_engine.py
order_manager.py
tick_data.py

# ❌ 错误
EventEngine.py
orderManager.py
tick-data.py
```

### 类命名
```python
# ✅ 正确: 帕斯卡命名法
class EventEngine:
class OrderManager:
class TickData:

# ❌ 错误
class event_engine:
class order_manager:
```

### 函数命名
```python
# ✅ 正确: 蛇形命名法
def send_order():
def process_tick():
def calculate_returns():

# ❌ 错误
def SendOrder():
def processTick():
```

### 常量命名
```python
# ✅ 正确: 全大写
MAX_ORDER_SIZE = 100
DEFAULT_TIMEOUT = 30
EVENT_TICK = "eTick"

# ❌ 错误
max_order_size = 100
defaultTimeout = 30
```

---

## 类型标注规范

### 公共函数必须有类型标注
```python
# ✅ 正确
def process_tick(tick: TickData) -> OrderData:
    """处理行情数据并生成订单"""
    return OrderData(...)

# ❌ 错误
def process_tick(tick):
    return OrderData(...)
```

### 复杂类型使用 TypeAlias
```python
# ✅ 正确
from typing import TypeAlias, Dict

TickDataDict: TypeAlias = Dict[str, TickData]

def process_ticks(ticks: TickDataDict) -> List[OrderData]:
    ...

# ❌ 错误
def process_ticks(ticks: dict):
    ...
```

### Optional 类型
```python
# ✅ 正确
from typing import Optional

def get_price(symbol: str) -> Optional[float]:
    ...

# ❌ 错误
def get_price(symbol):  # 可能返回 None
    ...
```

---

## 文档字符串规范

### Google 风格文档字符串
```python
# ✅ 正确
def send_order(
    symbol: str,
    exchange: Exchange,
    direction: Direction,
    offset: Offset,
    price: float,
    volume: float,
) -> str:
    """
    发送订单。

    Args:
        symbol: 代码
        exchange: 交易所
        direction: 方向
        offset: 开平仓
        price: 价格
        volume: 数量

    Returns:
        订单ID

    Raises:
        ValueError: 参数无效
    """
    ...

# ❌ 错误
def send_order(symbol, exchange, ...):
    # 发送订单
    ...
```

### 类文档字符串
```python
# ✅ 正确
class EventEngine:
    """
    事件引擎。

    负责事件的路由、分发和处理，使用单例模式确保全局唯一。

    Attributes:
        _timer: 定时器
        _port: 端口
    """
    ...
```

---

## 导入规范

### 导入顺序
```python
# 1. 标准库
import sys
from abc import ABC, abstractmethod

# 2. 第三方库
import numpy as np
import polars as pl
from PySide6.QtCore import Signal

# 3. 本地模块
from vnpy.trader.object import TickData
from vnpy.event import Event, EventEngine
```

### 避免通配符导入
```python
# ❌ 错误
from vnpy.trader.object import *

# ✅ 正确
from vnpy.trader.object import TickData, OrderData, TradeData
```

---

## 异常处理规范

### 明确异常类型
```python
# ✅ 正确
try:
    price = float(user_input)
except ValueError as e:
    logger.error(f"Invalid price: {user_input}")
    raise

# ❌ 错误
try:
    price = float(user_input)
except:  # 裸 except
    pass
```

### 上下文管理器
```python
# ✅ 正确: 使用上下文管理器
with open("data.csv", "r") as f:
    data = f.read()

# ❌ 错误: 手动关闭
f = open("data.csv", "r")
data = f.read()
f.close()  # 可能不执行
```

---

## 日志规范

### 使用 logger 而非 print
```python
# ✅ 正确
from loguru import logger

logger.info("Order sent")
logger.error(f"Order failed: {e}")

# ❌ 错误
print("Order sent")
print(f"Error: {e}")
```

### 日志级别
```python
logger.debug("调试信息")     # 开发调试
logger.info("正常信息")       # 重要事件
logger.warning("警告信息")   # 潜在问题
logger.error("错误信息")     # 错误发生
logger.critical("严重错误")  # 系统崩溃
```

---

## 数据处理规范

### 优先使用 Polars
```python
# ✅ 正确: 大数据用 Polars
import polars as pl

df = pl.read_csv("large_data.csv")
result = df.filter(pl.col("price") > 100)

# 可接受: 小数据用 Pandas
import pandas as pd

df = pd.read_csv("small_data.csv")
result = df[df["price"] > 100]
```

### 向量化操作
```python
# ❌ 慢速: Python 循环
squares = []
for x in numbers:
    squares.append(x ** 2)

# ✅ 快速: NumPy 向量化
import numpy as np
squares = np.array(numbers) ** 2
```

---

## 异步编程规范

### 异步函数命名
```python
# ✅ 正确: 异步函数加 a_ 前缀
async def connect():
    ...

async def send_order_async():
    ...

# ❌ 错误: 异步函数不加标识
async def connect():
    ...

def send_order_async():  # 实际不是异步
    ...
```

### await 使用
```python
# ✅ 正确: 立即 await
result = await async_function()

# ❌ 错误: 忘记 await
result = async_function()  # 返回 coroutine
```

---

## 测试规范

### 测试命名
```python
# ✅ 正确: test_ 前缀
def test_create_order():
    ...

def test_order_failed():
    ...

class TestOrderManager:
    ...

# ❌ 错误
def create_order_test():
    ...
```

### pytest fixture
```python
# ✅ 正确: 使用 fixture
@pytest.fixture
def sample_tick():
    return TickData(...)

def test_process(sample_tick):
    result = process_tick(sample_tick)
    assert result.symbol == "IF2501"
```

---

## Git 提交规范

### 提交信息格式
```bash
# ✅ 正确: 类型(模块): 简短描述
git commit -m "feat(trader): 添加订单撤销功能"
git commit -m "fix(event): 修复事件重复分发问题"
git commit -m "docs: 更新 API 文档"
git commit -m "test(trader): 添加订单测试用例"

# ❌ 错误
git commit -m "添加功能"
git commit -m "fix"
git commit -m "wip"
```

### 提交类型
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `test`: 测试相关
- `refactor`: 重构
- `style`: 代码风格
- `perf`: 性能优化
- `chore`: 构建/工具

---

## 性能优化规范

### 避免过早优化
```python
# ✅ 正确: 先写清晰代码，再优化
def process_data(data):
    return data.transform()

# 性能分析后再决定是否优化
```

### 使用 profile 优化
```bash
# 性能分析
python -m cProfile -s time script.py

# 找到瓶颈后再优化
```

---

## 代码审查规范

### 审查清单
- [ ] 遵循命名规范
- [ ] 有类型标注
- [ ] 有文档字符串
- [ ] 通过 ruff 检查
- [ ] 通过 mypy 检查
- [ ] 有对应测试
- [ ] 性能可接受
- [ ] 无安全漏洞

---

## 参考资源

- [PEP 8](https://peps.python.org/pep-0008/)
- [PEP 484](https://peps.python.org/pep-0484/) - 类型标注
- [Google Python 风格指南](https://google.github.io/styleguide/pyguide.html)
- [Loguru 文档](https://github.com/Delgan/loguru)
