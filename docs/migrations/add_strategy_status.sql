-- ========================================
-- 添加Strategy.status字段支持软删除
-- ========================================
--
-- 为strategies表添加status字段,实现软删除功能
-- 状态值: 'active' (活跃), 'deleted' (已删除)
-- 默认值: 'active'
--

-- 添加status字段(自动应用DEFAULT值到现有行)
ALTER TABLE strategies ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active';

-- 验证
SELECT id, name, status FROM strategies LIMIT 5;

