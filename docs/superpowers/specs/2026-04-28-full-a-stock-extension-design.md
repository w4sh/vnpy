# 全A股前瞻因子系统扩展方案（修正版 v2）

> 日期：2026-04-28
> 状态：权限已就绪（2000积分），待确认后生成实施计划
>
> 修正说明：
> - v1：基于对现有代码库（vnpy/alpha/factors/、web_app/）的全面审查，修正了原方案中与实际代码状态不符的设计
> - v2：Tushare 已升级至 2000 积分，daily_basic / income / fina_indicator 全部可用，更新限流参数和迁移时间线

## 一、需求背景

### 1.1 当前状况

vnpy 前瞻因子系统（第一期 + 第二期）已完成，实现了两类前瞻性指标：

| 维度 | 因子 | 数据来源 | 权限状态 |
|------|------|----------|---------|
| 日频估值 | pe_ttm, pb, ps_ttm | `daily_basic` API | ✅ **2000积分已就绪** |
| 季频财务 | revenue_yoy, profit_yoy, roe, gross_margin, debt_to_assets | `income` + `fina_indicator` | ✅ **2000积分已就绪** |
| 资金流向 | north_net, north_ma5/10/20, flow_score | `moneyflow_hsgt` API | ✅ 免费可用 |

当前架构针对 **~250 只股票**的股票池设计，日终更新和因子计算在可接受时间内完成。

现有代码结构（已完成）：

```
vnpy/alpha/factors/
├── base.py              # DataFetcher / FactorComputer / FactorStorage 三个抽象基类
├── engine.py            # FactorEngine (总调度器) + FactorPipeline (单维度管线)
├── fusion.py            # DimensionScorer (截面排名) + SignalFusion (加权融合)
├── fundamental/
│   ├── fetcher.py       # FundamentalFetcher (fetch_daily_basic / fetch_income / fetch_fina_indicator)
│   ├── factors.py       # FundamentalComputer (compute_daily / compute_quarterly)
│   └── storage.py       # FundamentalStorage (fundamental_daily.parquet / fundamental_quarterly.parquet)
├── flow/
│   ├── fetcher.py       # FlowFetcher (fetch_hsgt_flow)
│   ├── factors.py       # FlowComputer (compute_flow)
│   └── storage.py       # FlowStorage (flow_daily.parquet)
└── sentiment/
    └── __init__.py      # 占位，尚未实现

web_app/
├── factor_api.py        # 4 个 API 端点 (/api/factors/{snapshot, history, detail, flow})
├── scheduler_tasks.py   # APScheduler 定时任务 (15:35 日终因子更新)
├── candidate/
│   ├── screening_engine.py  # 候选股筛选 (STOCK_POOL 约250只, run_screening)
│   └── backtest.py          # 回测指标计算
└── templates/index.html     # 前瞻指标标签页
```

### 1.2 用户需求

将前瞻因子系统扩展到 **全量 A 股（5000+ 只股票）**，实现：
- 全部 A 股股票的每日因子评估
- 完整的回测支持（全市场回测）
- 未来预测能力

### 1.3 当前权限能力（2000积分）

Tushare 已升级至 2000 积分，三个阶段所需的 API 全部可用：

| API | 积分门槛 | 当前权限 | 调用模式 | 频次 | 日总量 |
|-----|---------|---------|---------|------|--------|
| `stock_basic` | 免费 | ✅ 可用 | 一次获取全部 | 200次/分钟 | 10万次 |
| `daily` | 免费 | ✅ 可用 | 按日期全市场 | 200次/分钟 | 10万次 |
| `moneyflow_hsgt` | 免费 | ✅ 可用 | 按日期范围 | 200次/分钟 | 10万次 |
| `daily_basic` | 2000 | ✅ **已就绪** | 按日期全市场 | 200次/分钟 | 10万次 |
| `income` | 2000 | ✅ **已就绪** | 逐只拉取 | 200次/分钟 | 10万次 |
| `fina_indicator` | 2000 | ✅ **已就绪** | 逐只拉取 | 200次/分钟 | 10万次 |

