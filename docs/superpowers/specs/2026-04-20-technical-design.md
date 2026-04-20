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
ALTER TABLE strategies ADD COLUMN is_dirty BOOLEAN DEFAULT 0;
```

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

**策略 dirty 状态：**

```python
# 交易修改时标记 dirty
def update_transaction(transaction_id, data):
    # 更新交易
    # 标记策略为 dirty
    mark_strategy_dirty(strategy_id)
    # 返回响应
```

**后台重算任务：**

```python
@scheduler.scheduled_job('interval', minutes=5)
def recalc_dirty_strategies():
    """每5分钟重算 dirty 策略"""
    dirty_strategies = session.query(Strategy)\
        .filter_by(is_dirty=True)\
        .all()
    
    for strategy in dirty_strategies:
        recalc_strategy(strategy.id)
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
