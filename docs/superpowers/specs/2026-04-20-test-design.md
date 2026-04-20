# 持仓管理系统第二阶段 - 测试设计文档

**项目:** vn.py 量化交易平台
**文档类型:** 测试规格说明书
**设计日期:** 2026-04-20
**版本:** 1.1

---

## 1. 测试策略

### 1.1 测试原则

每个 Task 完成后必须执行：
1. **功能测试** - 验证新功能正常工作
2. **边界值测试** - 验证输入边界条件
3. **SQL 注入测试** - 验证安全防护
4. **XSS 测试** - 验证前端防护
5. **性能测试** - 验证响应时间
6. **回归测试** - 确保不影响原有功能

### 1.2 测试通过标准

**必须满足：**
- ✅ 所有测试用例 100% 通过
- ✅ 代码覆盖率 > 80%
- ✅ 无关键安全漏洞（SQL注入、XSS）
- ✅ 性能指标达标（见下方）
- ✅ 回归测试通过

**性能指标（基于 1000 持仓、100,000 交易）：**
- API 响应时间 < 1 秒
- 页面加载时间 < 3 秒
- 分页查询 < 500ms

---

## 2. 后端 API 测试

### 2.1 策略管理 API 测试

#### 功能测试

| ID | 测试场景 | 验证点 | 优先级 |
|----|----------|--------|--------|
| TC-STR-001 | 更新策略描述 | 成功更新，返回200 | P0 |
| TC-STR-002 | 更新策略风险等级 | 成功更新，返回200 | P0 |
| TC-STR-003 | 更新受保护字段 | 返回400错误 | P0 |
| TC-STR-004 | 软删除策略 | status='deleted' | P0 |
| TC-STR-005 | 删除后查询 | 返回404 | P0 |
| TC-STR-006 | Dirty 状态重算 | recalc_status='dirty' 后重算 | P0 |
| TC-STR-007 | 状态重算完成 | recalc_status='clean' | P0 |
| TC-STR-008 | 重算失败状态 | recalc_status='failed' | P0 |

#### 状态机制测试

```python
def test_strategy_recalc_status_lifecycle(self, client):
    """测试：策略重算状态生命周期"""
    session = get_db_session()

    # 创建策略（初始状态为 clean）
    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status='clean'
    )
    session.add(strategy)
    session.commit()
    strategy_id = strategy.id

    # 验证初始状态
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'clean'
    assert strategy.recalc_retry_count == 0

    # 标记 dirty
    mark_strategy_dirty(strategy_id, session)
    session.commit()

    # 验证 dirty 状态
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'dirty'
    assert strategy.recalc_retry_count == 0

    # 执行重算
    recalc_strategy(strategy_id, session)

    # 验证 clean 状态
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'clean'
    assert strategy.recalc_retry_count == 0
    assert strategy.last_error is None
```

#### 恢复机制测试

```python
def test_recalc_timeout_recovery(self, client):
    """测试：重算超时恢复机制"""
    session = get_db_session()

    # 创建策略
    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status='recomputing',
        updated_at=datetime.now() - timedelta(minutes=35)  # 超过30分钟
    )
    session.add(strategy)
    session.commit()
    strategy_id = strategy.id

    # 执行恢复任务
    from app import recover_stuck_strategies
    recover_stuck_strategies()

    # 验证状态已重置为 dirty
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'dirty'
    assert '重算超时' in strategy.last_error
```

#### 并发控制测试

```python
def test_concurrent_recalc_prevention(self, client):
    """测试：并发重算防护（乐观锁）"""
    session1 = get_db_session()
    session2 = get_db_session()

    # 创建 dirty 策略
    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status='dirty'
    )
    session1.add(strategy)
    session1.commit()
    strategy_id = strategy.id

    # Worker 1 尝试获取执行权
    rows1 = session1.query(Strategy)\
        .filter_by(id=strategy_id, recalc_status='dirty')\
        .update({'recalc_status': 'recomputing'}, synchronize_session=False)
    session1.commit()

    assert rows1 == 1  # Worker 1 成功获取

    # Worker 2 尝试获取执行权
    rows2 = session2.query(Strategy)\
        .filter_by(id=strategy_id, recalc_status='dirty')\
        .update({'recalc_status': 'recomputing'}, synchronize_session=False)
    session2.commit()

    assert rows2 == 0  # Worker 2 被拒绝

    # 验证状态为 recomputing
    strategy = session1.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'recomputing'

    session1.close()
    session2.close()
```

#### 边界值测试

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|----|----------|------|----------|--------|
| TC-STR-101 | 描述最大长度 | 500字符 | 200 OK | P0 |
| TC-STR-102 | 描述超长 | 501字符 | 400 Bad Request | P0 |
| TC-STR-103 | 风险等级枚举 | 所有合法值 | 200 OK | P0 |

