# 全A股前瞻因子系统扩展方案

> 日期：2026-04-28
> 状态：设计已确认，待生成实施计划

## 一、需求背景

### 1.1 当前状况

vnpy 前瞻因子系统（第一期 + 第二期）已完成，实现了三类前瞻性指标：
- 基本面因子（营收增速、PE/PB、ROE 等 7 个因子）
- 资金流向因子（北向资金 + 情绪评分）

当前架构针对 **250 只股票**的股票池设计，日终更新和因子计算在可接受时间内完成。

### 1.2 用户需求

将前瞻因子系统扩展到 **全量 A 股（5000+ 只股票）**，实现：
- 全部 A 股股票的每日因子评估
- 完整的回测支持（全市场回测）
- 未来预测能力

### 1.3 核心约束

| 约束项 | 当前情况 | 说明 |
|--------|----------|------|
| 数据源 | Tushare 免费版 | 1200 积分 |
| API 限速 | 每分钟 50 次调用 | 每日约 5000 次上限 |
| 数据费用 | 免费 + 积分制 | 高级数据需积分兑换 |

---

## 二、需求讨论过程

### 2.1 全A股范围的讨论

**问题**：全 A 股的范围如何定义？

**选项**：
1. 扩大股票池（250 → 2000-3000 只）
2. 全量 A 股（5000+ 只）
3. 用户可配置任意范围

**结论**：选择方案 2（全量 A 股），架构上不做股票池大小限制。

---

### 2.2 数据获取策略的讨论

**问题**：全量 5000+ 只股票的数据如何获取？

**选项**：
1. Tushare 全市场批量接口
2. 本地缓存 + Tushare 增量
3. 混合模式

**结论**：选择方案 2（本地缓存 + 增量更新）。
- 首日全量拉取并缓存到本地
- 之后每日增量更新（只拉取有变化的股票）

---

### 2.3 因子计算策略的讨论

**问题**：5000+ 只股票的因子计算策略？

**选项**：
1. 每日全量计算
2. 按需计算 + 增量更新

**结论**：选择方案 1（每日全量计算）。
- 优先保证数据完整性
- 用户接受较长的计算时间（日终批处理场景）

---

### 2.4 改造优先级的讨论

**问题**：改造涉及多个环节，优先级如何？

**选项**：
1. 速度优先
2. 存储优先
3. 稳定性优先

**结论**：优先级为 **稳定性 > 存储 > 速度**。
- 稳定性最重要：数据不能丢失，API 限速友好
- 存储其次：支持大数据量高效读写
- 速度最后：日终批处理场景，速度可接受

---

### 2.5 数据源扩展的讨论

**问题**：未来可能切换其他数据源，如何设计？

**结论**：采用多数据源抽象。
- 定义 `DataSource` 抽象接口
- 未来可接入东方财富、万得等
- 当下先以 Tushare 实现并跑通功能

---

### 2.6 限流策略的讨论

**问题**：Tushare 免费版（1200 积分）如何设计限流？

**方案**：50 只/批次，间隔 3 秒。
- 每批次处理 50 只股票
- 每批次完成后休眠 3 秒
- 每日可处理约 1667 只（3 天完成一次全量同步）
- 之后每日增量更新

---

## 三、最终设计方案

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Scheduler (APScheduler)                  │
│  周一至周五 15:30 候选股筛选                                 │
│  周一至周五 15:35 日终因子更新                               │
└──────────────────────┬────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                 BatchFactorEngine (新增)                    │
│                                                              │
│  ① load_stock_pool()     ──→  A股全量股票列表 (5000+只) │
│  ② load_checkpoint()      ──→  恢复中断的批次进度           │
│  ③ run_daily_batch()    ──→  分批处理，每批50只          │
│  ④ save_checkpoint()     ──→  每批完成后写checkpoint        │
│  ⑤ commit_partition()   ──→  数据全部成功后commit到正式表  │
└──────────────────────┬────────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
┌──────────────────┐    ┌──────────────────────┐
│ Tushare API     │    │  Parquet Storage     │
│ (限流+重试+退避)│    │  (按日期分区)         │
│ 50只/批, 3秒间隔│    │  ~/.vntrader/factors/ │
└──────────────────┘    └──────────────────────┘
```

### 3.2 新增组件

| 组件 | 文件 | 说明 |
|------|------|------|
| `BatchFactorEngine` | `engine.py` | 支持分批执行和 checkpoint 恢复的因子引擎 |
| `CheckpointManager` | `checkpoint.py` | 断点恢复管理 |
| `StockPoolManager` | `stock_pool.py` | A 股全量股票池管理 |
| `TushareDataFetcher` | `fetcher.py` | Tushare 数据拉取（限流+重试） |

### 3.3 股票池管理

```
StockPoolManager (股票池管理器)
├── DataSource (抽象基类)  ← 未来扩展预留
│   ├── fetch_stock_list() → List[StockInfo]
│   └── fetch_delist_info() → List[str]  # 剔除股票
│
├── TushareStockSource (Tushare 实现)  ← 当下
│   └── 调用 stock_basic 接口
│
└── StockPoolManager
    ├── _data_source: DataSource  # 可注入
    ├── get_full_pool() → List[str]  # 当前股票池
    ├── get_delisted() → List[str]  # 剔除股票
    └── sync()  # 增量同步
