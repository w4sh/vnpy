# 前瞻性因子指标系统 — 设计方案

> 日期：2026-04-27
> 状态：设计已确认，待生成实施计划

## 目标

在 vnpy 量化交易框架中加入三类前瞻性指标，弥补现有 Alpha 模块纯粹依赖价格/量价因子的问题，支持对未来做更高置信度的预期：

1. **基本面因子**（第一期）— 营收增速、PE/PB、ROE 等估值和盈利能力维度
2. **资金流向**（第二期）— 主力净流入/北向资金动向
3. **市场情绪**（第三期）— 涨停数、换手率异常等

## 决策总结

| 决策项 | 选择 |
|--------|------|
| 集成方式 | Alpha 模块构建因子供 ML 使用 + web_app 可视化展示 |
| 频率策略 | 季频/日频保持各自自然频率，策略层做信号融合 |
| 覆盖范围 | 先对齐现有 250 只股票池，架构预留全 A 股扩展 |
| 建设顺序 | 基本面（第一期） → 资金流向（第二期） → 市场情绪（第三期） |
| 权重策略 | 等权起步，所有权重暴露为策略 Setting 参数，后续可走 IC 加权 |

## 一、新增包结构

```
vnpy/alpha/factors/                    # 新增：独立因子引擎包
├── __init__.py                        # 导出 FactorEngine, SignalFusion
├── engine.py                          # FactorEngine: 总调度器
├── base.py                            # 抽象基类
├── fundamental/                       # [第一期] 基本面因子
│   ├── __init__.py
│   ├── fetcher.py                     # Tushare 数据拉取
│   ├── factors.py                     # 因子计算
│   └── storage.py                     # Parquet 持久化
├── flow/                              # [第二期，占位] 资金流向因子
│   ├── __init__.py
│   ├── fetcher.py
│   ├── factors.py
│   └── storage.py
├── sentiment/                         # [第三期，占位] 市场情绪因子
│   ├── __init__.py
│   ├── fetcher.py
│   ├── factors.py
│   └── storage.py
└── fusion.py                          # 多频信号融合层

web_app/                               # Web 端展示（现有 + 新增）
├── factor_api.py                      # [新增] 因子数据 API（3 个端点）
└── templates/index.html               # [修改] 新增「前瞻指标」标签页
```

## 二、核心设计原则

1. **自然频率隔离**：基本面 = 季频因子表，资金流/情绪 = 日频因子表，互不污染
2. **报告期 vs 可用日**：基本面数据存储时保留 `report_date`（报告期）和 `pub_date`（实际公告日），因子计算用 `pub_date` 避免未来数据
3. **因子 → Alpha 管线**：通过 `get_factor_matrix()` 输出宽表 DataFrame，注入 AlphaDataset
4. **因子 → Web 展示**：通过 `get_latest_snapshot()` 供 Flask API 查询最新快照

## 三、Tushare 数据来源

### 第一期 — 基本面因子 4 条数据线

| 接口 | 内容 | 频率 | 关键字段 |
|------|------|------|----------|
| `income` | 利润表 | 季频 | revenue, n_income, total_cogs, operate_profit |
| `fina_indicator` | 财务指标 | 季频 | roe, roa, grossprofit_margin, netprofit_margin, debt_to_assets |
| `daily_basic` | 每日估值指标 | 日频 | pe, pe_ttm, pb, ps, ps_ttm, total_mv, circ_mv |
| `disclosure_date` | 财报实际公告日 | 按公告 | pre_date, actual_date |

### 第一期 7 个基本面因子

