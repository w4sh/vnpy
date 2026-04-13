# 不可变规则 (Invariants)

这些规则是 vn.py 项目的核心架构原则，**永远不能被违反**。

## 核心架构不变性

### 1. 事件驱动架构
```python
# ✅ 正确: 通过 EventEngine 通信
event_engine.publish(EventType.EVENT, data)

# ❌ 错误: 直接调用其他模块
other_module.some_function()
```

### 2. 数据对象不可变性
```python
# ✅ 正确: 创建新对象
new_tick = TickData(
    gateway_name=tick.gateway_name,
    symbol=tick.symbol,
    ...
)

# ❌ 错误: 修改已存在的对象
tick.last_price = 100.0
```

### 3. 异步网关调用
```python
# ✅ 正确: 异步调用
async def connect():
    await gateway.connect()

# ❌ 错误: 同步阻塞调用
gateway.connect()  # 阻塞主线程
```

### 4. 类型安全
```python
# ✅ 正确: 完整类型标注
def process_tick(tick: TickData) -> OrderData:
    ...

# ❌ 错误: 缺少类型标注
def process_tick(tick):
    ...
```

## 技术栈约束

### Python 版本
- **支持**: 3.10, 3.11, 3.12, 3.13
- **推荐**: 3.13
- **禁止**: < 3.10

### 关键依赖版本锁定
```toml
# ❌ 不能修改这些版本
PySide6==6.8.2.1
ta-lib==0.6.4
```

### 包管理器
- **强制**: uv
- **禁止**: pip (除了特殊情况)

### 特殊安装源
```bash
# ta-lib 必须从自定义镜像
uv pip install ta-lib==0.6.4 --index=https://pypi.vnpy.com --system
```

## 代码质量约束

### 必须通过的检查
```bash
ruff check .      # 必须无错误
mypy vnpy         # 必须无错误
pytest tests/     # 核心测试必须通过
```

### 代码风格
- **自动格式化**: ruff format
- **忽略规则**: 仅 E501 (行长度)
- **类型检查**: 严格模式 (disallow_untyped_defs)

## 性能约束

### 事件系统
- **延迟**: < 1ms
- **吞吐**: > 10000 events/sec

### 数据处理
- **优先**: Polars > Pandas
- **避免**: 不必要的数据复制
- **优化**: 向量化操作

### 内存使用
- **避免**: 大对象长期持有
- **释放**: 及时清理不再需要的数据

## 安全约束

### 敏感信息
- **API密钥**: 环境变量或配置文件，不提交代码
- **交易凭证**: 加密存储
- **日志**: 不记录敏感信息

### 输入验证
- **所有外部输入**: 必须验证
- **类型检查**: 使用类型标注和运行时验证
- **边界检查**: 数组访问、数值范围

## 测试约束

### 覆盖率目标
- **核心模块** (vnpy/trader, vnpy/event): > 80%
- **Alpha模块** (vnpy/alpha): > 70%
- **其他模块**: > 60%

### 测试类型
- **单元测试**: 所有公共API
- **集成测试**: 关键工作流
- **性能测试**: 事件系统、数据处理

---

## 违反后果

如果违反这些不变性规则:

1. **架构破坏**: 系统变得不可维护
2. **性能下降**: 交易延迟增加
3. **安全风险**: 资金或数据泄露
4. **兼容性**: 版本升级失败

---

**记住: 这些规则是 vn.py 的基础，永远不能被违反!**