能力评估：
- 日频全量更新（`daily_basic` 一次调用 + `moneyflow_hsgt` 一次调用）：每次 2 个 API 请求，秒级完成
- 季频冷启动（5000只 × 2个API = 10000次调用）：200次/分钟 ≈ 50 分钟完成，10万次/天绰绰有余
- 季频增量更新（财报旺季 ~500-1000 只欠更新）：~2000次调用，约 10 分钟完成

---

## 二、权限状态确认（✅ 已完成）

### 2.1 当前权限

Tushare 账户已升级至 **2000 积分**，以下接口全部可用：

- `daily_basic`（日频估值）：PE/PB/PS/总市值/换手率 — 全市场一次拉取
- `income`（利润表）：营收/净利润/营业利润 — 逐只拉取
- `fina_indicator`（财务指标）：ROE/ROA/毛利率/净利率/负债率 — 逐只拉取

### 2.2 API 频率与容量（2000积分）

| 参数 | 值 | 说明 |
|------|-----|------|
| 每分钟频次 | 200次/分钟 | 是免费版（50次）的 4 倍 |
| 每日总调用量 | 10万次/API | 足够全量A股冷启动一次性完成 |
| 日频日常开销 | ~2次/天 | daily_basic(1次) + moneyflow_hsgt(1次) |
| 季频冷启动 | ~10000次 | 5000只 × 2 API，约 50 分钟完成 |
| 季频增量 | ~2000次 | 财报旺季 500-1000 只欠更新，约 10 分钟

---

## 三、需求讨论过程

### 3.1 全A股范围的讨论

**问题**：全 A 股的范围如何定义？

**结论**：选择方案 2（全量 A 股），架构上不做股票池大小限制。通过 `stock_basic` API（免费可用）获取全量代码列表，包含 A 股沪深两市所有正常交易股票。

---

### 3.2 数据获取策略的讨论

**问题**：全量 5000+ 只股票的数据如何获取？

**重要修正**：不同 API 的拉取模式完全不同，需区分对待：

| API | 拉取模式 | 策略 |
|-----|---------|------|
| `daily_basic` | 全市场批量（一次调用返回全部） | 不需分批，一次调用即可 |
| `moneyflow_hsgt` | 市场级（一次调用返回全部） | 不需分批，一次调用即可 |
| `income` | 逐只调用 | 需要分批，50只/批 |
| `fina_indicator` | 逐只调用 | 需要分批，50只/批 |

**结论**：
- **日频数据**（daily_basic + moneyflow_hsgt）：一次全量拉取，无需分批
- **季频数据**（income + fina_indicator）：分批拉取 + 本地缓存增量更新
- 首日全量拉取并缓存到本地
- 之后每日增量更新（只拉取有变化的股票）

---

### 3.3 因子计算策略的讨论

**问题**：5000+ 只股票的因子计算策略？

**结论**：每日全量计算。Polars 对 5000 × 365 的数据量计算在秒级完成，全量计算的成本远低于增量逻辑的复杂度。

---

### 3.4 改造优先级的讨论

**修正**：实际优先级应为 **数据源就绪 > 稳定性 > 存储 > 速度 > 前端展示**。

| 优先级 | 事项 | 说明 |
|--------|------|------|
| ~~P0~~ ✅ | ~~数据源权限就绪~~ | ✅ 已升级至 2000 积分，daily_basic/income/fina_indicator 全部可用 |
| P0 | StockPoolManager | 替代手选 250 只 STOCK_POOL，提供全量A股代码列表 |
| P0 | FactorEngine 增强（分批 + checkpoint） | 季频因子分批拉取的核心设施 |
| P1 | 日频数据冷启动 | 清空模拟数据，首次拉取全量 daily_basic 真实数据 |
| P1 | 季频数据冷启动 | 首次全量拉取 income + fina_indicator，约 50 分钟 |
| P1 | 回测层适配 | get_factor_matrix 支持全量 |
| P2 | 前端进度指示器 | 简单的状态灯（✅/🔄/❌），先不做完整状态页面 |
| P3 | 前端完整同步状态页 | 低优先级，非用户高频场景 |

