# 持仓管理系统第二阶段 - 技术设计文档

**项目:** vn.py 量化交易平台
**文档类型:** 技术设计说明书
**设计日期:** 2026-04-20
**版本:** 1.0

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

### 3.1 新增字段

positions 表新增 prev_close_price 字段

### 3.2 审计日志表

- transaction_audit_log
- strategy_audit_log

### 3.3 每日快照表

- daily_profit_loss
- daily_portfolio_summary

### 3.4 图表配置表

- chart_configs
- chart_templates

---

## 4. 安全防护

### 4.1 SQL 注入防护

使用参数化查询

### 4.2 XSS 防护

输入转义和验证

---

## 5. 性能优化

### 5.1 数据库优化

- 索引优化
- 查询优化
- 分页查询

### 5.2 缓存机制

- LRU 缓存
- 5分钟过期

---

**文档状态：** 技术评审中
