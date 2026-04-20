# 持仓管理系统设计文档

**项目:** vn.py 量化交易平台扩展
**功能模块:** 持仓管理系统
**设计日期:** 2026-04-14
**版本:** v1.0

## 1. 系统概述

### 1.1 项目背景
vn.py量化交易平台目前包含策略回测、智能选股和策略对比功能。为了完善平台的交易管理能力，需要开发持仓管理系统，支持用户管理实际持仓、分析策略效果、控制投资风险。

### 1.2 核心目标
- **持仓分析导向**: 重点关注当前持仓的市值变化、收益统计、风险指标
- **策略管理导向**: 按策略分组管理持仓，对比不同策略的表现
- **手动录入为主**: 主要通过Web界面手动管理持仓数据
- **数据库存储**: 使用SQLite/MySQL提供强大的查询能力
- **全面风险管理**: 包含预警、监控、分析等完整风控体系

### 1.3 系统定位
这是一个基于Web的持仓管理和策略分析系统，作为现有vn.py量化交易平台的功能扩展，服务于量化投资者的持仓管理、策略分析和决策支持需求。

## 2. 系统架构

### 2.1 技术架构
采用经典的三层架构设计：

**数据层**
- SQLite数据库存储核心数据
- SQLAlchemy ORM进行数据访问
- 数据备份和恢复机制

**业务层**
- Flask RESTful API提供数据服务
- 业务逻辑处理和数据计算
- 与现有回测、选股模块集成

**表现层**
- 响应式Web界面设计
- 仪表盘+分层导航模式
- 丰富的数据可视化图表

### 2.2 技术栈
- **后端**: Flask + SQLAlchemy + SQLite
- **前端**: JavaScript + Bootstrap + Chart.js
- **数据分析**: Pandas + NumPy
- **数据库**: SQLite (开发) / MySQL (生产)

## 3. 数据模型设计

### 3.1 数据库表结构

#### 3.1.1 持仓表 (positions)
```sql
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL,           -- 股票代码
    name VARCHAR(50),                      -- 股票名称
    quantity INTEGER NOT NULL,              -- 持仓数量
    cost_price DECIMAL(10,2) NOT NULL,     -- 成本价
    current_price DECIMAL(10,2),           -- 当前价
    market_value DECIMAL(15,2),            -- 市值
    profit_loss DECIMAL(15,2),             -- 盈亏金额
    profit_loss_pct DECIMAL(8,4),          -- 盈亏百分比
    strategy_id INTEGER,                    -- 关联策略ID
    buy_date DATE,                         -- 买入日期
    status VARCHAR(20) DEFAULT 'holding',   -- 状态: holding/sold
    stop_loss DECIMAL(10,2),               -- 止损价
    take_profit DECIMAL(10,2),             -- 止盈价
    notes TEXT,                             -- 备注
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);
```

#### 3.1.2 策略表 (strategies)
```sql
CREATE TABLE strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,             -- 策略名称
    description TEXT,                       -- 策略描述
    initial_capital DECIMAL(15,2) NOT NULL,-- 初始资金
    current_capital DECIMAL(15,2),         -- 当前资金
    total_return DECIMAL(8,4),             -- 总收益率
    max_drawdown DECIMAL(8,4),             -- 最大回撤
    sharpe_ratio DECIMAL(6,4),             -- 夏普比率
    risk_level VARCHAR(20),                -- 风险等级
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 3.1.3 交易记录表 (transactions)
```sql
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER,                   -- 关联持仓ID
    strategy_id INTEGER,                    -- 关联策略ID
    transaction_type VARCHAR(20) NOT NULL, -- 类型: buy/sell/dividend/bonus
    symbol VARCHAR(20) NOT NULL,           -- 股票代码
    quantity INTEGER NOT NULL,              -- 数量
    price DECIMAL(10,2) NOT NULL,           -- 价格
    amount DECIMAL(15,2) NOT NULL,         -- 金额
    fee DECIMAL(10,2),                     -- 手续费
    transaction_date DATE NOT NULL,         -- 交易日期
    notes TEXT,                             -- 备注
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (position_id) REFERENCES positions(id),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);
```

#### 3.1.4 风险指标表 (risk_metrics)
```sql
CREATE TABLE risk_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER,                   -- 关联持仓ID
    strategy_id INTEGER,                    -- 关联策略ID
    volatility DECIMAL(8,4),               -- 波动率
    var DECIMAL(10,2),                     -- 风险价值
    beta DECIMAL(6,4),                     -- 贝塔系数
    concentration DECIMAL(6,4),             -- 集中度
    risk_score DECIMAL(6,4),               -- 风险评分
    calculated_at TIMESTAMP,                -- 计算时间
    FOREIGN KEY (position_id) REFERENCES positions(id),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);