#### SQL 注入测试

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|----|----------|------|----------|--------|
| TC-STR-201 | 描述字段注入 | SQL注入载荷 | 400 或转义 | P0 |
| TC-STR-202 | 风险等级注入 | SQL注入载荷 | 400 Bad Request | P0 |

---

### 2.2 交易记录 API 测试

#### 功能测试

| ID | 测试场景 | 验证点 | 优先级 |
|----|----------|--------|--------|
| TC-TRN-001 | 修改价格 | 成功更新，记录审计 | P0 |
| TC-TRN-002 | 缺少原因 | 返回400错误 | P0 |
| TC-TRN-003 | 修改触发重算 | recalc_status='dirty' | P0 |
| TC-TRN-004 | 审计日志记录 | 记录旧值和新值 | P0 |

#### 状态传播测试

```python
def test_transaction_triggers_dirty_flag(self, client):
    """测试：交易修改触发 dirty 状态"""
    session = get_db_session()

    position = Position(
        symbol="000001.SZSE",
        quantity=1000,
        cost_price=10.00,
        strategy_id=1
    )
    session.add(position)
    session.commit()

    transaction = Transaction(
        position_id=position.id,
        strategy_id=position.strategy_id,
        transaction_type="buy",
        symbol="000001.SZSE",
        quantity=1000,
        price=10.00,
        amount=10000
    )
    session.add(transaction)
    session.commit()
    transaction_id = transaction.id

    # 修改交易
    response = client.put(f'/api/transactions/{transaction_id}',
                        json={"price": 15.00, "reason": "测试"})
    assert response.status_code == 200

    # 验证策略被标记为 dirty
    strategy = session.query(Strategy).get(position.strategy_id)
    assert strategy.recalc_status == 'dirty'
    assert strategy.recalc_retry_count == 0
```

#### 边界值测试

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|----|----------|------|----------|--------|
| TC-TRN-101 | 价格最小值 | 0.01 | 200 OK | P0 |
| TC-TRN-102 | 价格为零 | 0.00 | 400 Bad Request | P0 |
| TC-TRN-103 | 数量最小值 | 1 | 200 OK | P0 |
| TC-TRN-104 | 手续费为负 | -5.0 | 400 Bad Request | P0 |

---

### 2.3 持仓计算规则测试

#### 加权平均成本法测试

