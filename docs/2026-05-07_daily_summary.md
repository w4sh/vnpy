# 2026-05-07 工作记录

## 完成事项

### 1. 动量因子修复

**问题**：因子快照中动量因子 `momentum_60d` 全部为 50.0（中位数），因为日频 Parquet 中缺少 close 列。

**修复**：
- `scripts/backfill_close.py` — 从 Tushare 拉取最近 60 个交易日的 `daily_basic` 数据（含 close），经 `compute_daily` 格式转换后合并到日频因子 Parquet。合并 328,801 行 close 数据到原有的 7,228,091 行 parquet。
- `web_app/factor_api.py` — `_compute_momentum_60d()` 使用 `drop_nulls().first()` / `drop_nulls().last()` 代替 `first()` / `last()`，避免最早交易日 close 为空时导致整个聚合结果出错。
- `vnpy/alpha/factors/fundamental/fetcher.py` — `fetch_daily_basic()` 的 `keep_cols` 中加入 `"close"`，确保后续日频取数自动包含收盘价。

**效果**：50/50 只候选股全部显示合理动量评分，4 维度评分系统（估值/质量/成长/动量）正常工作。

### 2. ETF 推荐面板

**问题**：ETF 引擎有多个 Bug 导致管道无法运行：(1) `fund_basic` 的 `fund_type` 为中文分类而非 "ETF-ETF"；(2) 规模列名为 `issue_amount` 而非 `fund_size`；(3) 费率列名为 `m_fee`/`c_fee`；(4) `score_etf()` 需要多日行情但管道只提供单日数据。

**修复**：

ETF 引擎 (`web_app/etf/etf_engine.py`)：
- 筛选逻辑修正：`name` 含 "ETF" 或 `invest_type` 为"被动指数型"；跳过 REITs/货币市场型
- 规模使用 `issue_amount` 近似
- 费率使用 `m_fee` + `c_fee`
- 新增 `fetch_multi_day_etf_daily()` — 逐日调用 `fund_daily(trade_date=xxx)` 聚合 80 个日历日（约 48 个交易日）的行情，构建 per-ETF 的 close/amount 时间序列（约 80 次 API 调用）
- `build_etf_daily_snapshot()` — 当日 `fund_daily` 无数据时降级使用多日数据
- `fetch_etf_nav()` — 参数 `trade_date` → `nav_date`

**全管道数据**：
| 阶段 | 结果 |
|---|---|
| ETF 池 | 1875 只（规模 > 1 亿） |
| 多日行情快照 | 1571 只（≥ 20 个数据点） |
| 因子计算 | 1571 / 1571 通过 |
| DB 存储 | Top 30 |
| 推荐引擎 | 15 BUY + 15 HOLD |
| 耗时 | ~23s |

**API 端点**（Blueprint: `etf_recommendation_bp`）：
- `GET /api/etf/candidates/latest` — 最新 ETF 评分排名
- `GET /api/etf/recommendations/latest` — 最新推荐（含仓位分配）
- `GET /api/etf/recommendations/history?date=` — 历史推荐查询
- `POST /api/etf/recommendations/generate` — 手动触发筛选+推荐

**前端**：
- 独立页面 `/etf_overview`：统计卡片、ETF 评分排名表格、因子权重配置面板
- 主页嵌入标签页"指数推荐"：导航按钮 + `etf-page` 容器 + 同名 JS 函数
- 调度器集成：交易日 15:40 自动触发 `run_daily_etf()` + 补跑逻辑

### 3. 多维度评分系统重构

**原因**：Polars 1.40 移除了 `Series[bool_mask]` 索引语法，原有基于 `pl.Series` 布尔索引的百分位归一化代码不可用。

**改动**：
- `vnpy/alpha/factors/scoring.py` — 完全重写：所有 `_score_*` 函数返回 `pl.Expr` 而非 `pl.Series`
  - `_global_percentile()`, `_industry_percentile()` — 返回 `pl.Expr`，使用 `pl.Expr.rank()` 替代手动排序
  - 动态列存在性检查 — `available_cols: set[str]` 参数避免缺失季频因子时报错
  - `_industry_percentile_with_neg(factor_col)` — 资产负债率等越低越好的因子
