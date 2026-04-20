-- ========================================
-- Phase 2 Schema Rollback Script
-- 回滚Phase 2的所有数据库变更
-- ========================================
--
-- 重要: 执行此脚本前请备份数据库!
-- sqlite3 position_management.db .backup backup_$(date +%Y%m%d).db
--
-- 此脚本将删除以下内容:
-- 1. daily_profit_loss表
-- 2. strategy_audit_log表
-- 3. transaction_audit_log表
-- 4. strategies表的新增字段
-- 5. transactions表的新增字段
-- 6. positions表的新增字段
--
-- 警告: 删除表和字段将导致数据永久丢失,请谨慎操作!
-- ========================================

-- ========================================
-- 1. 删除每日盈亏快照表
-- ========================================
DROP INDEX IF EXISTS idx_daily_pl_position;
DROP INDEX IF EXISTS idx_daily_pl_date;
DROP TABLE IF EXISTS daily_profit_loss;

-- ========================================
-- 2. 删除策略审计日志表
-- ========================================
DROP INDEX IF EXISTS idx_strategy_audit_changed_at;
DROP INDEX IF EXISTS idx_strategy_audit_strategy;
DROP TABLE IF EXISTS strategy_audit_log;

-- ========================================
-- 3. 删除交易审计日志表
-- ========================================
DROP INDEX IF EXISTS idx_audit_log_changed_at;
DROP INDEX IF EXISTS idx_audit_log_transaction;
DROP TABLE IF EXISTS transaction_audit_log;

-- ========================================
-- 4. 删除strategies表新增字段
-- ========================================
-- SQLite不支持直接删除列,需要重建表
CREATE TABLE strategies_backup (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    initial_capital NUMERIC(15, 2) NOT NULL,
    current_capital NUMERIC(15, 2),
    total_return NUMERIC(8, 4),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO strategies_backup
SELECT id, name, initial_capital, current_capital, total_return, created_at, updated_at
FROM strategies;

DROP TABLE strategies;
ALTER TABLE strategies_backup RENAME TO strategies;

-- ========================================
-- 5. 删除transactions表新增字段
-- ========================================
-- SQLite不支持直接删除列,需要重建表
CREATE TABLE transactions_backup (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL,
    strategy_id INTEGER NOT NULL,
    transaction_type VARCHAR(10) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    quantity INTEGER NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    amount NUMERIC(15, 2) NOT NULL,
    fee NUMERIC(10, 2) DEFAULT 0,
    transaction_date DATE NOT NULL,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (position_id) REFERENCES positions(id),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);

INSERT INTO transactions_backup
SELECT id, position_id, strategy_id, transaction_type, symbol, quantity, price, amount, fee, transaction_date, notes, created_at
FROM transactions;

DROP TABLE transactions;
ALTER TABLE transactions_backup RENAME TO transactions;

-- ========================================
-- 6. 删除positions表新增字段
-- ========================================
-- SQLite不支持直接删除列,需要重建表
CREATE TABLE positions_backup (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(50),
    quantity INTEGER NOT NULL,
    cost_price NUMERIC(10, 2) NOT NULL,
    current_price NUMERIC(10, 2),
    market_value NUMERIC(15, 2),
    profit_loss NUMERIC(15, 2),
    profit_loss_pct NUMERIC(8, 4),
    strategy_id INTEGER,
    buy_date DATE,
    status VARCHAR(20) DEFAULT 'holding',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);

INSERT INTO positions_backup
SELECT id, symbol, name, quantity, cost_price, current_price, market_value, profit_loss, profit_loss_pct, strategy_id, buy_date, status, created_at, updated_at
FROM positions;

DROP TABLE positions;
ALTER TABLE positions_backup RENAME TO positions;

-- ========================================
-- 回滚完成
-- ========================================
-- 验证表结构
.schema strategies
.schema transactions
.schema positions
