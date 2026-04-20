# 持仓管理系统第二阶段 - 技术设计文档

**项目:** vn.py 量化交易平台
**文档类型:** 技术设计说明书
**设计日期:** 2026-04-20
**版本:** 1.1

---

## 1. 系统架构

### 1.1 整体架构

三层架构：表现层 → 业务层 → 数据层

### 1.2 技术栈

- 后端：Flask + SQLAlchemy + SQLite
- 前端：HTML5 + Bootstrap 5 + Chart.js
- 测试：pytest + Playwright

---

## 2. API 设计

### 2.1 策略管理 API

- PUT /api/strategies/<id> - 更新策略
- DELETE /api/strategies/<id> - 软删除策略
- GET /api/strategies/<id> - 获取详情
- GET /api/strategies/<id>/positions - 获取持仓列表

### 2.2 交易记录 API

- PUT /api/transactions/<id> - 修改交易
- GET /api/transactions/<id>/audit - 审计日志

### 2.3 仪表盘 API

- GET /api/analytics/dashboard/summary - 关键指标
- GET /api/analytics/dashboard/today-breakdown - 今日盈亏明细

---

## 3. 数据库设计

### 3.1 表结构变更

**positions 表新增字段：**

```sql
ALTER TABLE positions ADD COLUMN prev_close_price NUMERIC(10, 2);
ALTER TABLE positions ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1;
```

**strategies 表新增字段：**

```sql
ALTER TABLE strategies ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1;
ALTER TABLE strategies ADD COLUMN recalc_status VARCHAR(20) NOT NULL DEFAULT 'clean';
ALTER TABLE strategies ADD COLUMN recalc_retry_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE strategies ADD COLUMN last_error TEXT;
```

**recalc_status 字段规范：**
- 字段类型：VARCHAR(20) NOT NULL
- 默认值：'clean'
- 允许值：'clean', 'dirty', 'recomputing', 'failed'（应用层约束）
- 替代原 is_dirty 字段，统一状态管理
- recalc_retry_count：重试次数计数器
- last_error：最后一次失败原因

**transactions 表新增字段：**

```sql
ALTER TABLE transactions ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1;
```

**user_id 字段规范：**
- 字段类型：INTEGER NOT NULL
- 默认值：1（当前用户）
- 不允许为 NULL
- 为未来多用户扩展预留

### 3.2 审计日志表

transaction_audit_log, strategy_audit_log

### 3.3 每日盈亏快照表

daily_profit_loss, daily_portfolio_summary

### 3.4 图表配置表

chart_configs, chart_templates

---

## 4. 数据一致性模型

### 4.1 冗余存储 + 衍生更新

**原则：**
- 持仓数据、策略指标采用冗余存储
- 不采用纯实时计算
- 数据变更触发重算流程

**重算范围：**
- 默认：仅影响对应的 strategy_id
- 包括：持仓数量、市值、总资产、盈亏、净值曲线

**重算触发时机：**
- 交易记录创建/修改/删除
- 持仓创建/修改/删除
- 价格更新（手动触发）

### 4.2 Dirty 状态机制

**状态生命周期（单状态机）：**

```
clean（数据一致）
  ↓ 数据变更
dirty（数据已变更，等待重算）
  ↓ 重算任务触发
recomputing（正在重算）
  ↓ 重算成功/失败
clean / failed
```

**状态定义：**
- `clean`：数据一致，衍生数据准确
- `dirty`：数据已变更，衍生数据可能过期，等待重算
- `recomputing`：正在执行重算任务
- `failed`：重算失败（连续失败3次），需要人工介入或等待自动重试

**状态字段设计：**
- 使用 `recalc_status` 作为唯一状态字段（枚举：clean/dirty/recomputing/failed）
- 删除或废弃 `is_dirty` 字段，避免状态不一致
- 所有状态判断基于 `recalc_status` 字段

**标记 dirty 状态：**

```python
def mark_strategy_dirty(strategy_id, session):
    """标记策略为 dirty 状态

    必须在调用方的事务中执行，不在此函数内 commit
    """
    strategy = session.query(Strategy).get(strategy_id)
    if strategy and strategy.recalc_status == 'clean':
        strategy.recalc_status = 'dirty'
        strategy.recalc_retry_count = 0
        strategy.last_error = None
        # 不在此 commit，由调用方统一提交
```

**后台重算任务（使用乐观锁）：**