- 新增 `vnpy/alpha/factors/industry.py` — 行业分类模块
- 清理 `vnpy/alpha/factors/flow/` — 被 `fundamental/` 完全替代

### 4. Bug 修复

- `web_app/templates/index.html` — `loadFactorSnapshot(dateStr)` 缺少 `async` 关键字导致前端 JS 运行时报错
- `web_app/templates/index.html` — `async async function` 双重关键字
- `web_app/etf/etf_engine.py` — 底部游离的重复 `except` 代码块

## 文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `scripts/backfill_close.py` | close 数据回填脚本 |
| 新增 | `scripts/backfill_factors.py` | 因子回填脚本 |
| 新增 | `vnpy/alpha/factors/scoring.py` | 多维度评分系统（Polars 1.40） |
| 新增 | `vnpy/alpha/factors/industry.py` | 行业分类 |
| 修改 | `web_app/etf/etf_engine.py` | ETF 引擎重写 + 多日行情 + NAV 修复 |
| 修改 | `web_app/factor_api.py` | 动量因子 drop_nulls 修复 |
| 修改 | `web_app/scheduler_tasks.py` | ETF 调度集成 |
| 修改 | `web_app/templates/index.html` | ETF 嵌入标签 + async 修复 |
| 修改 | `vnpy/alpha/factors/fundamental/fetcher.py` | daily_basic 新增 close 列 |
| 修改 | `vnpy/alpha/factors/fundamental/factors.py` | 适配修改 |
| 修改 | `vnpy/alpha/factors/fundamental/storage.py` | 适配修改 |
| 修改 | `vnpy/alpha/factors/fusion.py` | 适配修改 |
| 修改 | `vnpy/alpha/factors/engine.py` | flow 引用清理 |
| 修改 | `vnpy/alpha/factors/tushare_config.py` | 适配修改 |
| 删除 | `vnpy/alpha/factors/flow/` | flow 模块清理 |

## 提交

`67d23aac` — 18 个文件，1244 行新增 / 664 行删除

---

### 5. 定时任务调度器重构

**问题**：定时任务已连续多日无法正常执行。根因：
1. 两个 `run_scheduler.py`（根目录 + `web_app/`）使用不同 PID 文件，单实例保护失效，每个 cron job 执行两次
2. `web_app/run_scheduler.py` 的补跑逻辑有时间门控 `now.hour >= 15`，若进程在 15:30 前启动则跳过补跑
3. launchd `KeepAlive` 持续复活旧进程，导致进程泄漏

**修复**：
- 删除 `web_app/run_scheduler.py`，统一到根目录 `run_scheduler.py` 作为唯一入口
- `run_scheduler.py` 完全重写：合并两个版本优点，统一 PID 文件 `.scheduler.pid`
- `web_app/scheduler_tasks.py`：
  - `init_scheduler()` — 用 `scheduler.running` 判重，移除 `_scheduler_initialized` 全局标志
  - 新增 `run_startup_catch_up()` — 无时间门控补跑，仅检查数据是否存在 + 是否交易日
  - 补跑顺序：候选股筛选 → 因子更新 → 组合推荐 → ETF 推荐
- 清理 launchd 残余：卸载并删除 `com.vnpy.scheduler.plist`
- 停止旧进程：kill 50897, 50093, 89780

**CLI 使用**：
```bash
python run_scheduler.py                  # 前台运行
python run_scheduler.py --daemon         # 后台守护进程
python run_scheduler.py --status         # 检查状态
python run_scheduler.py --stop           # 停止
python run_scheduler.py --run-today-at 16:30  # 指定今日执行时间
```

**文件变更**：`run_scheduler.py` 重写，`web_app/run_scheduler.py` 删除，`web_app/scheduler_tasks.py` +129 行