```

## 4. 用户界面设计

### 4.1 导航结构
在现有基础上增加第四个主导航项：
- **策略回测** | **智能选股** | **策略对比** | **持仓管理** → 新增

持仓管理的子导航：
- **持仓概览** - 仪表盘首页
- **策略分析** - 按策略管理持仓
- **交易记录** - 完整交易历史
- **风险分析** - 风险监控和预警

### 4.2 仪表盘布局

**顶部区域 - 关键指标卡片**
```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│ 总资产      │ 总盈亏      │ 今日盈亏    │ 持仓数量    │
│ ¥1,234,567  │ +¥123,456   │ +¥12,345    │ 15只       │
│             │             │             │             │
└─────────────┴─────────────┴─────────────┴─────────────┘
```

**中部区域 - 可视化图表**
- 左侧：持仓分布饼图
- 中间：净值收益曲线
- 右侧：策略对比柱状图

**底部区域 - 持仓明细表格**
- 支持排序、筛选、搜索
- 实时显示盈亏状态
- 快速操作按钮

### 4.3 核心页面设计

#### 4.3.1 持仓概览页面
- 投资组合总览仪表盘
- 关键指标实时更新
- 持仓分布可视化
- 收益趋势分析

#### 4.3.2 策略分析页面
- 策略列表卡片展示
- 单个策略详细分析
- 策略对比功能
- 策略表现排名

#### 4.3.3 交易记录页面
- 完整交易历史表格
- 支持筛选和搜索
- 交易详情查看
- 批量导入功能

#### 4.3.4 风险分析页面
- 风险指标仪表盘
- 预警通知中心
- 风险分析报告
- 处理建议推荐

## 5. 核心业务功能

### 5.1 持仓管理功能

#### 5.1.1 新增持仓
- 表单录入：股票代码、数量、买入价、策略选择
- 自动获取：股票名称、实时价格
- 风险设置：止损价、止盈价
- 数据验证：格式检查、逻辑验证

#### 5.1.2 修改持仓
- 数量调整：加仓、减仓操作
- 成本修正：分红、配股后成本调整
- 风险调整：修改止损止盈价格
- 策略变更：更换持仓所属策略

#### 5.1.3 平仓处理
- 卖出记录：记录卖出价格、数量、手续费
- 盈亏计算：自动计算实际盈亏和收益率
- 状态更新：将持仓状态改为"已卖出"
- 数据归档：移入历史持仓记录

### 5.2 策略管理功能

#### 5.2.1 策略创建
- 基础信息：策略名称、描述、初始资金
- 风险设置：风险等级、仓位上限
- 策略类型：选择策略类型（回测/选股/自定义）

#### 5.2.2 策略分析
- 收益分析：总收益、年化收益、累计收益曲线
- 风险分析：最大回撤、波动率、夏普比率
- 持仓分析：策略内持仓分布、个股贡献度
- 表现评估：策略排名、优劣势分析

#### 5.2.3 策略对比
- 多维度对比：收益、风险、效率指标
- 可视化对比：雷达图、柱状图、曲线图
- 时间维度：不同时间段的表现对比
- 最佳策略：自动识别表现最好的策略

### 5.3 风险管理功能

#### 5.3.1 风险监控
- 实时监控：持仓市值、盈亏状态、风险指标
- 阈值预警：价格突破止损止盈、风险超标
- 集中度监控：单一持仓占比、行业集中度
- 杠杆监控：总仓位、资金使用率

#### 5.3.2 风险评估
- 风险评分：综合评估持仓组合风险等级
- VaR计算：计算在险价值和最大可能损失
- 压力测试：模拟极端市场情况下的表现
- 风险报告：生成详细的风险分析报告

## 6. API接口设计

### 6.1 持仓管理接口
```
GET    /api/positions              - 获取持仓列表
POST   /api/positions              - 新增持仓
PUT    /api/positions/<id>         - 修改持仓
DELETE /api/positions/<id>         - 删除持仓
GET    /api/positions/<id>         - 获取持仓详情
```

### 6.2 策略管理接口
```
GET    /api/strategies            - 获取策略列表
POST   /api/strategies            - 创建策略
PUT    /api/strategies/<id>        - 更新策略
DELETE /api/strategies/<id>        - 删除策略
GET    /api/strategies/<id>/positions - 获取策略持仓
```

### 6.3 交易记录接口
```
GET    /api/transactions          - 获取交易记录
POST   /api/transactions          - 记录新交易
GET    /api/transactions/position/<id> - 获取持仓交易历史
PUT    /api/transactions/<id>     - 修改交易记录
```

### 6.4 数据分析接口
```
GET    /api/analytics/portfolio   - 投资组合分析
GET    /api/analytics/strategy/<id> - 策略分析
GET    /api/analytics/risk/metrics - 风险指标
GET    /api/analytics/comparison    - 策略对比分析
```

### 6.5 系统管理接口
```
GET    /api/system/health          - 系统健康检查
POST   /api/system/backup          - 数据备份
POST   /api/system/import          - 数据导入
GET    /api/system/export          - 数据导出
```

## 7. 技术实现要点

### 7.1 后端实现
- **Flask路由**: 使用Blueprint模块化组织API
- **SQLAlchemy ORM**: 数据库操作和关系管理
- **数据验证**: 使用Marshmallow进行数据验证和序列化
- **错误处理**: 统一的异常处理和错误响应
- **性能优化**: 数据库索引、查询优化、缓存策略

### 7.2 前端实现
- **组件化设计**: 可复用的UI组件
- **状态管理**: 使用Vuex/Redux管理应用状态
- **图表集成**: Chart.js/ECharts实现数据可视化
- **响应式布局**: Bootstrap框架支持多设备访问
- **用户体验**: AJAX无刷新更新、loading动画、友好提示

### 7.3 数据处理
- **实时数据**: 定时更新股票价格和持仓数据
- **计算逻辑**: 盈亏计算、风险指标计算、统计分析
- **数据同步**: 确保前后端数据一致性
- **历史数据**: 支持历史数据查询和趋势分析

## 8. 实施路线图

### 8.1 第一阶段：核心功能（MVP）- 2-3周
**目标**: 实现基础持仓管理

**主要任务**:
1. 设计并创建数据库表结构
2. 实现持仓CRUD操作
3. 创建基础仪表盘界面
4. 实现简单持仓列表和详情
5. 基础分析和统计功能

**验收标准**:
- 能够新增、修改、删除持仓
- 显示基本的资产和盈亏指标
- 简单的持仓列表展示

### 8.2 第二阶段：策略与分析 - 2-3周
**目标**: 完善策略管理和数据分析

**主要任务**:
1. 实现策略创建和管理
2. 持仓与策略关联
3. 增强数据可视化
4. 交易记录管理
5. 基础风险指标计算

**验收标准**:
- 支持5+个策略同时管理
- 完整的交易历史追踪
- 策略对比分析功能

### 8.3 第三阶段：高级功能 - 2-3周
**目标**: 完整的分析决策支持

**主要任务**:
1. 综合策略对比分析
2. 高级风险管理
3. 数据导入导出
4. 性能优化
5. 深度系统集成

**验收标准**:
- 完整的风险预警系统
- 支持数据导入导出
- 系统性能满足要求

## 9. 成功标准

### 9.1 功能标准
- 支持100+个持仓记录管理
- 支持5+个策略同时分析
- 风险预警准确率>90%
- 数据分析响应时间<2秒

### 9.2 性能标准
- 页面加载时间<3秒
- API响应时间<1秒
- 支持10+并发用户
- 数据库查询优化

### 9.3 用户体验标准
- 界面直观易用，学习成本低
- 操作流程顺畅，反馈及时
- 错误提示友好，指导清晰
- 移动端适配良好

## 10. 风险与挑战

### 10.1 技术风险
- **数据一致性**: 多表关联操作的并发控制
- **性能瓶颈**: 大量数据的计算和展示性能
- **系统集成**: 与现有模块的兼容性

### 10.2 业务风险
- **数据准确性**: 计算结果的准确性和可靠性
- **用户接受度**: 新功能的学习成本和使用习惯
- **需求变更**: 功能需求的不断演进和调整

### 10.3 应对措施
- 充分的前期调研和需求分析
- 迭代开发，小步快跑
- 完善的测试覆盖
- 用户反馈收集和持续改进

---

**文档状态**: 设计完成，等待实施
**下一步**: 准备开发环境和创建实施计划