| 因子名 | 公式 | 频率 | 类型 |
|--------|------|------|------|
| `revenue_yoy_growth` | (本期营收 - 去年同期营收) / abs(去年同期营收) | 季频 | 增长 |
| `net_profit_yoy_growth` | (本期净利 - 去年同期净利) / abs(去年同期净利) | 季频 | 增长 |
| `roe` | ROE（净资产收益率） | 季频 | 盈利 |
| `gross_margin` | 毛利率 | 季频 | 盈利 |
| `pe_ttm` | 市盈率 TTM | 日频 | 估值 |
| `pb` | 市净率 | 日频 | 估值 |
| `ps_ttm` | 市销率 TTM | 日频 | 估值 |
| `debt_to_assets` | 资产负债率 | 季频 | 风险 |

## 四、因子引擎架构

### 4.1 抽象基类（`base.py`）

```python
class DataFetcher(ABC):
    """从 Tushare 获取原始数据"""
    def fetch(self, symbols: list[str], date: datetime) -> pl.DataFrame: ...

class FactorComputer(ABC):
    """从原始数据计算因子值，返回长表"""
    def compute(self, raw_df: pl.DataFrame) -> pl.DataFrame: ...

class FactorStorage(ABC):
    """Parquet 读写"""
    def save(self, factors: pl.DataFrame) -> None: ...
    def load(self, symbols, start, end) -> pl.DataFrame: ...
    def get_latest(self, symbols) -> pl.DataFrame: ...
```

### 4.2 FactorEngine（`engine.py`）

```python
class FactorEngine:
    """因子引擎总调度器"""
    def register(name, fetcher, computer, storage): ...
    def run_daily(symbols, date) -> dict: ...
    def run_quarterly(symbols, season_end) -> dict: ...
    def get_factor_matrix(symbols, start, end, factor_names) -> pl.DataFrame: ...
    def get_latest_snapshot(symbols) -> pl.DataFrame: ...
```

注册模式：每个维度独立注册自己的完整管线，引擎按序调度。

### 4.3 拉取调度策略

防止过度调用 Tushare API：

- **日频数据**（`daily_basic`）：全市场批量拉取，过滤后 1 次调用
- **季频数据**（income/fina_indicator）：仅财报旺季窗口拉取（4/30, 8/31, 10/31, 次年 4/30 前后 5 个交易日），平时跳过
- **公告日期**（disclosure_date）：每周拉 1 次

## 五、数据存储 Schema

### 季频因子表（`fundamental_quarterly.parquet`）

```
report_date | pub_date   | vt_symbol  | factor_name           | factor_value
2024-03-31  | 2024-04-25 | 600036.SSE | revenue_yoy_growth    | 0.085
```

### 日频因子表（`fundamental_daily.parquet`）

```
trade_date  | vt_symbol   | pe_ttm | pb    | ps_ttm | total_mv
2024-10-25  | 600036.SSE  | 6.23   | 0.85  | 1.82   | 8.45e11
```

## 六、信号融合层（`fusion.py`）

### 两层聚合架构

```
层1: 单维度内评分 → 层2: 跨维度加权融合 → final_score
```

### 层1 — DimensionScorer

对每个维度内部的因子值做**截面排名标准化**到 0-100：

```
rank_pct = (rank_in_cross_section / total_stocks) * 100
dimension_score = Σ(rank_pct_i * weight_i)
```

第一期基本面维度：8 个因子等权（各 0.125），输出 `fundamental_score`。

### 层2 — SignalFusion

跨维度等权融合（第一期为 1 维度，后续调整）：

| 建设阶段 | technical | fundamental | flow | sentiment |
|----------|-----------|-------------|------|-----------|
| 第一期 | 等权（随策略 setting 调） | 等权 | — | — |
| 第二期 | 可配 | 可配 | 可配 | — |
| 第三期 | 可配 | 可配 | 可配 | 可配 |

### 前值填充策略（无未来数据）

- 季频评分在 `pub_date` 当天开始生效
- 至下一个 `pub_date` 之前保持不变
- 某交易日若股票尚无财报公告，评分为 NaN（不参与当日排名）

### 在 AlphaStrategy 中的整合