```python
@scheduler.scheduled_job('interval', minutes=5)
def recalc_dirty_strategies():
    """每5分钟重算 dirty 策略"""
    session = get_db_session()

    try:
        # 使用乐观锁获取待重算策略
        dirty_strategies = session.query(Strategy)\
            .filter_by(recalc_status='dirty')\
            .all()

        for strategy in dirty_strategies:
            # 尝试获取执行权（条件更新）
            rows_affected = session.query(Strategy)\
                .filter_by(id=strategy.id, recalc_status='dirty')\
                .update({'recalc_status': 'recomputing'}, synchronize_session=False)

            if rows_affected == 0:
                # 已被其他 worker 抢占，跳过
                continue

            session.commit()

            try:
                # 执行重算（传入同一 session）
                recalc_strategy(strategy.id, session)
            except Exception as e:
                handle_recalc_failure(strategy.id, str(e), session)
    finally:
        session.close()
```

**重算函数实现（单一事务）：**

```python
def recalc_strategy(strategy_id, session):
    """重算策略的所有衍生数据

    关键约束：
    1. 整个重算过程必须在单一事务中完成
    2. 所有数据库操作使用传入的 session，禁止函数内部创建新 session
    3. 保证原子性：要么全部成功，要么全部回滚

    采用全量重算策略，避免累计误差
    """
    try:
        # 获取策略对象（已在事务中）
        strategy = session.query(Strategy).get(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        # 获取所有持仓（在同一事务中）
        positions = session.query(Position)\
            .filter_by(strategy_id=strategy_id, status='holding')\
            .all()

        # 为每个持仓重新计算成本和数量（不单独 commit）
        for position in positions:
            _recalc_position_cost(position, session)

        # 更新策略指标
        total_market_value = sum(p.market_value for p in positions)
        strategy.current_capital = total_market_value
        strategy.total_return = (strategy.current_capital - strategy.initial_capital) / strategy.initial_capital

        # 所有计算成功后，统一更新状态
        strategy.recalc_status = 'clean'
        strategy.recalc_retry_count = 0
        strategy.last_error = None

        # 单一事务提交点
        session.commit()

    except Exception as e:
        # 任何失败都回滚整个事务
        session.rollback()
        raise

def _recalc_position_cost(position, session):
    """重算持仓的成本和数量（加权平均成本法）

    私有函数，不对外暴露
    必须在调用方的事务中执行，不在此函数内 commit

    Args:
        position: 持仓对象（已在 session 中）
        session: 数据库会话（与调用方同一事务）
    """
    # 获取所有相关交易（按时间顺序）
    transactions = session.query(Transaction)\
        .filter_by(position_id=position.id)\
        .order_by(Transaction.transaction_date)\
        .all()

    total_qty = 0
    total_cost = 0.0

    for txn in transactions:
        if txn.transaction_type == 'buy':
            # 买入：加权平均成本
            # 新成本 = (原成本 × 原数量 + 新金额) / (原数量 + 新数量)
            amount = txn.quantity * txn.price + txn.fee
            new_qty = total_qty + txn.quantity
            new_cost = (total_cost * total_qty + amount) / new_qty if new_qty > 0 else 0

            total_qty = new_qty
            total_cost = new_cost

        elif txn.transaction_type == 'sell':
            # 卖出：成本不变，实现盈亏
            # 已实现盈亏 = (卖出价 - 成本价) × 卖出数量
            sell_amount = txn.quantity * txn.price - txn.fee
            cost_basis = total_cost * txn.quantity
            realized_profit = sell_amount - cost_basis

            total_qty -= txn.quantity
            # 成本保持不变

    # 更新持仓（不单独 commit）
    position.quantity = total_qty
    position.cost_price = total_cost
    position.market_value = position.current_price * total_qty
    position.profit_loss = position.market_value - (total_cost * total_qty)
    position.profit_loss_pct = (position.profit_loss / (total_cost * total_qty)) * 100 if total_qty > 0 else 0

    # 注意：不在此 commit，由外层 recalc_strategy 统一提交

def handle_recalc_failure(strategy_id, error_msg, session):
    """处理重算失败

    根据重试次数决定状态：
    - 重试次数 < 3：状态保持 dirty，允许后台任务继续重试
    - 重试次数 >= 3：状态改为 failed，停止自动重试

    必须在调用方的事务中执行
    """
    strategy = session.query(Strategy).get(strategy_id)

    if strategy.recalc_retry_count >= 3:
        # 已达到最大重试次数，标记为 failed
        strategy.recalc_status = 'failed'
        strategy.last_error = f"Max retries exceeded: {error_msg}"
    else:
        # 保持 dirty 状态，等待下次重试
        strategy.recalc_status = 'dirty'
        strategy.last_error = error_msg

    session.commit()
```

**查询 API 状态处理：**