```python
def test_weighted_average_cost_calculation(self, client):
    """测试：加权平均成本法计算"""
    session = get_db_session()

    # 创建策略和持仓
    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status='clean'
    )
    session.add(strategy)
    session.commit()

    position = Position(
        symbol="000001.SZSE",
        strategy_id=strategy.id,
        quantity=0,
        cost_price=0.00,
        current_price=10.00
    )
    session.add(position)
    session.commit()
    position_id = position.id

    # 第一次买入：1000股 @ 10.00
    txn1 = Transaction(
        position_id=position_id,
        strategy_id=strategy.id,
        transaction_type="buy",
        symbol="000001.SZSE",
        quantity=1000,
        price=10.00,
        fee=5.0,
        amount=10005
    )
    session.add(txn1)
    session.commit()

    # 触发重算
    position = session.query(Position).get(position_id)
    _recalc_position_cost(position, session)

    # 验证：成本 = (1000 * 10.00 + 5) / 1000 = 10.005
    position = session.query(Position).get(position_id)
    assert position.quantity == 1000
    assert abs(position.cost_price - 10.005) < 0.001

    # 第二次买入：500股 @ 12.00
    txn2 = Transaction(
        position_id=position_id,
        strategy_id=strategy.id,
        transaction_type="buy",
        symbol="000001.SZSE",
        quantity=500,
        price=12.00,
        fee=3.0,
        amount=6003
    )
    session.add(txn2)
    session.commit()

    # 触发重算
    position = session.query(Position).get(position_id)
    _recalc_position_cost(position, session)

    # 验证：新成本 = (10.005 * 1000 + 6003) / 1500 = 10.672
    position = session.query(Position).get(position_id)
    assert position.quantity == 1500
    assert abs(position.cost_price - 10.672) < 0.001

    # 卖出：300股 @ 11.00
    txn3 = Transaction(
        position_id=position_id,
        strategy_id=strategy.id,
        transaction_type="sell",
        symbol="000001.SZSE",
        quantity=300,
        price=11.00,
        fee=3.0,
        amount=3297
    )
    session.add(txn3)
    session.commit()

    # 触发重算
    position = session.query(Position).get(position_id)
    _recalc_position_cost(position, session)

    # 验证：卖出后成本不变，数量减少
    position = session.query(Position).get(position_id)
    assert position.quantity == 1200
    assert abs(position.cost_price - 10.672) < 0.001  # 成本不变

    # 验证已实现盈亏 = (11.00 - 10.672) * 300 - 3 = 95.4
    # 应该记录在审计日志中

def test_full_recalculation_flow(self, client):
    """测试：完整重算流程（单一事务）"""
    session = get_db_session()

    # 创建测试数据
    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status='clean'
    )
    session.add(strategy)
    session.commit()
    strategy_id = strategy.id

    # 创建多个持仓和交易
    positions = []
    for i in range(3):
        position = Position(
            symbol=f"00000{i+1}.SZSE",
            strategy_id=strategy_id,
            quantity=1000 * (i+1),
            cost_price=10.00 + i,
            current_price=12.00 + i
        )
        session.add(position)
        positions.append(position)
    session.commit()

    # 修改交易触发dirty
    transaction = Transaction(
        position_id=positions[0].id,
        strategy_id=strategy_id,
        transaction_type="buy",
        symbol="000001.SZSE",
        quantity=500,
        price=15.00,
        amount=7500
    )
    session.add(transaction)
    session.commit()

    # 标记dirty
    mark_strategy_dirty(strategy_id, session)
    session.commit()

    # 验证dirty状态
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'dirty'

    # 执行重算
    recalc_strategy(strategy_id, session)

    # 验证重算完成
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'clean'
    assert strategy.recalc_retry_count == 0
    assert strategy.last_error is None

    # 验证持仓数据已更新
    for position in positions:
        position = session.query(Position).get(position.id)
        assert position.market_value == position.current_price * position.quantity
        assert position.profit_loss_pct > 0

def test_recalculation_failure_and_retry(self, client):
    """测试：重算失败和重试机制"""
    session = get_db_session()

    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status='dirty',
        recalc_retry_count=0
    )
    session.add(strategy)
    session.commit()
    strategy_id = strategy.id

    # 模拟重算失败（破坏数据完整性）
    # 删除所有持仓，导致重算失败
    positions = session.query(Position)\
        .filter_by(strategy_id=strategy_id)\
        .all()
    for p in positions:
        session.delete(p)
    session.commit()

    # 尝试重算（应该失败）
    try:
        recalc_strategy(strategy_id, session)
        assert False, "应该抛出异常"
    except Exception:
        pass

    # 调用失败处理
    handle_recalc_failure(strategy_id, "模拟重算失败")

    # 验证失败状态（独立事务）
    session = get_db_session()
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'dirty'  # 第1次失败，保持 dirty
    assert strategy.recalc_retry_count == 1
    assert "模拟重算失败" in strategy.last_error

    session.close()

    # 模拟第3次失败
    for i in range(2):
        handle_recalc_failure(strategy_id, f"模拟重算失败{i+2}")

    # 验证达到最大重试次数
    session = get_db_session()
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'failed'  # 第3次失败，标记为 failed
    assert strategy.recalc_retry_count == 3
    assert "Max retries exceeded" in strategy.last_error

    session.close()
```

#### 事务边界测试

```python
def test_recalc_transaction_rollback(self, client):
    """测试：重算失败时事务回滚"""
    session = get_db_session()

    # 创建策略和持仓
    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status='dirty'
    )
    session.add(strategy)
    session.commit()
    strategy_id = strategy.id

    position = Position(
        symbol="000001.SZSE",
        strategy_id=strategy_id,
        quantity=1000,
        cost_price=10.00,
        current_price=12.00
    )
    session.add(position)
    session.commit()
    position_id = position.id

    # 记录原始数据
    original_quantity = position.quantity
    original_cost = position.cost_price

    # 模拟重算过程中的异常
    try:
        # 修改部分数据
        position.quantity = 2000
        position.cost_price = 15.00

        # 模拟异常
        raise Exception("模拟重算失败")
    except Exception:
        session.rollback()

    # 验证数据未改变（回滚成功）
    session = get_db_session()
    position = session.query(Position).get(position_id)
    assert position.quantity == original_quantity
    assert position.cost_price == original_cost

    # 验证策略状态未改变
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'dirty'  # 仍为 dirty

    session.close()

def test_recalc_status_consistency(self, client):
    """测试：状态字段一致性（无 is_dirty 冗余）"""
    session = get_db_session()

    # 创建策略（不设置 is_dirty）
    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status='clean'
    )
    session.add(strategy)
    session.commit()
    strategy_id = strategy.id

    # 验证只有 recalc_status 字段
    strategy = session.query(Strategy).get(strategy_id)
    assert hasattr(strategy, 'recalc_status')
    assert strategy.recalc_status == 'clean'

    # 标记 dirty
    mark_strategy_dirty(strategy_id, session)
    session.commit()

    # 验证状态改变
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'dirty'

    # 执行重算
    recalc_strategy(strategy_id, session)

    # 验证状态变为 clean
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'clean'

    session.close()
```

#### 完整状态机流转测试