---

## 四、最终设计方案

### 4.1 整体架构

```
┌──────────────────────────────────────────────────────┐
│              Scheduler (APScheduler)                 │
│ 周一至周五 15:35 日终因子更新                          │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│           FactorEngine (增强现有引擎)                 │
│                                                      │
│  现有能力（不变）:                                    │
│    run_daily(symbols, trade_date)                     │
│    run_quarterly(symbols, end_date)                   │
│    get_latest_snapshot(symbols)                       │
│    get_factor_matrix(symbols, start, end)             │
│                                                      │
│  新增能力:                                            │
│    StockPoolManager (全量股票代码)          ← 新增 │
│    CheckpointManager (断点恢复)            ← 新增    │
│    RateLimiter (API限流)                   ← 新增    │
│    run_quarterly_batch() (分批季频更新)    ← 新增    │
└──────────────────────┬───────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
┌──────────────────┐    ┌──────────────────────┐
│ Tushare API      │    │  Parquet Storage     │
│ 批量: 一次拉全量  │    │ (保持单文件模式)      │
│ 逐只: 50只/批限流 │    │  ~/.vntrader/factors/ │
└──────────────────┘    └──────────────────────┘
```

### 4.2 新增与修改组件

| 组件 | 文件 | 操作 | 说明 |
|------|------|------|------|
| `FactorEngine` | `engine.py` | **修改** | 新增 `checkpoint_manager` 属性，`run_quarterly()` 增加分批逻辑 |
| `CheckpointManager` | `checkpoint.py` | **新增** | 断点恢复管理，JSON 文件记录已处理批次 |
| `StockPoolManager` | `stock_pool.py` | **新增** | 通过 `stock_basic` 获取全量A股代码，替代手选 STOCK_POOL |
| `RateLimiter` | `rate_limiter.py` | **新增** | 通用 API 限流器（令牌桶算法），供 Fetcher 层注入 |
| `scheduler_tasks.py` | `web_app/` | **修改** | 使用 StockPoolManager 获取全量股票池 |
| `factor_api.py` | `web_app/` | **修改** | `get_stock_pool()` 改为从 StockPoolManager 获取 |

### 4.3 股票池管理

```
StockPoolManager (股票池管理器)
│
├── __init__(data_dir)
│   └── 从 ~/.vntrader/factors/stock_pool.json 加载缓存
│
├── get_full_pool() → List[str]
│   ├── 优先返回缓存（已同步过的全量列表）
│   └── 无缓存时调用 sync() 首次同步
│
├── sync() → List[str]
│   ├── 调用 stock_basic(list_status="L") 获取上市公司代码
│   ├── 过滤: 剔除退市(list_status="D")、暂停(list_status="P")
│   ├── 过滤: 剔除 ST/*ST 股票(通过 name 字段)
│   ├── 转换格式: 000001.SZ → 000001.SZSE
│   ├── 缓存到 stock_pool.json
│   └── 返回当前有效股票列表
│
├── get_new_listings(since_date) → List[str]
│   └── 返回自某日期后新上市的股票
│
└── get_filtered_pool(filter_rules) → List[str]
    └── 用户自定义过滤（市值范围、板块等）
```

**与现有系统的集成**：
- **替代** `web_app/candidate/screening_engine.py` 中的手选 `STOCK_POOL`（约250只）
- **替代** `factor_api.py` 中的 `get_stock_pool()` 函数
- `stock_basic` 是免费接口，无需升级权限即可使用

### 4.4 API 限流层

