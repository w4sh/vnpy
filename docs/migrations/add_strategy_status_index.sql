-- ========================================
-- 为strategies.status字段添加索引
-- ========================================
--
-- 提升查询性能，特别是在过滤已删除策略时
--

CREATE INDEX idx_strategies_status ON strategies(status);

-- 验证
.index strategies idx_strategies_status