```python
def test_complete_state_machine_transitions(self, client):
    """测试：完整状态机流转路径"""
    session = get_db_session()

    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status='clean'
    )
    session.add(strategy)
    session.commit()
    strategy_id = strategy.id

    # 路径1: clean → dirty → recomputing → clean
    assert strategy.recalc_status == 'clean'

    mark_strategy_dirty(strategy_id, session)
    session.commit()
    assert strategy.recalc_status == 'dirty'

    rows = session.query(Strategy)\
        .filter_by(id=strategy_id, recalc_status='dirty')\
        .update({'recalc_status': 'recomputing'})
    session.commit()
    assert rows == 1
    assert strategy.recalc_status == 'recomputing'

    recalc_strategy(strategy_id, session)
    assert strategy.recalc_status == 'clean'

    # 路径2: clean → dirty → recomputing → failed
    mark_strategy_dirty(strategy_id, session)
    session.commit()

    rows = session.query(Strategy)\
        .filter_by(id=strategy_id, recalc_status='dirty')\
        .update({'recalc_status': 'recomputing'})
    session.commit()

    # 模拟重算失败3次
    for i in range(3):
        try:
            raise Exception("模拟失败")
        except:
            handle_recalc_failure(strategy_id, f"失败{i+1}")

    session = get_db_session()
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'failed'

    # 路径3: failed → dirty → recomputing → clean（重试恢复）
    rows = session.query(Strategy)\
        .filter_by(id=strategy_id, recalc_status='failed')\
        .update({'recalc_status': 'dirty', 'recalc_retry_count': 0})
    session.commit()

    recalc_strategy(strategy_id, session)
    assert strategy.recalc_status == 'clean'

    session.close()
```

#### Heartbeat 机制测试

```python
def test_recalc_heartbeat_updates_updated_at(self, client):
    """测试：重算过程中 updated_at 持续更新（heartbeat）"""
    from datetime import datetime, timedelta
    import time

    session = get_db_session()

    # 创建测试数据（模拟长时间重算）
    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status='dirty'
    )
    session.add(strategy)

    # 创建100个持仓（模拟大数据量）
    for i in range(100):
        position = Position(
            symbol=f"00000{i}.SZSE",
            strategy_id=strategy.id,
            quantity=1000,
            cost_price=10.00 + i * 0.1,
            current_price=12.00 + i * 0.1
        )
        session.add(position)
    session.commit()
    strategy_id = strategy.id

    # 记录初始 updated_at
    initial_updated_at = strategy.updated_at

    # 标记开始重算
    rows = session.query(Strategy)\
        .filter_by(id=strategy_id, recalc_status='dirty')\
        .update({'recalc_status': 'recomputing'})
    session.commit()

    # 执行重算（需要一定时间）
    import time
    time.sleep(2)  # 模拟耗时操作

    recalc_strategy(strategy_id, session)

    # 验证 updated_at 在重算过程中被更新
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.updated_at > initial_updated_at

    session.close()
```

#### 部分重算中断测试

```python
def test_partial_recalc_interrupted_by_exception(self, client):
    """测试：重算循环中异常时的原子性"""
    session = get_db_session()

    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status='dirty'
    )
    session.add(strategy)

    # 创建多个持仓
    positions = []
    for i in range(5):
        position = Position(
            symbol=f"00000{i}.SZSE",
            strategy_id=strategy.id,
            quantity=1000 * (i+1),
            cost_price=10.00,
            current_price=12.00
        )
        session.add(position)
        positions.append(position)
    session.commit()

    # 记录原始数据
    original_data = {}
    for p in positions:
        original_data[p.id] = {
            'quantity': p.quantity,
            'cost_price': p.cost_price
        }

    # 模拟在处理第3个position时抛出异常
    original_recalc = _recalc_position_cost

    def mock_recalc_with_exception(position, session):
        if position.symbol == '000002.SZSE':  # 第3个
            raise Exception("模拟处理第3个持仓时失败")
        return original_recalc(position, session)

    # 替换函数
    import app
    app._recalc_position_cost = mock_recalc_with_exception

    # 执行重算（应该失败）
    try:
        recalc_strategy(strategy.id, session)
        assert False, "应该抛出异常"
    except Exception:
        pass

    # 恢复原函数
    app._recalc_position_cost = original_recalc

    # 验证：所有position数据未改变（原子性）
    for p in positions:
        p = session.query(Position).get(p.id)
        assert p.quantity == original_data[p.id]['quantity']
        assert p.cost_price == original_data[p.id]['cost_price']

    # 验证：策略状态仍为dirty
    strategy = session.query(Strategy).get(strategy.id)
    assert strategy.recalc_status == 'dirty'  # 重算失败

    session.close()
```

#### 实际并发重算测试