```python
@app.route('/api/strategies/<int:strategy_id>')
def get_strategy(strategy_id):
    """获取策略详情，包含重算状态"""
    strategy = session.query(Strategy).get(strategy_id)

    result = {
        'id': strategy.id,
        'name': strategy.name,
        'current_capital': strategy.current_capital,
        'recalc_status': strategy.recalc_status,  # 关键：返回状态
        'last_error': strategy.last_error
    }

    # 前端根据 recalc_status 显示提示
    return jsonify(result)
```

**前端状态提示：**

```javascript
// 根据 recalc_status 显示提示
if (data.recalc_status === 'dirty' || data.recalc_status === 'recomputing') {
    showNotification('数据更新中，当前显示可能为旧值', 'info');
} else if (data.recalc_status === 'failed') {
    showNotification(`数据更新失败：${data.last_error}`, 'error');
}
```

---

## 5. 图表配置 Schema

### 5.1 统一数据结构

```json
{
  "version": "1.0",
  "cards": ["total_assets", "total_profit_loss", "today_profit_loss", "position_count"],
  "layout": {
    "top_cards": ["total_assets", "total_profit_loss", "today_profit_loss", "position_count"],
    "core_charts": ["position_distribution", "nav_curve", "strategy_comparison"],
    "advanced_charts": ["profit_waterfall", "concentration_curve", "industry_distribution"],
    "advanced_collapsed": false
  },
  "charts": [
    {
      "id": "position_distribution",
      "type": "pie",
      "metric": "distribution",
      "title": "持仓分布",
      "enabled": true,
      "options": {...}
    },
    {
      "id": "nav_curve",
      "type": "line",
      "metric": "nav",
      "title": "净值收益曲线",
      "enabled": true,
      "options": {
        "range": "30d",
        "showBaseline": true,
        "zoomable": true
      }
    }
  ]
}
```

**Schema 要求：**
- version 字段用于向后兼容检测
- 前后端严格遵循同一 schema
- 所有配置变更需保证向后兼容

### 5.2 Schema 验证

```python
# schemas/chart_config.py
def validate_chart_config(config_json):
    """验证图表配置"""
    try:
        config = json.loads(config_json)
        
        # 验证必需字段
        required_fields = ['version', 'cards', 'charts']
        for field in required_fields:
            if field not in config:
                return False, f"缺少必需字段: {field}"
        
        # 验证版本
        if config['version'] not in ['1.0', '1.1']:
            return False, f"不支持的配置版本: {config['version']}"
        
        return True, ""
    except Exception as e:
        return False, f"配置格式错误: {str(e)}"
```

---

## 6. 分页支持

### 6.1 分页实现

**所有列表 API 必须支持分页：**

```python
def paginate_query(query, page=1, per_page=20):
    """分页查询"""
    total = query.count()
    
    # 限制每页最大数量
    per_page = min(per_page, 100)
    
    items = query.limit(per_page).offset((page - 1) * per_page).all()
    
    return {
        'data': items,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page,
            'has_prev': page > 1,
            'has_next': page * per_page < total
        }
    }
```

### 6.2 API 端点示例

**获取持仓列表（带分页）：**

```
GET /api/positions?page=1&per_page=20

响应：
{
  "data": [...],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 150,
    "pages": 8,
    "has_prev": false,
    "has_next": true
  }
}
```

---

## 7. 性能优化

### 7.1 索引优化

```sql
-- 复合索引
CREATE INDEX idx_positions_strategy_status ON positions(strategy_id, status);
CREATE INDEX idx_transactions_date_type ON transactions(transaction_date, transaction_type);
CREATE INDEX idx_daily_pl_date_position ON daily_profit_loss(record_date, position_id);
```

### 7.2 查询优化

**批量加载：**

```python
# 避免 N+1 查询
strategies = session.query(Strategy)\
    .options(joinedload(Strategy.positions))\
    .all()
```

**分页查询：**

```python
# 大数据量分页
positions = session.query(Position)\
    .filter_by(status='holding')\
    .order_by(Position.market_value.desc())\
    .limit(20)\
    .offset((page - 1) * 20)\
    .all()
```

### 7.3 性能指标

**基于数据规模：1000 持仓、100,000 交易**

| 操作 | 预期性能 |
|------|----------|
| 持仓列表查询（分页） | < 500ms |
| 交易记录查询（分页） | < 1s |
| 仪表盘指标计算 | < 1s |
| 历史净值曲线查询 | < 2s |
| 策略重算 | < 5s |

---

## 8. 安全防护

### 8.1 SQL 注入防护

使用参数化查询

### 8.2 XSS 防护

输入转义和验证

---

**文档状态：** 技术评审中