```
RateLimiter (令牌桶限流器)
│
├── __init__(rate_per_minute=200, burst=20)
│   └── burst: 允许的瞬时突发请求数（2000积分：200次/分钟）
│
├── acquire() → None
│   ├── 获取一个令牌（阻塞直到可用）
│   └── 自动等待至下次允许的时间
│
├── acquire_batch(n: int) → None
│   └── 批量获取 n 个令牌
│
└── get_stats() → dict
    └── {used_today, remaining, reset_time}
```

**注意**：`daily_basic` 和 `moneyflow_hsgt` 是市场级全量接口，每次调用只需 1 个令牌，不受 batch_size 限制。只有 `income` 和 `fina_indicator`（逐只拉取）需要按 batch_size=50 限流。

### 4.5 数据获取层（修正版）

```
日频数据拉取（一次全量，无分批）:
│
├── daily_basic(trade_date)
│   └── 1 次 API 调用 → 返回当日全量 4000-5000 行
│       └── 列: trade_date, ts_code, pe, pe_ttm, pb, ps, ps_ttm,
│                total_mv, circ_mv, turnover_rate
│
├── moneyflow_hsgt(end_date)
│   └── 1 次 API 调用 → 返回近 90 天资金流向序列
│       └── 列: trade_date, north_cum, south_cum → 差分得日净流入

季频数据拉取（分批，50只/批）:
│
├── income(ts_code)
│   └── 逐只调用 × N 只欠更新股票
│       └── 每批 50 只，间隔 3 秒
│       └── 重试机制: 失败 → 5s → 10s → 15s (最多3次)
│
└── fina_indicator(ts_code)
    └── 同上，逐只调用 × N 只欠更新股票
```

**与第一版方案的差异**：

| 项 | 第一版 | 修正版 |
|-----|--------|--------|
| daily_basic 调用次数 | 100批 × 50只/批 = 100次 | **1次**（全市场批量接口） |
| daily_basic 耗时 | ~300秒（含间隔） | ~1秒 |
| 分批对象 | 所有API | 仅 income + fina_indicator |
| 是否新建 Fetcher 类 | `TushareDataFetcher` | 保持现有 `FundamentalFetcher`，注入 `RateLimiter` |

### 4.6 存储层（保持单文件模式）

```
Parquet Storage (单文件模式，仅在季频层增加分批写入)
├── 目录结构
│   └── ~/.vntrader/factors/
│       ├── fundamental_daily.parquet     # 所有日频因子（维持现有格式）
│       ├── fundamental_quarterly.parquet # 所有季频因子（维持现有格式）
│       ├── flow_daily.parquet            # 所有资金流数据（维持现有格式）
│       └── stock_pool.json               # 全量股票池缓存 (新增)
│
├── Checkpoint (仅用于季频分批拉取)
│   └── ~/.vntrader/factors/checkpoint/
│       └── quarterly_sync_20241025.json
│       {
│           "batch_num": 15,
│           "processed": ["000001.SZSE", "000002.SZSE", ...],
│           "failed": [{"symbol": "600036.SSE", "error": "timeout", "retries": 2}],
│           "status": "in_progress"
│       }
│
└── 与第一版的差异
    ├── 取消: 按日期分区 (date=YYYYMMDD/data.parquet)
    ├── 取消: 临时目录 + commit 策略
    ├── 取消: meta.json 批次元数据
    └── 保持: 现有单文件 Parquet 格式，通过 checkpoint 的 processed 列表实现断点恢复
```

**为什么保持单文件模式而不是按日期分区**：

- 数据量不大：5000只 × 12字段 × ~20字节/行 ≈ 120KB/天，全量历史 ≈ 30MB
- Polars Parquet 读取 30MB 文件 < 0.1秒，按日期分区无显著性能提升
- 避免迁移成本：现有 `load/get_latest/get_factor_matrix` 接口无需重写
- 断点恢复可通过 checkpoint 的 processed 列表实现，不需要文件级隔离

### 4.7 FactorEngine 增强方案