```python
def test_actual_concurrent_recalc_execution(self, client):
    """测试：两个线程同时执行 recalc_strategy"""
    import threading
    import time

    session = get_db_session()

    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status='dirty'
    )
    session.add(strategy)
    session.commit()
    strategy_id = strategy.id

    # 创建两个线程同时执行重算
    results = {'success': 0, 'failed': 0}
    lock = threading.Lock()

    def worker(worker_id):
        try:
            session = get_db_session()
            recalc_strategy(strategy_id, session)
            with lock:
                results['success'] += 1
        except Exception as e:
            with lock:
                results['failed'] += 1
        finally:
            session.close()

    thread1 = threading.Thread(target=worker, args=(1,))
    thread2 = threading.Thread(target=worker, args=(2,))

    # 同时启动
    thread1.start()
    thread2.start()

    # 等待完成
    thread1.join()
    thread2.join()

    # 验证：只有一个成功，另一个失败
    assert results['success'] == 1
    assert results['failed'] == 1

    # 验证：策略状态为clean（成功的线程）
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'clean'

    session.close()
```

#### 端到端数据一致性测试

```python
def test_end_to_end_data_consistency(self, client):
    """测试：交易修改 → 标记dirty → 重算 → 查询 全链路"""
    session = get_db_session()

    # 创建策略和持仓
    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status='clean'
    )
    session.add(strategy)
    session.commit()
    strategy_id = strategy.id

    position = Position(
        symbol="000001.SZSE",
        strategy_id=strategy_id,
        quantity=1000,
        cost_price=10.00,
        current_price=10.00
    )
    session.add(position)
    session.commit()
    position_id = position.id

    # 记录初始状态
    original_capital = strategy.current_capital
    original_quantity = position.quantity

    # 1. 创建交易（触发标记dirty）
    transaction = Transaction(
        position_id=position_id,
        strategy_id=strategy_id,
        transaction_type="buy",
        symbol="000001.SZSE",
        quantity=500,
        price=12.00,
        fee=5.0,
        amount=6005
    )
    session.add(transaction)
    session.commit()

    # 2. 验证标记为dirty
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'dirty'

    # 3. 执行重算
    recalc_strategy(strategy_id, session)

    # 4. 验证重算完成
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'clean'

    # 5. 验证数据一致性
    position = session.query(Position).get(position_id)

    # 持仓数量 = 1000 + 500 = 1500
    assert position.quantity == 1500

    # 持仓成本 = (10.00 * 1000 + 6005) / 1500 = 10.67
    assert abs(position.cost_price - 10.67) < 0.01

    # 市值 = 1500 * 12.00 = 18000
    assert position.market_value == 18000

    # 盈亏 = 18000 - (10.67 * 1500) = 1995
    assert abs(position.profit_loss - 1995) < 1

    # 策略总资产 = 18000
    assert abs(strategy.current_capital - 18000) < 1

    # 总回报率 = (18000 - 1000000) / 1000000（负值，因为只有一个持仓）
    # 这个值取决于initial_capital的设置

    session.close()
```

#### Scheduler批处理测试

```python
def test_scheduler_batch_processing_multiple_strategies(self, client):
    """测试：Scheduler 批量处理多个 dirty 策略"""
    session = get_db_session()

    # 创建10个dirty策略
    strategy_ids = []
    for i in range(10):
        strategy = Strategy(
            name=f"测试策略{i}",
            initial_capital=1000000 * (i+1),
            recalc_status='dirty'
        )
        session.add(strategy)
        session.commit()
        strategy_ids.append(strategy.id)

    # 为每个策略创建持仓
    for strategy_id in strategy_ids:
        position = Position(
            symbol="000001.SZSE",
            strategy_id=strategy_id,
            quantity=1000,
            cost_price=10.00,
            current_price=12.00
        )
        session.add(position)
    session.commit()

    # 执行批量处理任务（模拟scheduler）
    from app import recalc_dirty_strategies
    recalc_dirty_strategies()

    # 验证：所有策略都被重算
    for strategy_id in strategy_ids:
        strategy = session.query(Strategy).get(strategy_id)
        assert strategy.recalc_status == 'clean', f"策略{strategy_id}未重算"

    session.close()
```

---

### 2.4 分页功能测试

