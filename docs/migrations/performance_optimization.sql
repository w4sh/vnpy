-- ========================================
-- 性能优化：添加数据库索引
-- ========================================
--
-- 为常用查询字段添加索引，提升查询性能
-- 基于实际API查询模式分析
--

-- 1. positions表索引
-- ----------------------

-- 按策略查询持仓（position_api.get_strategies, strategy_api.get_strategy_positions）
CREATE INDEX IF NOT EXISTS idx_positions_strategy_id
ON positions(strategy_id);

-- 按状态筛选持仓（大部分API只查询holding状态）
CREATE INDEX IF NOT EXISTS idx_positions_status
ON positions(status);

-- 组合索引：策略+状态（最常见的查询模式）
CREATE INDEX IF NOT EXISTS idx_positions_strategy_status
ON positions(strategy_id, status);

-- 按股票代码查询
CREATE INDEX IF NOT EXISTS idx_positions_symbol
ON positions(symbol);

-- 2. transactions表索引
-- ----------------------

-- 按策略查询交易记录
CREATE INDEX IF NOT EXISTS idx_transactions_strategy_id
ON transactions(strategy_id);

-- 按持仓查询交易记录
CREATE INDEX IF NOT EXISTS idx_transactions_position_id
ON transactions(position_id);

-- 按交易类型查询
CREATE INDEX IF NOT EXISTS idx_transactions_type
ON transactions(transaction_type);

-- 按日期范围查询（常用于分析）
CREATE INDEX IF NOT EXISTS idx_transactions_date
ON transactions(transaction_date);

-- 3. strategy_audit_log表索引
-- ----------------------

-- 按策略查询审计日志
CREATE INDEX IF NOT EXISTS idx_strategy_audit_log_strategy_id
ON strategy_audit_log(strategy_id);

-- 按时间倒序查询审计日志
CREATE INDEX IF NOT EXISTS idx_strategy_audit_log_changed_at
ON strategy_audit_log(changed_at DESC);

-- 4. transaction_audit_log表索引
-- ----------------------

-- 按交易查询审计日志
CREATE INDEX IF NOT EXISTS idx_transaction_audit_log_transaction_id
ON transaction_audit_log(transaction_id);

-- 按时间倒序查询审计日志
CREATE INDEX IF NOT EXISTS idx_transaction_audit_log_changed_at
ON transaction_audit_log(changed_at DESC);

-- 验证索引创建
-- ----------------------
SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%';