**不改写现有 `FactorEngine`，在其基础上增量增强**：

```
FactorEngine (增强版)
│
├── 现有方法 (不变):
│   ├── register(name, frequency, fetcher, computer, storage)
│   ├── run_daily(symbols, trade_date)  → dict
│   ├── get_latest_snapshot(symbols)     → pl.DataFrame
│   └── get_factor_matrix(symbols, start, end) → pl.DataFrame
│
├── 新增属性:
│   ├── self.stock_pool: StockPoolManager | None
│   ├── self.rate_limiter: RateLimiter | None
│   └── self.checkpoint: CheckpointManager | None
│
├── 新增方法:
│   ├── init_stock_pool(data_dir) → None
│   │   └── 创建 StockPoolManager 实例
│   │
│   ├── run_quarterly_batch(symbols, end_date, batch_size=50) → dict
│   │   ├── 从 checkpoint 恢复上次中断位置
│   │   ├── 分批拉取 income + fina_indicator
│   │   ├── 每批计算因子 → 追加写入 Parquet
│   │   ├── 每批更新 checkpoint
│   │   └── 完成后标记 checkpoint 完成
│   │
│   └── get_sync_status() → dict
│       └── 返回本次同步的状态信息
```

**日频 run_daily 无需改动**（daily_basic 全市场一次拉取），仅季频需要分批增强。

### 4.8 分批执行流程（仅季频）

```
FactorEngine.run_quarterly_batch(symbols, end_date, batch_size=50)
│
├── Step 1: 初始化
│   ├── 获取待处理列表: symbols - checkpoint.processed
│   ├── 如果有 checkpoint 记录，从中断位置继续
│   └── 确定财报缓存日期（避免重复拉取已有数据）
│
├── Step 2: 分批处理 (仅对逐只接口)
│   │
│   └── for batch_idx, batch in enumerate(batches(pending, batch_size)):
│       │
│       ├── 2.1: 限流
│       │   └── rate_limiter.acquire_batch(len(batch))
│       │
│       ├── 2.2: 拉取数据 (逐只)
│       │   └── for symbol in batch:
│       │       ├── fetch_income(ts_code)
│       │       └── fetch_fina_indicator(ts_code)
│       │
│       ├── 2.3: 计算因子
│       │   └── computer.compute_quarterly(all_income, all_fina, all_disc)
│       │
│       ├── 2.4: 写入存储
│       │   └── storage.save_quarterly(factors)  # 追加到 Parquet
│       │
│       ├── 2.5: 更新 checkpoint
│       │   └── checkpoint.save({
│       │       "batch_num": batch_idx,
│       │       "processed": [...batch],
│       │       "failed": [...failed_in_batch],
│       │       "status": "in_progress"
│       │   })
│       │
│       └── 2.6: 批次间隔
│           └── time.sleep(3)  # 对 Tushare 友好的批量间隔
│
├── Step 3: 完成
│   ├── checkpoint.mark_complete()
│   ├── 记录失败股票列表（供下次重试）
│   └── 返回结果统计
│
└── Step 4: 异常恢复
    └── 任何步骤失败 → checkpoint 保持 "in_progress"
        → 下次 run_quarterly_batch 自动跳过 processed 列表中的股票
```

### 4.9 异常处理

```
任何步骤失败 →
    ① 记录失败股票和错误到 checkpoint.failed
    ② 保持 checkpoint.status = "in_progress"
    ③ 数据已写入 Parquet（成功的部分），失败的未写入
    ④ 下次 run_quarterly_batch 时自动跳过 processed，继续处理未完成的

调度器重试策略:
    - 当日失败 → 次日 run_quarterly_batch 自动恢复
    - 连续失败超过 3 天 → 发送 WARN 日志，人工介入
```

### 4.10 季频因子更新流程