```

**数据源扩展（Future TODO）**：
- 未来可接入 EastMoney、Wind、同花顺等
- 通过 `DataSourceFactory` 注入不同数据源实现
- 不影响现有 Tushare 实现

### 3.4 数据获取层

```
TushareDataFetcher (免费版 1200 积分)
├── 每日硬性上限：5000 次 API 调用（留余量）
│
├── 分批策略
│   ├── 日频（daily_basic）：全量股票分批处理
│   │   └── 每批次 50 只，间隔 3 秒
│   │
│   └── 每批次后休眠 3 秒
│
├── 重试机制
│   ├── 首次失败 → 等待 5s → 重试 → 10s → 15s
│   ├── 最大重试次数：3 次
│   └── 429 错误（限速）→ 等待 60s 后继续
│
└── 断点续传
    ├── checkpoint 记录每批最后成功的股票代码
    └── 中断后从 checkpoint 恢复
```

### 3.5 存储层

```
Parquet Storage (按日期分区)
├── 目录结构
│   └── ~/.vntrader/factors/
│       ├── fundamental_daily/
│       │   ├── date=20241025/
│       │   │   ├── data.parquet  (当日全量)
│       │   │   └── meta.json     (批次元数据)
│       │   ├── date=20241024/
│       │   └── ...
│       │
│       ├── fundamental_quarterly/
│       │   ├── date=20241025/
│       │   └── ...
│       │
│       └── flow_daily/
│           ├── date=20241025/
│           └── ...
│
├── Checkpoint (批次进度)
│   └── ~/.cache/vnpy/checkpoints/
│       └── fundamental_daily_20241025.json
│       {
│           "batch_id": 15,
│           "last_success_symbol": "600036.SSE",
│           "processed": ["000001.SZSE", ...],
│           "failed": [{"symbol": "600036.SSE", "error": "timeout"}],
│           "timestamp": "2024-10-25T15:45:00"
│       }
│
├── 写入策略
│   ├── 每批次数据先写入 `~/.tmp/factors/` 临时目录
│   ├── 批次全部成功 → 移动到正式分区 `date=YYYYMMDD/`
│   └── 批次失败 → 保留临时文件，重试后覆盖
│
└── 查询策略
    ├── get_latest(trade_date)  → 读取指定日期分区
    └── get_range(start, end)   → 合并多个日期分区
```

### 3.6 分批执行流程

```
BatchFactorEngine.run_daily(trade_date)
│
├── Step 1: 初始化
│   ├── 加载股票池（StockPoolManager）
│   ├── 加载 checkpoint（如有中断记录）
│   └── 过滤已处理的股票，保留待处理列表
│
├── Step 2: 分批处理
│   │
│   └── for batch in batches(stock_list, batch_size=50):
│       │
│       ├── Step 2.1: 拉取数据
│       │   ├── fetcher.fetch_daily_basic(symbols=batch)
│       │   └── fetcher.fetch_hsgt_flow(trade_date)  # 北向资金（每批只拉1次）
│       │
│       ├── Step 2.2: 计算因子
│       │   ├── computer.compute_daily(raw)
│       │   └── computer.compute_flow(raw)
│       │
│       ├── Step 2.3: 写入临时目录
│       │   └── storage.save_batch(batch_data, tmp=True)
│       │
│       ├── Step 2.4: 更新 checkpoint
│       │   └── checkpoint.update(batch_id, success_symbols)
│       │
│       └── Step 2.5: 休眠
│           └── time.sleep(3)
│
├── Step 3: 提交数据
│   ├── 验证所有批次完成
│   ├── 将临时分区数据 commit 到正式分区
│   └── 清理临时文件
│
└── Step 4: 更新完成状态
    └── checkpoint.mark_complete()