```python
def test_optimistic_lock_concurrent_access(self, client):
    """测试：乐观锁防止并发重算"""
    session1 = get_db_session()
    session2 = get_db_session()

    # 创建 dirty 策略
    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status='dirty'
    )
    session1.add(strategy)
    session1.commit()
    strategy_id = strategy.id

    # Worker 1 尝试获取执行权
    rows_affected1 = session1.query(Strategy)\
        .filter_by(id=strategy_id, recalc_status='dirty')\
        .update({'recalc_status': 'recomputing'}, synchronize_session=False)
    session1.commit()

    # Worker 2 尝试获取执行权
    rows_affected2 = session2.query(Strategy)\
        .filter_by(id=strategy_id, recalc_status='dirty')\
        .update({'recalc_status': 'recomputing'}, synchronize_session=False)
    session2.commit()

    # 验证：Worker 1 成功，Worker 2 失败
    assert rows_affected1 == 1
    assert rows_affected2 == 0

    # 验证最终状态为 recomputing
    strategy = session1.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'recomputing'

    session1.close()
    session2.close()

def test_recovery_from_stuck_recomputing_status(self, client):
    """测试：从卡死的 recomputing 状态恢复"""
    from datetime import datetime, timedelta

    session = get_db_session()

    # 创建卡死的策略（recomputing 状态且超过30分钟）
    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status='recomputing',
        updated_at=datetime.now() - timedelta(minutes=35)
    )
    session.add(strategy)
    session.commit()
    strategy_id = strategy.id

    # 执行恢复任务
    from app import recover_stuck_strategies
    recover_stuck_strategies()

    # 验证状态已重置为 dirty
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'dirty'
    assert '重算超时' in strategy.last_error

    session.close()

def test_no_recovery_for_recent_recomputing(self, client):
    """测试：不重置最近的 recomputing 状态"""
    from datetime import datetime, timedelta

    session = get_db_session()

    # 创建正常的 recomputing 策略（5分钟前）
    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status='recomputing',
        updated_at=datetime.now() - timedelta(minutes=5)
    )
    session.add(strategy)
    session.commit()
    strategy_id = strategy.id

    # 执行恢复任务
    from app import recover_stuck_strategies
    recover_stuck_strategies()

    # 验证状态仍为 recomputing（未超时，不重置）
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'recomputing'
    assert strategy.last_error is None

    session.close()
```

---

### 2.4 分页功能测试

| ID | 测试场景 | 验证点 | 优先级 |
|----|----------|--------|--------|
| TC-PAG-001 | 默认分页 | 每页20条 | P0 |
| TC-PAG-002 | 自定义页大小 | 每页50条 | P0 |
| TC-PAG-003 | 超大页大小 | 限制为100 | P0 |
| TC-PAG-004 | 边界页码 | 第一页/最后一页 | P0 |
| TC-PAG-005 | 空数据集 | 返回空数组 | P0 |

**测试代码：**

```python
def test_pagination_default(self, client):
    """测试：默认分页"""
    # 创建25条测试数据
    for i in range(25):
        position = Position(symbol=f'TEST{i:03d}.SZSE', quantity=100, cost_price=10.00)
        session.add(position)
    session.commit()
    
    # 请求第一页
    response = client.get('/api/positions?page=1')
    assert response.status_code == 200
    
    data = response.json['data']
    pagination = response.json['pagination']
    
    assert len(data) == 20  # 每页20条
    assert pagination['page'] == 1
    assert pagination['total'] == 25
    assert pagination['pages'] == 2
    assert pagination['has_next'] == True
    
    # 请求第二页
    response = client.get('/api/positions?page=2')
    assert response.status_code == 200
    assert len(response.json['data']) == 5  # 剩余5条

def test_pagination_max_per_page(self, client):
    """测试：每页最大数量限制"""
    response = client.get('/api/positions?per_page=200')
    assert response.status_code == 200
    
    pagination = response.json['pagination']
    assert pagination['per_page'] <= 100  # 限制为100
```

---

## 3. 前端测试

### 3.1 功能测试

| ID | 测试场景 | 验证点 | 优先级 |
|----|----------|--------|--------|
| TC-FE-001 | 页面加载 | 4个卡片+3个图表 | P0 |
| TC-FE-002 | 指标卡片刷新 | 30秒自动刷新 | P0 |
| TC-FE-003 | 分页导航 | 上一页/下一页 | P0 |
| TC-FE-004 | Dirty 状态提示 | 显示"数据更新中" | P0 |

### 3.2 XSS 测试

| ID | 测试场景 | 输入 | 验证点 | 优先级 |
|----|----------|------|--------|--------|
| TC-FE-201 | 创建持仓 XSS | <script>alert('XSS')</script> | 脚本不执行 | P0 |
| TC-FE-202 | 搜索框 XSS | 注入载荷 | 脚本不执行 | P0 |

### 3.3 性能测试

| ID | 测试场景 | 数据规模 | 预期指标 | 优先级 |
|----|----------|----------|----------|--------|
| TC-PERF-101 | 持仓列表查询 | 1000条持仓 | < 500ms | P0 |
| TC-PERF-102 | 交易记录查询 | 100,000条记录 | < 1s | P0 |
| TC-PERF-103 | 分页加载 | 每页100条 | < 500ms | P0 |

---

## 4. 回归测试

### 4.1 第一阶段功能