```
季频更新流程（每季度财报季执行，"欠更新检测"策略）
│
├── Step 1: 确定财报窗口
│   ├── 4月底（年报）、8月底（中报）、10月底（三季报）
│   └── 窗口期：截止日后 5 个交易日（调用 is_earnings_window 判断）
│
├── Step 2: 获取欠更新股票列表
│   ├── 对比 StockPoolManager.get_full_pool() 与 storage 中已有最新财报日期
│   ├── 筛选出: 财报发布日期 > 缓存中的最新财报日期
│   └── 跳过: 已是最新财报（避免重复拉取，节省积分）
│
├── Step 3: 分批处理（仅对欠更新股票，50只/批，间隔3秒）
│   │
│   └── for batch in batches(outdated_stocks, batch_size=50):
│       ├── rate_limiter.acquire_batch(len(batch))
│       ├── fetch_income(ts_code) × batch
│       ├── fetch_fina_indicator(ts_code) × batch
│       ├── fetch_disclosure_date(ts_code) × batch
│       ├── compute_quarterly(all_raw)
│       ├── save_quarterly(factors)  # 追加到 Parquet
│       └── checkpoint.update(batch_idx, batch)
│
└── Step 4: 全量计算
    ├── 财报数据就绪后，对所有 stock_pool 做全量季频因子计算
    └── 前值填充: 非报告期用最近一期财报数据填充
```

**欠更新检测的优势**：
- 5000只股票中，单次财报季真正需要更新的可能只有500-1000只（窗口期发布的财报）
- 减少50%以上的 API 调用量
- 历史财报不再重复拉取

### 4.11 与现有系统集成

```
现有系统                          新增/修改
──────────────────────────────────────────────────
vnpy/alpha/factors/
├── engine.py                     [修改] 季频增加分批逻辑 + checkpoint
├── checkpoint.py                 [新增] CheckpointManager
├── stock_pool.py                 [新增] StockPoolManager
├── rate_limiter.py               [新增] RateLimiter
├── fundamental/
│   ├── fetcher.py                [修改] 注入 RateLimiter
│   ├── factors.py                [不变]
│   └── storage.py                [不变]
├── flow/
│   └── (全部不变)
└── base.py                       [不变]

web_app/
├── scheduler_tasks.py             [修改] 使用 StockPoolManager + 季频分批
├── factor_api.py                 [修改] get_stock_pool() 改用 StockPoolManager
└── candidate/
    └── screening_engine.py       [修改] STOCK_POOL 改为从 StockPoolManager 获取
```

### 4.12 数据迁移计划

从当前 250 只模拟数据 → 全量 5000+ 只真实数据的过渡步骤：

```
Phase 0: 权限升级 ✅ 已完成
├── Tushare 已升级至 2000+ 积分
└── daily_basic、income、fina_indicator 接口可调用

Phase 1: 股票池扩展（首次运行，下一步实施）
├── StockPoolManager.sync() 获取全量A股代码（~5000只）
├── 自动缓存到 ~/.vntrader/factors/stock_pool.json
└── 替换 factor_api.py 中的 get_stock_pool()

Phase 2: 日频数据冷启动（首次运行，~1秒完成）
├── 删除 ~/.vntrader/factors/fundamental_daily.parquet（清理模拟数据）
├── FactorEngine.run_daily(full_pool, today)
│   ├── fetch_daily_basic(today) → 1次调用，获取全量估值
│   └── compute_daily + save_daily → 写入真实数据
└── 后续每日增量追加（同一 Parquet 文件）

Phase 3: 季频数据冷启动（首次运行，~50分钟内完成，2000积分一天搞定）
├── run_quarterly_batch(full_pool, today, batch_size=50)
│   ├── 5000只 × 2个API (income + fina_indicator) = ~10000次调用
│   ├── 200次/分钟频次: 10000÷200 = 50分钟（含API响应时间）
│   ├── 日总量 10万次，10000次只占 10%，充裕
│   └── 批次间隔 3 秒仍然保留（对服务器友好，非性能瓶颈）
└── 结束后标记完成，后续仅增量更新欠更新股票

Phase 4: Web API 更新
├── snapshot 端点: 返回全量前50名（无需改动）
├── history 端点: 数据集变大，考虑增加分页
└── flow 端点: 无需改动（市场级数据不变）
```