```python
class MultiDimensionStrategy(AlphaStrategy):
    def on_bars(self, bars):
        tech_signal = self.get_signal()
        fund_signal = self.factor_engine.get_snapshot_asof(today)
        final = self.fusion.fuse(today, symbols, tech_signal, fund_signal)
        # 按 final_score 排序，取 top N 设目标仓位
```

### 可解释性输出

每只股票的融合结果附带 `detail_json`，记录各维度评分和贡献：

```json
{
  "symbol": "600036.SSE", "date": "2024-10-25", "final_score": 72.5,
  "dimensions": {
    "technical": {"score": 65, "weight": 0.5, "contribution": 32.5},
    "fundamental": {"score": 68, "weight": 0.5, "contribution": 34.0}
  }
}
```

## 七、Web 展示层

### 导航位置

在 `index.html` 页面导航中新增「前瞻指标」标签，位列「股票候选」之后。

### API 端点（`/api/factors`）

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/api/factors/snapshot?date=YYYY-MM-DD` | 指定交易日全部股票因子快照，支持排序 |
| GET | `/api/factors/history?symbol=600036.SSE&days=60` | 单只股票因子评分历史序列 |
| GET | `/api/factors/detail?symbol=600036.SSE&date=YYYY-MM-DD` | 单只股票维度贡献分解 |

### 4 个可视化组件

1. **因子综合排名表**：Top 20 股票的综合评分及日环比变化
2. **维度贡献分解图**（堆叠柱状图，Chart.js）：点击股票后展示各维度贡献占比
3. **因子历史曲线**（折线图，Chart.js）：单只股票各因子评分 + 综合评分的时间序列
4. **跨模块联动**：排名前 5 自动关联到候选股模块，支持一键加入持仓

### 与现有模块的交互

| 现有模块 | 交互方式 |
|----------|----------|
| `candidate/screening` | 前瞻因子评分可作为筛选新增维度 |
| `scheduler_tasks.py` | 任务链：先 `factor_engine` 更新因子 → 再 `candidate.run_screening` |
| `AlphaDataset` | `dataset.add_feature(name, result=factor_df)` 注入 |
| `AlphaStrategy` | `SignalFusion.fuse()` 在 `on_bars` 中调用 |
| 持仓管理 | 对已持有个股显示前瞻因子异常告警 |

## 八、第一期交付范围

| 文件 | 类型 | 说明 |
|------|------|------|
| `vnpy/alpha/factors/__init__.py` | 新增 | 导出 FactorEngine, SignalFusion |
| `vnpy/alpha/factors/base.py` | 新增 | DataFetcher, FactorComputer, FactorStorage |
| `vnpy/alpha/factors/engine.py` | 新增 | FactorEngine 调度器 |
| `vnpy/alpha/factors/fundamental/__init__.py` | 新增 | 基本面因子包入口 |
| `vnpy/alpha/factors/fundamental/fetcher.py` | 新增 | Tushare 数据拉取 |
| `vnpy/alpha/factors/fundamental/factors.py` | 新增 | 7 个基本面因子计算 |
| `vnpy/alpha/factors/fundamental/storage.py` | 新增 | Parquet 读写 + 格式转换 |
| `vnpy/alpha/factors/fusion.py` | 新增 | SignalFusion + DimensionScorer |
| `web_app/factor_api.py` | 新增 | 3 个 API 端点 |
| `web_app/templates/index.html` | 修改 | 新增前瞻指标标签页 |
| `tests/test_factors.py` | 新增 | 因子引擎单元测试 |

## 九、不做什么

- 不做实时推送/Tick 级别因子更新（日终批处理即可）
- 不做 ML 模型的自动整合（用户自行决定如何将融合信号输入模型）
- 第一期不做行业中性化处理（后续迭代加入）
- 不修改 AlphaDataset、AlphaModel 的现有接口（仅通过 add_feature 注入）
- 不做自动调参/超参搜索（权重由用户通过策略 Setting 控制）
