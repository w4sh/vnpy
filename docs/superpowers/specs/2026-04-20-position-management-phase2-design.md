# 持仓管理系统 - 第二阶段功能设计文档

**项目:** vn.py 量化交易平台 - 持仓管理系统
**设计日期:** 2026-04-20
**版本:** v2.0
**状态:** 设计阶段

---

## 1. 项目概述

### 1.1 背景
持仓管理系统第一阶段已实现基础的数据模型、核心 API 和部分前端界面。第二阶段将重点完善：
1. **API 端点补充**：策略更新/删除、交易记录修改
2. **持仓概览页面增强**：顶部指标卡片、可视化图表
3. **图表配置系统**：用户可自定义仪表盘

### 1.2 核心目标
- 完善所有 CRUD API 端点，提供完整的数据管理能力
- 实现专业的持仓概览仪表盘，支持数据可视化
- 构建可扩展的图表配置系统，支持用户自定义
- 确保系统安全性、性能和可维护性

---

## 2. API 端点设计

### 2.1 策略管理 API

#### 2.1.1 更新策略
**端点：** \`PUT /api/strategies/<id>\`

**请求体：**
\`\`\`json
{
  "description": "更新后的策略描述（可选）",
  "risk_level": "低（可选）"
}
\`\`\`

**不可修改字段：**
- name: 策略名称
- initial_capital: 初始资金
- total_return, max_drawdown, sharpe_ratio: 性能指标

#### 2.1.2 删除策略（软删除）
**端点：** \`DELETE /api/strategies/<id>\`

将 status 设为 'deleted'，记录审计日志

---

### 2.2 交易记录管理 API

#### 2.2.1 修改交易记录
**端点：** \`PUT /api/transactions/<id>\`

**请求体：**
\`\`\`json
{
  "price": 38.50,
  "quantity": 1000,
  "fee": 5.0,
  "reason": "价格录入错误（必填）"
}
\`\`\`

---

### 2.3 持仓概览 API

#### 2.3.1 仪表盘关键指标
**端点：** \`GET /api/analytics/dashboard/summary\`

返回 4 个关键指标卡片数据

#### 2.3.2 今日盈亏明细
**端点：** \`GET /api/analytics/dashboard/today-breakdown\`

---

## 3. 数据库设计

### 3.1 新增字段

\`\`\`sql
-- positions 表新增
ALTER TABLE positions ADD COLUMN prev_close_price NUMERIC(10, 2);
\`\`\`

### 3.2 审计日志表

\`\`\`sql
CREATE TABLE transaction_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER NOT NULL,
    field_name VARCHAR(50),
    old_value TEXT,
    new_value TEXT,
    change_reason TEXT NOT NULL,
    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
);
\`\`\`

### 3.3 每日盈亏快照表

\`\`\`sql
CREATE TABLE daily_profit_loss (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_date DATE NOT NULL,
    position_id INTEGER NOT NULL,
    symbol VARCHAR(20),
    prev_close_price NUMERIC(10, 2),
    current_price NUMERIC(10, 2),
    daily_profit_loss NUMERIC(15, 2),
    FOREIGN KEY (position_id) REFERENCES positions(id),
    UNIQUE(record_date, position_id)
);
\`\`\`

---

## 4. 前端设计

### 4.1 页面布局

\`\`\`
┌─────────────────────────────────────────┐
│  [导航] 策略回测 | 智能选股 | 策略对比 | 持仓管理 │
├─────────────────────────────────────────┤
│  [子导航] 持仓概览 | 策略分析 | 交易记录 | 风险分析 │
├─────────────────────────────────────────┤
│  ┌───────┬───────┬───────┬───────┐    │
│  │总资产 │总盈亏 │今日盈亏│持仓数量│    │
│  └───────┴───────┴───────┴───────┘    │
│                                         │
│  ┌─────────┬─────────┬─────────┐      │
│  │持仓分布 │净值曲线 │策略对比 │      │
│  └─────────┴─────────┴─────────┘      │
│                                         │
│  [▼ 高级分析面板 - 可折叠]             │
│  ┌─────────┬─────────┬─────────┐      │
│  │盈亏瀑布 │集中度  │行业分布 │      │
│  └─────────┴─────────┴─────────┘      │
└─────────────────────────────────────────┘
\`\`\`

### 4.2 顶部指标卡片

- **总资产**：当前总市值
- **总盈亏**：累计盈亏金额和百分比
- **今日盈亏**：当日盈亏（基于昨收价）
- **持仓数量**：总持仓数、盈利数、亏损数

---

## 5. 测试策略

### 5.1 后端测试

**功能测试：**
- 正常请求（200 OK）
- 参数验证（400）
- 数据不存在（404）
- 并发请求

**边界值测试：**
- 数量：1（成功）、0（失败）、负数（失败）
- 价格：0.01（成功）、0.00（失败）
- 长度：最大值、超长值

**SQL 注入测试：**
\`\`\`python
sql_injection_attempts = [
    "000001.SZSE' OR '1'='1",
    "000001.SZSE'; DROP TABLE positions; --",
    "1 OR 1=1"
]
\`\`\`

**XSS 测试：**
\`\`\`javascript
xss_attempts = [
  "<script>alert('XSS')</script>",
  "<img src=x onerror=alert('XSS')>"
]
\`\`\`

### 5.2 前端测试

**功能测试：**
- 页面加载
- 图表渲染
- 搜索筛选
- 表单验证

**边界值测试：**
- 表单输入边界值
- 字符长度限制

**注入测试：**
- XSS 注入
- 搜索注入

### 5.3 回归测试

确保原有功能不受影响：
- 持仓 CRUD
- 策略 CRUD
- 分析 API
- 行情 API

---

## 6. 成功标准

- ✅ 所有 API 端点正常工作
- ✅ 前端页面完整可用
- ✅ 测试覆盖率 > 80%
- ✅ API 响应 < 1 秒
- ✅ 页面加载 < 3 秒
- ✅ 无安全漏洞

---

**文档状态：** 设计完成，等待审核
**下一步：** 编写实施计划，拆解 Task