### 4.13 测试策略

在现有 8 个单元测试基础上，新增以下测试场景：

| 测试类 | 测试内容 | 优先级 |
|--------|---------|--------|
| `TestStockPoolManager` | sync 获取代码列表、过滤退市/ST、缓存读写 | P0 |
| `TestCheckpointManager` | 保存/加载/恢复 checkpoint、处理完成状态 | P0 |
| `TestRateLimiter` | 令牌获取、速率限制、统计查询 | P0 |
| `TestFactorEngineBatch` | run_quarterly_batch 分批逻辑、断点恢复、失败重试 | P0 |
| `TestFullPoolIntegration` | 全量 5000 只模拟数据端到端流程 | P1 |

### 4.14 风险缓解措施

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| API 超时/限流导致批次失败 | 当次拉取数据不完整 | checkpoint 自动记录，下次恢复；200次/分钟频次留有充足余量 |
| 季频冷启动中途网络中断 | 需从头开始 | checkpoint 保证断点续传，已处理股票自动跳过 |
| Tushare 服务临时不可用 | 当次定时任务失败 | scheduler 次日自动重试，checkpoint 从断点恢复 |
| 存储文件损坏 | 所有因子数据丢失 | 运行 `run_daily` / `run_quarterly_batch` 重建（数据源在 Tushare） |
| Parquet 文件增大到几百MB | 查询变慢 | 5000只估算约 30MB/年，3年内无需分区 |

---

## 五、数据切换清单

权限已就绪（2000积分），从当前模拟数据切换到真实全量数据的操作步骤：

| 步骤 | 操作 | 命令/方法 |
|------|------|----------|
| 1 | 删除模拟日频数据 | `rm ~/.vntrader/factors/fundamental_daily.parquet` |
| 2 | 删除模拟季频数据 | `rm ~/.vntrader/factors/fundamental_quarterly.parquet` |
| 3 | 首次执行日频更新 | `engine.run_daily(full_pool, today)` — 1次 daily_basic 调用 |
| 4 | 首次执行季频冷启动 | `engine.run_quarterly_batch(full_pool, today)` — 约50分钟 |
| 5 | 验证 Web API | 访问 `/api/factors/snapshot` 检查真实数据返回 |
| 6 | 确认调度器 | 检查 scheduler 下次 15:35 自动触发是否正常 |

数据恢复说明：如果切换出现问题，原有的模拟数据可以通过重新构造 Mock 数据来恢复，或直接从头拉取真实数据。

---

## 六、未来扩展方向

```
Phase 1（当下）：Tushare 单数据源 + 增强 FactorEngine
├── StockPoolManager (全量A股代码)
├── FactorEngine 增强版 (季频分批 + checkpoint)
├── RateLimiter (API 限流)
└── 保持单文件 Parquet 存储

Phase 2（近期）：多数据源支持
├── DataSource 抽象接口
├── AkshareStockSource（免费替代，备选）
├── EastMoneyStockSource（东方财富）
└── 配置化切换数据源

Phase 3（远期）：性能优化
├── ThreadPoolExecutor 并行拉取季频数据（I/O 密集型提速）
├── asyncio 异步 API 调用
└── 按日期分区存储（当数据量超过百MB时启用）
```

---

## 七、不做什么

- 不做分布式调度（单机日终批处理足够）
- 不做实时增量更新（日终全量计算优先完整性和简单性）
- 不做按日期分区的存储改造（当前数据量不需要，待数据量超过百MB后再考虑）
- 不做多数据源切换（作为 Phase 2）
- 不做行业中性化处理（后续迭代考虑）
- 不做前端完整同步状态页面（前端降低优先级，先用日志 + 简单状态指示器）
