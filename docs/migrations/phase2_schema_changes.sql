-- ========================================
-- Phase 2: 数据库Schema变更脚本
-- 功能: 添加状态管理字段、审计日志表和每日盈亏快照表
-- ========================================

-- ========================================
-- 1. positions 表新增字段
-- ========================================
ALTER TABLE positions ADD COLUMN prev_close_price NUMERIC(10, 2);
ALTER TABLE positions ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1;

-- ========================================
-- 2. strategies 表新增字段
-- ========================================
ALTER TABLE strategies ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1;
ALTER TABLE strategies ADD COLUMN recalc_status VARCHAR(20) NOT NULL DEFAULT 'clean';
ALTER TABLE strategies ADD COLUMN recalc_retry_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE strategies ADD COLUMN last_error TEXT;

-- ========================================
-- 3. transactions 表新增字段
-- ========================================
ALTER TABLE transactions ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1;

-- ========================================
-- 4. 审计日志表
-- ========================================
CREATE TABLE transaction_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER NOT NULL,
    field_name VARCHAR(50) NOT NULL,
    old_value TEXT,
    new_value TEXT NOT NULL,
    change_reason TEXT NOT NULL,
    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    changed_by INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
);

CREATE INDEX idx_audit_log_transaction ON transaction_audit_log(transaction_id);
CREATE INDEX idx_audit_log_changed_at ON transaction_audit_log(changed_at);

-- ========================================
-- 5. 策略审计日志表
-- ========================================
CREATE TABLE strategy_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL,
    field_name VARCHAR(50) NOT NULL,
    old_value TEXT,
    new_value TEXT NOT NULL,
    change_reason TEXT NOT NULL,
    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    changed_by INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);

CREATE INDEX idx_strategy_audit_strategy ON strategy_audit_log(strategy_id);
CREATE INDEX idx_strategy_audit_changed_at ON strategy_audit_log(changed_at);

-- ========================================
-- 6. 每日盈亏快照表
-- ========================================
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

CREATE INDEX idx_daily_pl_date ON daily_profit_loss(record_date);
CREATE INDEX idx_daily_pl_position ON daily_profit_loss(position_id);
