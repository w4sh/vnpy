# 常见陷阱 (Pitfalls)

在 vn.py 项目开发中容易遇到的问题和解决方案。

## 依赖管理陷阱

### 问题 1: ta-lib 安装失败
```bash
# ❌ 错误方式
pip install ta-lib

# ✅ 正确方式
uv pip install ta-lib==0.6.4 --index=https://pypi.vnpy.com --system
```

### 问题 2: PySide6 版本不匹配
```python
# ❌ 错误: 修改版本号
PySide6==6.9.0

# ✅ 正确: 保持锁定版本
PySide6==6.8.2.1  # 不要修改!
```

### 问题 3: uv vs pip 混用
```bash
# ❌ 错误: 混用包管理器
uv pip install requests
pip install numpy

# ✅ 正确: 统一使用 uv
uv pip install requests numpy
```

---

## 代码风格陷阱

### 问题 4: 手动格式化
```bash
# ❌ 浪费时间手动格式化
# ✅ 使用 ruff format 自动格式化
ruff format .
```

### 问题 5: 忽略类型检查
```python
# ❌ 跳过类型标注
def process_data(data):  # 类型?
    return data.transform()

# ✅ 完整类型标注
def process_data(data: pl.DataFrame) -> pl.DataFrame:
    return data.transform()
```

### 问题 6: 抑制错误警告
```python
# ❌ 滥用 # noqa
result = risky_operation()  # noqa

# ✅ 修复问题，不抑制警告
result = safe_operation()
```

---

## 架构陷阱

### 问题 7: 绕过事件系统
```python
# ❌ 直接调用
strategy.on_tick(tick)

# ✅ 通过事件引擎
event_engine.publish(EVENT_TICK, tick)
```

### 问题 8: 修改数据对象
```python
# ❌ 修改已有对象
order.status = Status.ALLTRADED

# ✅ 创建新对象
new_order = OrderData(
    gateway_name=order.gateway_name,
    orderID=order.orderID,
    status=Status.ALLTRADED,
    ...
)
```

### 问题 9: 同步网关调用
```python
# ❌ 阻塞调用
def send_order():
    gateway.connect()  # 阻塞!
    return gateway.send_order(req)

# ✅ 异步调用
async def send_order():
    await gateway.connect()
    return await gateway.send_order(req)
```

---

## 性能陷阱

### 问题 10: 不必要的数据复制
```python
# ❌ 创建副本
df2 = df.copy()
df3 = df2.copy()

# ✅ 使用引用或视图
df2 = df
df3 = df
```

### 问题 11: Pandas vs Polars 选择
```python
# ❌ 大数据用 Pandas
import pandas as pd
df = pd.read_csv("large_file.csv")  # 慢

# ✅ 大数据用 Polars
import polars as pl
df = pl.read_csv("large_file.csv")  # 快
```

### 问题 12: 循环处理
```python
# ❌ 慢速循环
for tick in ticks:
    process_tick(tick)

# ✅ 向量化处理
import numpy as np
data = np.array([tick.last_price for tick in ticks])
process_data(data)
```

---

## 测试陷阱

### 问题 13: 跳过测试
```bash
# ❌ "代码看起来没问题，跳过测试"
# ✅ 必须运行测试
pytest tests/
```

### 问题 14: 测试不充分
```python
# ❌ 只测试成功路径
def test_success():
    result = process_tick(valid_tick)
    assert result is not None

# ✅ 测试失败路径
def test_failure():
    with pytest.raises(ValueError):
        process_tick(invalid_tick)
```

### 问题 15: 脆弱的测试
```python
# ❌ 脆弱断言
assert result is not None

# ✅ 具体验证
assert result.symbol == "IF2501"
assert result.volume == 100
assert result.status == Status.NOTTRADED
```

---

## 安全陷阱

### 问题 16: 硬编码凭证
```python
# ❌ 硬编码 API 密钥
API_KEY = "sk_live_abc123"

# ✅ 环境变量
import os
API_KEY = os.getenv("API_KEY")
```

### 问题 17: 日志泄露
```python
# ❌ 记录敏感信息
logger.info(f"Password: {password}")

# ✅ 脱敏记录
logger.info(f"Password: {'*' * len(password)}")
```

### 问题 18: 不验证输入
```python
# ❌ 直接使用外部输入
price = float(user_input)

# ✅ 验证后使用
try:
    price = float(user_input)
    if price <= 0:
        raise ValueError("Price must be positive")
except ValueError:
    handle_error()
```

---

## Git 工作流陷阱

### 问题 19: 跳过代码检查
```bash
# ❌ 直接提交
git add .
git commit -m "done"

# ✅ 先检查再提交
ruff format .
ruff check .
mypy vnpy
pytest tests/
git add .
git commit -m "done"
```

### 问题 20: 模糊的提交信息
```bash
# ❌ 不清晰的提交
git commit -m "fix"
git commit -m "update"
git commit -m "wip"

# ✅ 清晰的提交
git commit -m "fix(trader): 修复订单状态更新逻辑"
git commit -m "feat(event): 添加事件过滤器"
```

---

## 调试陷阱

### 问题 21: 过度使用 print
```python
# ❌ 到处 print
print(f"Debug: {var1}")
print(f"Debug: {var2}")

# ✅ 使用 logger
logger.debug(f"Var1: {var1}, Var2: {var2}")
```

### 问题 22: 盲目重启
```bash
# ❌ 遇到问题就重启
# ✅ 先查看日志
tail -f vnpy/trader/logs/*.log
```

---

## 翻译陷阱

### 问题 23: 修改翻译后不编译
```bash
# ❌ 只编辑 .po 文件
vim vnpy/trader/locale/zh_CN/LC_MESSAGES/vnpy.po

# ✅ 编译成 .mo 文件
msgfmt vnpy/trader/locale/zh_CN/LC_MESSAGES/vnpy.po \
      -o vnpy/trader/locale/zh_CN/LC_MESSAGES/vnpy.mo
```

---

## 添加新陷阱

当你遇到新问题时，请将其添加到此文件，并更新 `harness/feedback/improvements.md`。

格式:
```markdown
### 问题 XX: [标题]
[描述]
[错误示例]
[正确示例]
```