| ID | 功能 | 测试点 | 优先级 |
|----|------|--------|--------|
| TC-REG-001 | 持仓 CRUD | 创建/读取/更新/删除 | P0 |
| TC-REG-002 | 策略创建 | 创建成功 | P0 |
| TC-REG-003 | 分析 API | 正常返回数据 | P0 |
| TC-REG-004 | 行情 API | 更新价格成功 | P0 |
| TC-REG-005 | user_id 字段 | 默认值为1 | P0 |

**user_id 字段测试：**

```python
def test_user_id_default_value(self, client):
    """测试：user_id 默认值为 1"""
    session = get_db_session()
    
    position = Position(symbol="000001.SZSE", quantity=100, cost_price=10.00)
    session.add(position)
    session.commit()
    
    # 验证 user_id 默认值为 1
    assert position.user_id == 1
    
    # 验证 NOT NULL 约束
    session.execute("INSERT INTO positions (symbol, quantity, cost_price, user_id) "
                   "VALUES ('TEST', 100, 10.00, NULL)")
    # 应该抛出 IntegrityError
```

---

## 5. 安全测试套件

### 5.1 SQL 注入测试

```python
@pytest.mark.parametrize("method,endpoint,payload,injection_type", [
    ("POST", "/api/positions", {"symbol": "'; DROP TABLE positions--", "quantity": 100}, "position"),
    ("POST", "/api/strategies", {"name": "test'; DELETE FROM users--", "initial_capital": 100000}, "strategy"),
    ("PUT", "/api/transactions/1", {"price": 10, "reason": "'; DROP TABLE transactions--"}, "transaction"),
])
def test_sql_injection_comprehensive(client, method, endpoint, payload, injection_type):
    """全面的 SQL 注入测试

    根据 HTTP 方法选择请求类型：
    - POST: 创建资源
    - PUT: 更新资源
    """
    # 根据method选择请求方式
    if method == "POST":
        response = client.post(endpoint, json=payload)
    elif method == "PUT":
        response = client.put(endpoint, json=payload)
    else:
        response = client.get(endpoint, query_string=payload)

    # 应该返回 400（错误请求）或数据被转义后返回200
    assert response.status_code in [200, 400, 422]

    # 验证数据库表仍然存在（未被注入攻击删除）
    session = get_db_session()
    tables = session.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = [t[0] for t in tables]
    assert 'positions' in table_names
    assert 'strategies' in table_names
    assert 'transactions' in table_names

    # 验证注入载荷没有被当作SQL执行
    # 如果payload被当作SQL执行，数据会被转义或拒绝
    if response.status_code == 200:
        data = response.get_json()
        # 如果创建/更新成功，验证数据被正确转义
        if injection_type == "position":
            assert data.get('symbol') == payload['symbol'] or ';' not in data.get('symbol', '')
```

**SQL注入载荷示例：**

| 载荷类型 | 示例 | 预期行为 |
|---------|------|---------|
| DROP TABLE | `'; DROP TABLE positions--` | 拒绝或转义 |
| DELETE FROM | `test'; DELETE FROM users--` | 拒绝或转义 |
| UNION SELECT | `' UNION SELECT * FROM users--` | 拒绝或转义 |
| OR 注入 | `' OR '1'='1` | 拒绝或转义 |
| 注释符 | `test'; --` | 拒绝或转义 |

### 5.2 XSS 测试套件

```javascript
const xssPayloads = [
  "<script>alert('XSS')</script>",
  "<img src=x onerror=alert('XSS')>",
  "javascript:alert('XSS')",
  "<iframe src='javascript:alert(XSS)'></iframe>",
  "><script>alert(String.fromCharCode(88,83,83))</script>",
  "<svg onload=alert('XSS')>",
  "'-alert('XSS')-'",
  "'-alert(1)-'"
];

xssPayloads.forEach((payload, index) => {
  test(`XSS Payload ${index + 1}: ${payload}`, async ({ page }) => {
    await page.goto('/dashboard');
    await page.click('#btn-create-position');
    
    // 输入 XSS 载荷
    await page.fill('#input-name', payload);
    await page.fill('#input-symbol', '000001.SZSE');
    await page.fill('#input-quantity', '1000');
    await page.fill('#input-cost-price', '10.00');
    await page.click('#btn-save-position');
    
    // 验证没有 alert 弹出
    const alerts = [];
    page.on('dialog', dialog => {
      alerts.push(dialog.message());
      dialog.accept();
    });
    
    await page.waitForTimeout(2000);
    expect(alerts.length).toBe(0);
  });
});
```

---

## 6. 性能测试套件

### 6.1 大数据量性能测试

