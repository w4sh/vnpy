# Scheme C 策略优化实施方案 — 2026-05-07

## 概述

基于策略评估报告，将候选股推荐系统从短期技术驱动转型为中长期基本面驱动。
核心公式: `combined_score = fundamental_score×0.70 + technical_score×0.20 + performance_score×0.10`

---

## Phase 1: 股票候选系统 — 基本面分融入 + 绩效分重构

### 1.1 `candidate_types.py` — 新增字段

- `CandidateResult.fundamental_score: float = 0.0` — 基本面四维综合评分

### 1.2 `candidate/scoring.py` — 评分公式重构

- **权重常量**: `FUNDAMENTAL_WEIGHT=0.70`, `TECHNICAL_WEIGHT=0.20`, `PERFORMANCE_WEIGHT=0.10`
- **绩效分重构**: 移除 Sharpe，`PERF_WEIGHTS={"max_drawdown": 0.60, "total_return": 0.40}`
- **回退机制**: `fundamental_score=0` 时自动回退到 `tech×0.70+perf×0.30`
- **DB 存储**: `save_results_to_db()` 写入 `fundamental_score`

### 1.3 `screening_engine.py` — 基本面评分加载

- Step 2.5 在因子打分与排名之间插入 `_load_fundamental_scores()` 调用，注入 `fundamental_score`
- `_load_fundamental_scores()`: 加载日频+季频 Parquet → 合并季频因子（PIT 约束）→ 计算 60 日动量 → `compute_final_score_only()` → 格式转换返回
- 处理 `SH↔SSE`, `SZ↔SZSE` 格式转换
- 异常处理: `FileNotFoundError`(Parquet 未生成) + `ImportError`(模块未装) + `Exception`(通用异常)
- `_results_to_dicts()`: 含 `fundamental_score` 输出

### 1.4 `models.py` — CandidateStock 加列

- `fundamental_score = Column(Numeric(8, 2))` — 基本面四维综合评分

### 1.5 `app.py` — API 响应更新

- `/api/candidates/latest` 和 `/api/candidates/history`: 响应中包含 `fundamental_score` 字段

---

## Phase 2: 季频数据 PIT 修复

### 2.1 `storage.py` — PIT 约束

- `get_latest_quarterly_snapshot()` 新增 `as_of_date: str | None` 参数
- PIT 过滤: `df = df.filter(pl.col("pub_date") <= as_of_date)`
- 降级策略: `as_of_date=None` 时不过滤，维持向后兼容
- 两个调用方均已传入 `as_of_date`:
  - `screening_engine.py`: `as_of_date=latest_date` (从日频快照获取)
  - `factor_api.py`: `as_of_date=daily_date` (从加载的日频数据获取)

---

## Phase 3: ETF 系统修复

### 3.1 `etf_types.py` — 移除废弃字段

- 移除 `tracking_error`, `dividend_yield`, `tracking_score`, `yield_score`
- `to_dict()` 同步更新

### 3.2 `etf_factors.py` — 流动性 log 变换 + 清理

- `avg_daily_volume = math.log(max(avg_volume_20, 1.0))`
- 移除 tracking_error、dividend_yield 相关计算

### 3.3 `etf_scoring.py` — 6 因子系统 + 绩效分重构

- **6 因子权重**: `liquidity(0.25), size(0.20), cost(0.15), premium(0.05), momentum(0.25), volatility(0.10)`
- **绩效分**: `max_drawdown(0.60) + total_return(0.40)` (移除 Sharpe)
- `_normalize_factors()`: 6 个因子数组（无 tracking/yield）
- `save_results_to_db()`: 仅写入 ORM 定义列

### 3.4 `etf_recommendation_engine.py` — 持仓联动

- `EtfRecommendationResult`: 新增 `is_held: bool = False`
- `_classify_action_by_rank()`: 已持仓+排名>30 或评分<60 → SELL
- `_normalize_ts_code()`: `510050.SH → 510050` 用于持仓匹配
- `generate_etf_recommendations()`: 查询 `Position` 表，归一化匹配

### 3.5 `models.py` — ETF DB 列清理 + 迁移

- `EtfCandidate`: 从 ORM 模型移除 `tracking_error`, `dividend_yield`, `tracking_score`, `yield_score`
- 新增 `_migrate_etf_candidates()`: 自动检测并 `DROP COLUMN` 废弃列（SQLite 3.35+ 支持）
- 挂接到 `get_db_session()` 启动时自动执行

---

## Phase 4: 推荐引擎优化

### 4.1 `recommendation_engine.py` — 阈值滞回

- **新常量**: `SCORE_SELL=58`, `SCORE_BUY_HYSTERESIS=63`（范围 5 点，减少假信号）
- `_classify_action()`: 新增 `prev_action` 参数；上日为 SELL 且新分<63 维持 SELL
- `_get_prev_recommendations()`: 回溯 5 天查询 `PortfolioRecommendation` 表
- 异常保护: 首次运行/表不存在时降级为纯阈值判断，不阻塞管道

### 4.2 `recommendation_engine.py` — 行业集中度约束

- `MAX_PER_INDUSTRY = 3`: 未持仓 Top 10 推荐中单行业最多 3 只
- `_get_industry_for_symbol()`: 从申万一级行业分类缓存查询，处理 `SH↔SSE` 格式
- 行业约束插入在排序后的未持仓循环中，空 industry 跳过约束

---

## 文件变更清单

| 操作 | 文件 | Phase |
|------|------|-------|
| 修改 | `web_app/candidate/candidate_types.py` | 1 |
| 修改 | `web_app/candidate/scoring.py` | 1 |
| 修改 | `web_app/candidate/screening_engine.py` | 1 |
| 修改 | `web_app/models.py` | 1, 3 |
| 修改 | `web_app/app.py` | 1 |
| 修改 | `vnpy/alpha/factors/fundamental/storage.py` | 2 |
| 修改 | `web_app/factor_api.py` | 2 |
| 修改 | `web_app/etf/etf_types.py` | 3 |
| 修改 | `web_app/etf/etf_factors.py` | 3 |
| 修改 | `web_app/etf/etf_scoring.py` | 3 |
| 修改 | `web_app/etf_recommendation_engine.py` | 3 |
| 修改 | `web_app/recommendation_engine.py` | 4 |

## 验证要点

- `ruug check` 零错误
- `_load_fundamental_scores()` Parquet 缺失时降级运行
- ETF DB 迁移自动删除旧列，不阻塞新行写入
- `_get_prev_recommendations()` 空表/表不存在安全降级
- 滞回逻辑在首次运行时退化为纯阈值判断
