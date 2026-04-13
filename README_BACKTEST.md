# vn.py 最小闭环回测系统

基于 vn.py 4.3.0 的量化策略回测最小闭环系统。

## 📊 功能概览

✅ **数据管理**
- 支持 Tushare 真实数据下载（`scripts/download_data.py`）
- 支持模拟数据生成（`scripts/generate_mock_data.py`）
- AlphaLab 数据管理（Parquet 格式）

✅ **策略实现**
- 双均线策略（Dual Moving Average）
- 可自定义均线周期
- 金叉买入、死叉卖出逻辑

✅ **回测引擎**
- 基于 BacktestingEngine 的完整回测流程
- 绩效统计计算
- 图表展示

✅ **结果输出**
- 统计指标（收益率、夏普比率、最大回撤等）
- 成交记录详细日志
- 结果文件保存

## 🚀 快速开始

### 1. 环境激活

```bash
cd /Users/w4sh8899/project/vnpy
source venv/bin/activate
```

### 2. 生成模拟数据（快速测试）

```bash
python scripts/generate_mock_data.py
```

输出：
```
生成 IF.CFFEX 数据...
  ✓ IF.CFFEX: 522 条数据
生成 IH.CFFEX 数据...
  ✓ IH.CFFEX: 522 条数据
生成 IC.CFFEX 数据...
  ✓ IC.CFFEX: 522 条数据
```

### 3. 运行回测

```bash
python scripts/run_backtest.py
```

输出：
```
回测配置：
  合约：['IF.CFFEX', 'IH.CFFEX', 'IC.CFFEX']
  时间：2024-04-13 - 2024-12-31
  快线：5 日
  慢线：20 日
  初始资金：1,000,000

关键绩效指标
总收益率：-30.92%
年化收益：-39.69%
最大回撤：-36.02%
夏普比率：-1.88
```

## 📁 项目结构

```
vnpy/
├── scripts/                    # 可执行脚本
│   ├── download_data.py       # Tushare 数据下载
│   ├── generate_mock_data.py   # 模拟数据生成
│   ├── dual_ma_strategy.py    # 双均线策略
│   └── run_backtest.py        # 回测主程序
│
├── lab_data/                   # AlphaLab 数据目录
│   ├── daily/                  # 日线数据（Parquet）
│   │   ├── IF.CFFEX.parquet
│   │   ├── IH.CFFEX.parquet
│   │   └── IC.CFFEX.parquet
│   └── contract.json           # 合约配置
│
├── output/                     # 输出目录
│   ├── logs/                   # 日志文件
│   └── results/                # 结果数据
└── venv/                       # Python 虚拟环境
```

## 🛠️ 脚本说明

### 1. download_data.py
从 Tushare 下载真实的股指期货数据。

**特性**：
- 支持 IF/IH/IC 三大股指期货
- 自动配置合约参数（乘数、手续费等）
- 防爬策略（35秒延迟，避免频率限制）
- 自动合并多个合约数据

**使用**：
```python
from scripts.download_data import TushareDataDownloader

downloader = TushareDataDownloader("/path/to/lab_data")
downloader.download_daily_data("20200101", "20251231", symbols=["IF", "IH"])
```

**注意**：Tushare 免费账号有频率限制（每分钟2次），下载5年数据需要 1-2 小时。

### 2. generate_mock_data.py
生成模拟的股指期货数据，用于快速验证回测流程。

**特性**：
- 2年历史数据
- 3个品种（IF/IH/IC）
- 不同的趋势特征
- 自动保存为 Parquet 格式

**使用**：
```python
from scripts.generate_mock_data import generate_mock_data
generate_mock_data("IF.CFFEX", start_date, end_date, 3000.0, 0.0005, 0.02)
```

### 3. dual_ma_strategy.py
双均线策略实现。

**参数**：
- `fast_window`: 快线周期（默认 5）
- `slow_window`: 慢线周期（默认 20）
- `position_pct`: 仓位比例（默认 0.95）

**逻辑**：
- 快线上穿慢线 → 买入
- 快线下穿慢线 → 卖出

### 4. run_backtest.py
回测主程序。

**参数**：
- `vt_symbols`: 交易品种列表
- `start`: 回测开始日期
- `end`: 回测结束日期
- `capital`: 初始资金（默认 1,000,000）
- `fast_window`: 快线周期
- `slow_window`: 慢线周期

## 📊 回测结果解读

### 关键指标

- **总收益率**: 整体盈亏百分比
- **年化收益**: 年化收益率
- **最大回撤**: 最大亏损百分比
- **夏普比率**: 风险调整后收益（>1 为佳）
- **收益回撤比**: 收益/回撤比（>1 为佳）

### 输出文件

- `output/backtest_stats_*.txt`: 详细统计指标
- Plotly 图表（自动弹出浏览器）

## 🔧 自定义开发

### 修改策略参数

编辑 `scripts/dual_ma_strategy.py`：

```python
class DualMaStrategy(AlphaStrategy):
    fast_window: int = 10    # 修改快线周期
    slow_window: int = 30   # 修改慢线周期
```

### 创建新策略

1. 继承 `AlphaStrategy`
2. 实现 `on_init()`, `on_bars()`, `on_trade()` 方法
3. 在 `run_backtest.py` 中替换策略类

### 使用真实数据

```bash
# 1. 下载数据（需要 1-2 小时）
python scripts/download_data.py

# 2. 验证数据
source venv/bin/activate
python -c "from vnpy.alpha import AlphaLab; lab = AlphaLab('lab_data'); bars = lab.load_bar_data('IF.CFFEX', 'd', '2020-01-01', '2025-01-01'); print(f'{len(bars)} 条')"

# 3. 修改 run_backtest.py 中的时间范围
start = datetime(2020, 4, 13)
end = datetime(2025, 4, 13)
```

## ⚠️ 注意事项

1. **虚拟环境**: 必须激活 venv 虚拟环境才能运行
2. **Python 版本**: 需要 Python 3.10+
3. **数据格式**: 必须使用 CFFEX 作为交易所代码
4. **Tushare 限制**: 免费账号有严格的频率限制

## 📈 性能优化建议

1. **参数优化**: 尝试不同的均线周期组合
2. **多品种组合**: 扩展到更多交易品种
3. **风控模块**: 添加止损止盈逻辑
4. **资金管理**: 优化仓位分配策略

## 📚 参考文档

- vn.py 官方文档: https://www.vnpy.com/docs
- Alpha 策略开发: vnpy/alpha/strategy/
- 回测引擎: vnpy/alpha/strategy/backtesting.py

---

**创建日期**: 2026-04-13
**vn.py 版本**: 4.3.0
**Python 版本**: 3.14.3