```

### 3.7 异常处理

```
任何步骤失败 →
    ① 记录失败批次和股票到 checkpoint.failed
    ② 保存当前进度
    ③ 抛出 BatchError 供调度器捕获
    ④ 下次运行时自动从 checkpoint 恢复
```

**调度器重试策略**：
- 当日失败 → 次日自动重试失败的批次
- 连续失败超过 3 天 → 标记股票，人工介入

### 3.8 季频因子更新流程

```
季频更新流程（每季度财报季执行）
│
├── Step 1: 确定财报窗口
│   ├── 4月底（年报）、8月底（中报）、10月底（三季报）
│   └── 窗口期：截止日后 5 个交易日内
│
├── Step 2: 获取待更新股票列表
│   ├── 从 checkpoint 获取上次失败的股票
│   └── 从 stock_pool 获取尚未更新的股票
│
├── Step 3: 分批处理（50只/批，间隔3秒）
│   │
│   └── for batch in batches(stock_list, batch_size=50):
│       │
│       ├── fetch_income(ts_code)          # 利润表
│       ├── fetch_fina_indicator(ts_code)  # 财务指标
│       ├── fetch_disclosure_date(ts_code) # 公告日
│       │
│       ├── compute_quarterly(income, fina, disclosure)
│       │
│       ├── save_batch(batch_data, tmp=True)
│       │
│       └── checkpoint.update(batch_id, success_symbols)
│
└── Step 4: 增量更新策略
    │
    ├── 只拉取新财报（对比缓存中的最新财报日期）
    ├── 历史财报不重复拉取（节省积分）
    └── 财报发布日期作为 pub_date 前值填充
```

### 3.9 前端进度展示

```
新增「数据同步状态」标签页
│
├── 实时进度
│   ├── 当前批次：15/100
│   ├── 已处理：750/5000 只
│   ├── 进度条：15%
│   ├── 预计剩余时间：约 45 分钟
│   └── 当前处理：600036.SSE
│
├── 状态面板
│   ├── 日频更新：✅ 完成 / 🔄 进行中 / ❌ 失败
│   ├── 季频更新：✅ 完成 / ⏳ 等待中 / ❌ 失败
│   └── 北向资金：✅ 完成 / 🔄 进行中 / ❌ 失败
│
├── 失败记录
│   ├── 股票代码 | 失败原因 | 重试次数
│   ├── 600036.SSE | API 超时 | 2/3
│   └── 000001.SZSE | 积分不足 | 3/3 ❌
│
└── 操作按钮
    ├── 暂停同步
    ├── 强制重试失败项
    └── 查看历史记录
```

### 3.10 与现有系统集成

```
现有系统                      新增/修改
─────────────────────────────────────────────────────
web_app/
├── scheduler_tasks.py         # 修改：使用 BatchFactorEngine
├── factor_api.py             # 修改：适配新存储格式
│
vnpy/alpha/factors/
├── engine.py                 # 修改：新增 BatchFactorEngine
├── base.py                   # 新增：CheckpointManager
├── stock_pool.py             # 新增：StockPoolManager
├── storage.py               # 重构：按日期分区存储
└── checkpoint.py             # 新增：断点恢复逻辑
```

---

## 四、未来扩展方向

```
Phase 1（当下）：Tushare 单数据源
├── StockPoolManager + TushareStockSource
├── BatchFactorEngine + CheckpointManager
└── 按日期分区存储

Phase 2（未来）：多数据源支持
├── DataSource 抽象接口
├── EastMoneyStockSource（东方财富）
├── WindStockSource（万得，需商业授权）
└── 配置化切换数据源

Phase 3（未来）：性能优化
├── ThreadPoolExecutor 并行拉取（I/O 密集型提速）
├── asyncio 异步 API 调用
└── 本地缓存层优化
```

---

## 五、不做什么

- 不做分布式调度（当前为单机日终批处理场景，无需分布式）
- 不做实时增量更新（当前为日终批处理，每日全量计算）
- 不做多数据源切换（作为 Future TODO）
- 不做行业中性化处理（后续迭代考虑）