```python
def test_large_dataset_performance(client):
    """大数据量性能测试"""
    session = get_db_session()
    
    # 创建1000条持仓
    for i in range(1000):
        position = Position(
            symbol=f'{i:06d}.SZSE',
            quantity=100 + i,
            cost_price=10.00,
            user_id=1
        )
        session.add(position)
    session.commit()
    
    # 测试查询性能
    import time
    start = time.time()
    response = client.get('/api/positions?page=1&per_page=20')
    end = time.time()
    
    assert response.status_code == 200
    duration = (end - start) * 1000
    assert duration < 500  # 500ms
    print(f"1000条持仓查询耗时: {duration}ms")

def test_transaction_large_dataset(client):
    """交易记录大数据量测试"""
    session = get_db_session()
    
    # 创建10万条交易记录（分批）
    batch_size = 1000
    for batch in range(100):
        for i in range(batch_size):
            transaction = Transaction(
                position_id=1,
                strategy_id=1,
                transaction_type="buy",
                symbol="000001.SZSE",
                quantity=100,
                price=10.00,
                amount=1000,
                user_id=1
            )
            session.add(transaction)
        session.commit()  # 分批提交
    
    # 测试分页查询性能
    start = time.time()
    response = client.get('/api/transactions?page=1&per_page=20')
    end = time.time()
    
    assert response.status_code == 200
    duration = (end - start) * 1000
    assert duration < 1000  # 1秒内
    print(f"10万条交易分页查询耗时: {duration}ms")

def test_recalc_performance_large_dataset(client):
    """重算性能测试：1000持仓 + 100,000交易"""
    session = get_db_session()

    # 创建策略
    strategy = Strategy(
        name="性能测试策略",
        initial_capital=10000000,
        recalc_status='dirty'
    )
    session.add(strategy)
    session.commit()
    strategy_id = strategy.id

    # 创建1000个持仓
    print("创建1000个持仓...")
    positions = []
    for i in range(1000):
        position = Position(
            symbol=f'{i:06d}.SZSE',
            strategy_id=strategy_id,
            quantity=1000 + i,
            cost_price=10.00 + (i % 100) * 0.1,
            current_price=12.00 + (i % 100) * 0.1
        )
        session.add(position)
        positions.append(position)

        # 每100个提交一次
        if (i + 1) % 100 == 0:
            session.commit()

    session.commit()

    # 为每个持仓创建100条交易（总共100,000条）
    print("创建100,000条交易记录...")
    batch_size = 1000
    for batch in range(100):
        for i in range(batch_size):
            position = positions[i % 1000]
            transaction = Transaction(
                position_id=position.id,
                strategy_id=strategy_id,
                transaction_type="buy" if i % 2 == 0 else "sell",
                symbol=position.symbol,
                quantity=100,
                price=10.00 + (batch % 10),
                amount=1000,
                user_id=1
            )
            session.add(transaction)
        session.commit()  # 分批提交

    # 执行重算并测量性能
    print("执行重算...")
    import time
    start = time.time()

    recalc_strategy(strategy_id, session)

    end = time.time()
    duration = (end - start)

    print(f"1000持仓 + 100,000交易重算耗时: {duration:.2f}秒")

    # 性能要求：重算时间 < 5秒
    assert duration < 5, f"重算时间{duration}秒超过5秒限制"

    # 验证重算完成
    strategy = session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == 'clean'
    assert strategy.recalc_retry_count == 0

    # 验证数据准确性（抽查）
    for i in [0, 100, 500, 999]:
        position = session.query(Position).get(positions[i].id)
        assert position.market_value > 0
        assert abs(position.profit_loss_pct) < 100  # 盈亏百分比应合理

    session.close()
    print(f"✅ 性能测试通过：{duration:.2f}秒 < 5秒")
```

---

## 7. 测试执行计划

---

## 7. 测试执行计划

### 7.1 每个 Task 完成后

```bash
# 1. 单元测试
pytest tests/unit/ -v

# 2. API 集成测试
pytest tests/api/ -v

# 3. 前端测试
pytest tests/frontend/ -v

# 4. 安全测试
pytest tests/security/ -v

# 5. 性能测试
pytest tests/performance/ -v

# 6. 回归测试
pytest tests/regression/ -v

# 7. 覆盖率报告
pytest --cov=web_app --cov-report=html
```

### 7.2 测试报告模板

```markdown
## Task X 测试报告

**测试时间：** 2026-04-20

**测试结果：** ✅ 通过

**测试统计：**
- 总测试用例：200+
- 通过：200+
- 失败：0
- 覆盖率：85%

**性能指标：**
- 持仓列表查询：250ms ✅ (< 500ms)
- 交易记录查询：800ms ✅ (< 1s)
- 页面加载：2.1s ✅ (< 3s)

**安全测试：**
- SQL 注入：通过 ✅
- XSS：通过 ✅

**回归测试：**
- 第一阶段功能：全部通过 ✅

**结论：**
[✅] 通过，可以合并
```

---

**文档状态：** 测试评审中
