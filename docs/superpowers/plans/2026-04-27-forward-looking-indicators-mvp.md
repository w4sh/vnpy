# 前瞻性因子指标系统 — 第一期实施计划（基本面因子）

> **For agentic workers:** 每个任务完成后，使用 TaskUpdate 标记状态。任务间有依赖关系的不能并行执行。

**目标：** 在 vnpy/alpha/factors/ 下构建独立因子引擎，实现 7 个基本面因子的数据拉取、计算、存储，并提供信号融合层和 Web 展示。

**架构：** FactorEngine 通过注册模式调度 3 个抽象管线组件（DataFetcher / FactorComputer / FactorStorage），支持日频和季频数据独立处理，最终输出标准化因子矩阵注入 AlphaDataset，同时通过 REST API 供 Web 前端消费。

**技术栈：** Python 3.10+, Polars, Tushare Pro, Parquet, Flask Blueprint, APScheduler

---

### 预检步骤：确认依赖

先检查项目是否已有 polars 和 pyarrow 依赖。

- [ ] **Step 1: 确认 polars 依赖**

运行：
```
uv run python -c "import polars; print(polars.__version__)"
```
预期：输出版本号，例如 `1.2.0`。如果报 `ModuleNotFoundError`，运行：
```
uv pip install polars pyarrow
```

---

### 任务 1：创建目录结构

**文件：**
- 创建: `vnpy/alpha/factors/__init__.py`（空文件）
- 创建: `vnpy/alpha/factors/fundamental/__init__.py`（空文件）
- 创建: `vnpy/alpha/factors/flow/__init__.py`（空文件）
- 创建: `vnpy/alpha/factors/sentiment/__init__.py`（空文件）

- [ ] **Step 1: 创建目录结构**

```bash
mkdir -p vnpy/alpha/factors/fundamental
mkdir -p vnpy/alpha/factors/flow
mkdir -p vnpy/alpha/factors/sentiment
touch vnpy/alpha/factors/__init__.py
touch vnpy/alpha/factors/fundamental/__init__.py
touch vnpy/alpha/factors/flow/__init__.py
touch vnpy/alpha/factors/sentiment/__init__.py
```

- [ ] **Step 2: 提交**

```bash
git add vnpy/alpha/factors/ && git commit -m "feat: 创建前瞻因子引擎目录结构"
```

---

### 任务 2：实现抽象基类（`base.py`）

**文件：**
- 创建: `vnpy/alpha/factors/base.py`

- [ ] **Step 1: 写入抽象基类**

```python
"""
前瞻因子引擎抽象基类

定义数据拉取 → 因子计算 → 持久化的标准三阶段接口。
所有维度（基本面/资金流向/市场情绪）都实现这三个接口。
"""

from abc import ABC, abstractmethod
from datetime import datetime

import polars as pl


class DataFetcher(ABC):
    """数据拉取器抽象基类

    从外部数据源（如 Tushare）获取原始数据。
    """

    @abstractmethod
    def fetch(self, symbols: list[str], date: datetime) -> pl.DataFrame:
        """拉取指定交易日/报告期的原始数据"""
        ...


class FactorComputer(ABC):
    """因子计算器抽象基类

    输入原始数据，输出因子长表。
    长表格式: date_col | vt_symbol | factor_name | factor_value
    """

    @abstractmethod
    def compute(self, raw_df: pl.DataFrame) -> pl.DataFrame:
        """计算因子值，返回长表 DataFrame"""
        ...


class FactorStorage(ABC):
    """因子存储器抽象基类

    负责因子数据的 Parquet 文件读写。
    """

    @abstractmethod
    def save(self, factors: pl.DataFrame) -> None:
        """保存因子长表到 Parquet 文件"""
        ...

    @abstractmethod
    def load(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        """按日期范围和品种加载因子数据"""
        ...

    @abstractmethod
    def get_latest(self, symbols: list[str]) -> pl.DataFrame:
        """获取每个品种最新的因子快照"""
        ...
```

- [ ] **Step 2: 验证语法**

```bash
uv run python -c "from vnpy.alpha.factors.base import DataFetcher, FactorComputer, FactorStorage; print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add vnpy/alpha/factors/base.py && git commit -m "feat: 新增因子引擎抽象基类 (DataFetcher/FactorComputer/FactorStorage)"
```

---

### 任务 3：实现基本面因子存储层（`fundamental/storage.py`）

**文件：**
- 创建: `vnpy/alpha/factors/fundamental/storage.py`

- [ ] **Step 1: 写入存储层实现**

```python
"""
基本面因子 Parquet 存储层

支持：
- 季频因子表: {data_dir}/fundamental_quarterly.parquet
- 日频因子表: {data_dir}/fundamental_daily.parquet
- 宽表转换: 长表 → AlphaDataset 兼容的宽表格式
"""

import os
from datetime import datetime
from pathlib import Path

import polars as pl

from vnpy.alpha.factors.base import FactorStorage


DEFAULT_DATA_DIR = os.path.join(os.path.expanduser("~"), ".vntrader", "factors")


class FundamentalStorage(FactorStorage):
    """基本面因子 Parquet 存储"""

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.daily_path = self.data_dir / "fundamental_daily.parquet"
        self.quarterly_path = self.data_dir / "fundamental_quarterly.parquet"

    # ---- 存 ----

    def save_daily(self, factors: pl.DataFrame) -> None:
        """追加日频因子（按 trade_date + vt_symbol 去重）"""
        factors = factors.unique(subset=["trade_date", "vt_symbol"])
        if self.daily_path.exists():
            existing = pl.read_parquet(self.daily_path)
            combined = pl.concat([existing, factors]).unique(
                subset=["trade_date", "vt_symbol"]
            )
            combined.write_parquet(self.daily_path)
        else:
            factors.write_parquet(self.daily_path)

    def save_quarterly(self, factors: pl.DataFrame) -> None:
        """追加季频因子（长表格式，按 report_date + pub_date + vt_symbol + factor_name 去重）"""
        factors = factors.unique(
            subset=["report_date", "pub_date", "vt_symbol", "factor_name"]
        )
        if self.quarterly_path.exists():
            existing = pl.read_parquet(self.quarterly_path)
            combined = pl.concat([existing, factors]).unique(
                subset=["report_date", "pub_date", "vt_symbol", "factor_name"]
            )
            combined.write_parquet(self.quarterly_path)
        else:
            factors.write_parquet(self.quarterly_path)

    # ---- FactorStorage 接口 ----

    def save(self, factors: pl.DataFrame) -> None:
        """根据列名自动判断日频还是季频"""
        if "factor_name" in factors.columns:
            self.save_quarterly(factors)
        else:
            self.save_daily(factors)

    def load(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        """加载日内因子数据"""
        if not self.daily_path.exists():
            raise FileNotFoundError(f"{self.daily_path} 不存在，请先运行数据拉取")
        df = pl.read_parquet(self.daily_path)
        return df.filter(
            pl.col("vt_symbol").is_in(symbols)
            & (pl.col("trade_date") >= start)
            & (pl.col("trade_date") <= end)
        )

    def get_latest(self, symbols: list[str]) -> pl.DataFrame:
        """获取每个品种最近交易日的因子快照"""
        if not self.daily_path.exists():
            raise FileNotFoundError(f"{self.daily_path} 不存在")
        df = pl.read_parquet(self.daily_path)
        df = df.filter(pl.col("vt_symbol").is_in(symbols))
        if df.is_empty():
            return df
        latest_date = df["trade_date"].max()
        return df.filter(pl.col("trade_date") == latest_date)

    # ---- 格式转换 ----

    def to_wide_format(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        """将日频数据转为 AlphaDataset 兼容的宽表

        宽表格式: datetime | vt_symbol | pe_ttm | pb | ps_ttm

        注意: AlphaDataset 的 add_feature(result=df) 要求 df 有
        ["datetime", "vt_symbol", "data"] 三列，"data" 会被 rename 为因子名。
        所以这里不做 pivot，而是上层逐列注入。
        """
        return self.load(symbols, start, end)

    def load_quarterly_long(self) -> pl.DataFrame:
        """加载季频因子长表"""
        if not self.quarterly_path.exists():
            raise FileNotFoundError(f"{self.quarterly_path} 不存在")
        return pl.read_parquet(self.quarterly_path)
```

- [ ] **Step 2: 验证语法**

```bash
uv run python -c "from vnpy.alpha.factors.fundamental.storage import FundamentalStorage; print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add vnpy/alpha/factors/fundamental/storage.py && git commit -m "feat: 新增基本面因子 Parquet 存储层"
```

---

### 任务 4：实现 Tushare 数据拉取器（`fundamental/fetcher.py`）

**文件：**
- 创建: `vnpy/alpha/factors/fundamental/fetcher.py`

- [ ] **Step 1: 写入数据拉取器**

```python
"""
基本面因子 Tushare 数据拉取器

拉取四类数据:
- income: 利润表（逐只拉取）
- fina_indicator: 财务指标（逐只拉取）
- daily_basic: 每日估值指标（批量拉取）
- disclosure_date: 财报实际公告日
"""

import logging
import os
import time
from datetime import datetime

import numpy as np
import polars as pl

from vnpy.alpha.factors.base import DataFetcher

logger = logging.getLogger(__name__)


def _to_tushare_code(symbol: str) -> str:
    """vnpy 格式 (000001.SZSE) → tushare 格式 (000001.SZ)"""
    code, exchange = symbol.split(".")
    suffix = "SH" if exchange == "SSE" else "SZ"
    return f"{code}.{suffix}"


def _to_vnpy_code(ts_code: str) -> str:
    """tushare 格式 (000001.SZ) → vnpy 格式 (000001.SZSE)"""
    code, suffix = ts_code.split(".")
    exchange = "SSE" if suffix == "SH" else "SZSE"
    return f"{code}.{exchange}"


def get_pro_api():
    """获取 Tushare Pro API 实例"""
    import tushare as ts

    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 环境变量未设置")
    ts.set_token(token)
    return ts.pro_api()


class FundamentalFetcher(DataFetcher):
    """基本面数据拉取器"""

    def __init__(self):
        self.pro = get_pro_api()

    def fetch(self, symbols: list[str], date: datetime) -> pl.DataFrame:
        """统一拉取入口，返回原始数据 DataFrame"""
        raise NotImplementedError("请调用具体的 fetch 方法: fetch_daily / fetch_quarterly")

    # ---- 日频估值数据 ----

    def fetch_daily_basic(self, trade_date: str) -> pl.DataFrame:
        """批量拉取全市场日频估值数据

        参数:
            trade_date: '20241025' 格式
        返回:
            列: trade_date, ts_code, pe, pe_ttm, pb, ps, ps_ttm, total_mv, circ_mv, turnover_rate
        """
        try:
            raw = self.pro.daily_basic(trade_date=trade_date)
        except Exception as e:
            logger.warning(f"拉取 daily_basic(trade_date={trade_date}) 失败: {e}")
            return pl.DataFrame()

        if raw is None or len(raw) == 0:
            return pl.DataFrame()

        df = pl.from_pandas(raw)
        # 只保留需要的列
        keep_cols = [
            "trade_date", "ts_code", "pe", "pe_ttm", "pb",
            "ps", "ps_ttm", "total_mv", "circ_mv", "turnover_rate",
        ]
        existing = [c for c in keep_cols if c in df.columns]
        df = df.select(existing)

        df = df.with_columns(
            pl.col("trade_date").cast(pl.Utf8),
            pl.col("ts_code").cast(pl.Utf8),
        )
        return df

    # ---- 季频财务数据 ----

    def fetch_income(self, ts_code: str, start_date: str = "20180101") -> pl.DataFrame:
        """逐只拉取利润表

        返回:
            列: end_date, ts_code, revenue, n_income, total_cogs, operate_profit
        """
        try:
            raw = self.pro.income(
                ts_code=ts_code,
                start_date=start_date,
                fields="end_date,ts_code,revenue,n_income,total_cogs,operate_profit",
            )
            time.sleep(0.3)  # 频率控制
        except Exception as e:
            logger.warning(f"拉取 income({ts_code}) 失败: {e}")
            return pl.DataFrame()

        if raw is None or len(raw) == 0:
            return pl.DataFrame()

        df = pl.from_pandas(raw)
        cast_map = {}
        for col in ["revenue", "n_income", "total_cogs", "operate_profit"]:
            if col in df.columns:
                cast_map[col] = pl.col(col).cast(pl.Float64, strict=False)
        df = df.with_columns(
            pl.col("end_date").cast(pl.Utf8),
            pl.col("ts_code").cast(pl.Utf8),
            **cast_map,
        )
        return df

    def fetch_fina_indicator(
        self, ts_code: str, start_date: str = "20180101"
    ) -> pl.DataFrame:
        """逐只拉取财务指标

        返回:
            列: end_date, ts_code, roe, roa, grossprofit_margin,
                netprofit_margin, debt_to_assets
        """
        try:
            raw = self.pro.fina_indicator(
                ts_code=ts_code,
                start_date=start_date,
                fields="end_date,ts_code,roe,roa,grossprofit_margin,netprofit_margin,debt_to_assets",
            )
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"拉取 fina_indicator({ts_code}) 失败: {e}")
            return pl.DataFrame()

        if raw is None or len(raw) == 0:
            return pl.DataFrame()

        df = pl.from_pandas(raw)
        numeric_cols = [
            "roe", "roa", "grossprofit_margin",
            "netprofit_margin", "debt_to_assets",
        ]
        cast_map = {}
        for col in numeric_cols:
            if col in df.columns:
                cast_map[col] = pl.col(col).cast(pl.Float64, strict=False)
        df = df.with_columns(
            pl.col("end_date").cast(pl.Utf8),
            pl.col("ts_code").cast(pl.Utf8),
            **cast_map,
        )
        return df

    def fetch_disclosure_dates(self, ts_code: str) -> pl.DataFrame:
        """拉取财报披露日期（预计 + 实际公告日）

        返回:
            列: ts_code, end_date, pre_date, actual_date
        """
        try:
            raw = self.pro.disclosure_date(
                ts_code=ts_code,
                fields="ts_code,end_date,pre_date,actual_date",
            )
            time.sleep(0.2)
        except Exception as e:
            logger.warning(f"拉取 disclosure_date({ts_code}) 失败: {e}")
            return pl.DataFrame()

        if raw is None or len(raw) == 0:
            return pl.DataFrame()

        df = pl.from_pandas(raw)
        return df.with_columns(
            pl.col("end_date").cast(pl.Utf8),
            pl.col("ts_code").cast(pl.Utf8),
            pl.col("pre_date").cast(pl.Utf8),
            pl.col("actual_date").cast(pl.Utf8),
        )

    # ---- 财报旺季判断 ----

    @staticmethod
    def is_earnings_window(today: datetime, window_days: int = 5) -> bool:
        """判断今天是否在财报公告旺季窗口内

        旺季窗口: 4/30, 8/31, 10/31, 次年 4/30 前后 ±window_days 个自然日
        """
        earnings_deadlines = [
            datetime(today.year, 4, 30),
            datetime(today.year, 8, 31),
            datetime(today.year, 10, 31),
            datetime(today.year + 1, 4, 30),
        ]
        for deadline in earnings_deadlines:
            if abs((today - deadline).days) <= window_days:
                return True
        return False
```

- [ ] **Step 2: 验证语法**

```bash
uv run python -c "from vnpy.alpha.factors.fundamental.fetcher import FundamentalFetcher; print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add vnpy/alpha/factors/fundamental/fetcher.py && git commit -m "feat: 新增基本面 Tushare 数据拉取器"
```

---

### 任务 5：实现因子计算器（`fundamental/factors.py`）

**文件：**
- 创建: `vnpy/alpha/factors/fundamental/factors.py`

- [ ] **Step 1: 写入因子计算器**

```python
"""
基本面因子计算器

从拉取的 Tushare 原始数据中计算 7 个基本面因子:
  - 季频 (长表格式): revenue_yoy_growth, net_profit_yoy_growth, roe, gross_margin, debt_to_assets
  - 日频 (宽表格式): pe_ttm, pb, ps_ttm

季频因子输出格式:
    report_date | pub_date  | vt_symbol  | factor_name          | factor_value
日频因子输出格式:
    trade_date  | vt_symbol | pe_ttm  | pb     | ps_ttm
"""

import logging
from datetime import datetime

import numpy as np
import polars as pl

from vnpy.alpha.factors.base import FactorComputer
from vnpy.alpha.factors.fundamental.fetcher import _to_vnpy_code

logger = logging.getLogger(__name__)

# 季频因子列表
QUARTERLY_FACTORS = [
    "revenue_yoy_growth",
    "net_profit_yoy_growth",
    "roe",
    "gross_margin",
    "debt_to_assets",
]


class FundamentalComputer(FactorComputer):
    """基本面因子计算器"""

    def compute(self, raw_df: pl.DataFrame) -> pl.DataFrame:
        """统一入口，根据输入数据类型分发"""
        raise NotImplementedError("请调用 compute_quarterly() 或 compute_daily()")

    def compute_daily(self, daily_basic_df: pl.DataFrame) -> pl.DataFrame:
        """从 daily_basic 数据计算日频因子

        输入: trade_date, ts_code, pe_ttm, pb, ps_ttm, ...
        输出: trade_date, vt_symbol, pe_ttm, pb, ps_ttm
        """
        if daily_basic_df.is_empty():
            return pl.DataFrame()

        df = daily_basic_df.with_columns(
            pl.col("ts_code").map_elements(
                _to_vnpy_code, return_dtype=pl.Utf8
            ).alias("vt_symbol"),
        )

        # 只保留需要的因子列
        keep_cols = ["trade_date", "vt_symbol", "pe_ttm", "pb", "ps_ttm"]
        existing = [c for c in keep_cols if c in df.columns]
        df = df.select(existing)

        # 将估值倒数化（高估值 = 低得分），因子值为正指标
        for col in ["pe_ttm", "pb", "ps_ttm"]:
            if col in df.columns:
                df = df.with_columns(
                    pl.when(pl.col(col) > 0)
                    .then(1.0 / pl.col(col))
                    .otherwise(pl.lit(None))
                    .alias(col)
                )

        df = df.with_columns(
            pl.col("trade_date").cast(pl.Utf8),
            pl.col("vt_symbol").cast(pl.Utf8),
        )

        for col in ["pe_ttm", "pb", "ps_ttm"]:
            if col in df.columns:
                df = df.with_columns(pl.col(col).cast(pl.Float64))

        return df

    def compute_quarterly(
        self,
        income_df: pl.DataFrame,
        fina_df: pl.DataFrame,
        disclosure_df: pl.DataFrame,
    ) -> pl.DataFrame:
        """计算季频因子，输出长表

        输入: 利润表、财务指标、公告日期三张表（单只股票的）
        输出: report_date | pub_date | vt_symbol | factor_name | factor_value
        """
        if income_df.is_empty() or fina_df.is_empty():
            return pl.DataFrame()

        # 将 ts_code 统一为 vnpy 格式
        for frame in [income_df, fina_df, disclosure_df]:
            if "vt_symbol" not in frame.columns and "ts_code" in frame.columns:
                frame = frame.with_columns(
                    pl.col("ts_code").map_elements(
                        _to_vnpy_code, return_dtype=pl.Utf8
                    ).alias("vt_symbol")
                )

        vt_symbol = income_df["vt_symbol"][0]

        # ---- 构建公告日期映射 ----
        if not disclosure_df.is_empty():
            pub_dates = {}
            for row in disclosure_df.iter_rows(named=True):
                end = row.get("end_date", "")
                actual = row.get("actual_date", "")
                pre = row.get("pre_date", "")
                pub = actual if actual and actual != "nan" else pre
                if end and pub and pub != "nan":
                    pub_dates[str(end)] = str(pub)
        else:
            pub_dates = {}

        # ---- 利润表因子 ----
        income_sorted = income_df.sort("end_date")
        income_dict = {str(r["end_date"]): r for r in income_sorted.iter_rows(named=True)}

        rows = []

        for end_date_str, row in income_dict.items():
            # 计算去年同期日期
            try:
                end_dt = datetime.strptime(end_date_str, "%Y%m%d")
                prev_year = str(end_dt.year - 1) + end_date_str[4:]
            except ValueError:
                continue

            pub_date_str = pub_dates.get(end_date_str, end_date_str)
            rev = self._safe_float(row.get("revenue"))
            net = self._safe_float(row.get("n_income"))

            # 营收同比增速
            if prev_year in income_dict:
                prev_rev = self._safe_float(income_dict[prev_year].get("revenue"))
                prev_net = self._safe_float(income_dict[prev_year].get("n_income"))
                if prev_rev and prev_rev != 0:
                    rows.append((
                        end_date_str,
                        pub_date_str,
                        vt_symbol,
                        "revenue_yoy_growth",
                        round(rev / abs(prev_rev) - 1, 6),
                    ))
                if prev_net and prev_net != 0:
                    rows.append((
                        end_date_str,
                        pub_date_str,
                        vt_symbol,
                        "net_profit_yoy_growth",
                        round(net / abs(prev_net) - 1, 6),
                    ))

        # ---- 财务指标因子 ----
        fina_sorted = fina_df.sort("end_date")
        for row in fina_sorted.iter_rows(named=True):
            end_date_str = str(row["end_date"])
            pub_date_str = pub_dates.get(end_date_str, end_date_str)

            # ROE
            roe_val = self._safe_float(row.get("roe"))
            if roe_val is not None:
                rows.append((end_date_str, pub_date_str, vt_symbol, "roe", round(roe_val, 6)))

            # 毛利率
            gm_val = self._safe_float(row.get("grossprofit_margin"))
            if gm_val is not None:
                rows.append((end_date_str, pub_date_str, vt_symbol, "gross_margin", round(gm_val, 6)))

            # 资产负债率
            debt_val = self._safe_float(row.get("debt_to_assets"))
            if debt_val is not None:
                rows.append((end_date_str, pub_date_str, vt_symbol, "debt_to_assets", round(debt_val, 6)))

        if not rows:
            return pl.DataFrame()

        return pl.DataFrame(
            rows,
            schema=["report_date", "pub_date", "vt_symbol", "factor_name", "factor_value"],
            orient="row",
        )

    @staticmethod
    def _safe_float(val: any) -> float | None:
        """安全转换浮点数，处理 nan/inf"""
        if val is None:
            return None
        try:
            f = float(val)
            if np.isnan(f) or np.isinf(f):
                return None
            return f
        except (ValueError, TypeError):
            return None
```

- [ ] **Step 2: 验证语法**

```bash
uv run python -c "from vnpy.alpha.factors.fundamental.factors import FundamentalComputer; print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add vnpy/alpha/factors/fundamental/factors.py && git commit -m "feat: 新增基本面因子计算器（7个因子）"
```

---

### 任务 6：更新 `__init__.py` 导出

**文件：**
- 修改: `vnpy/alpha/factors/fundamental/__init__.py`

- [ ] **Step 1: 写入包导出**

```python
"""基本面因子模块"""

from vnpy.alpha.factors.fundamental.fetcher import FundamentalFetcher
from vnpy.alpha.factors.fundamental.factors import FundamentalComputer, QUARTERLY_FACTORS
from vnpy.alpha.factors.fundamental.storage import FundamentalStorage

__all__ = [
    "FundamentalFetcher",
    "FundamentalComputer",
    "FundamentalStorage",
    "QUARTERLY_FACTORS",
]
```

- [ ] **Step 2: 验证**

```bash
uv run python -c "from vnpy.alpha.factors.fundamental import FundamentalFetcher, FundamentalComputer, FundamentalStorage; print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add vnpy/alpha/factors/fundamental/__init__.py && git commit -m "feat: 更新基本面因子模块导出"
```

---

### 任务 7：实现 FactorEngine 调度器（`engine.py`）

**文件：**
- 创建: `vnpy/alpha/factors/engine.py`

- [ ] **Step 1: 写入调度器**

```python
"""
因子引擎总调度器

通过注册模式管理多个因子维度的完整管线。
支持日终调度和财报季调度。
"""

import logging
from datetime import datetime

import polars as pl

from vnpy.alpha.factors.base import DataFetcher, FactorComputer, FactorStorage

logger = logging.getLogger(__name__)


class FactorPipeline:
    """单个维度的因子计算管线"""

    def __init__(
        self,
        name: str,
        fetcher: DataFetcher,
        computer: FactorComputer,
        storage: FactorStorage,
    ):
        self.name = name
        self.fetcher = fetcher
        self.computer = computer
        self.storage = storage


class FactorEngine:
    """因子引擎总调度器"""

    def __init__(self, data_dir: str | None = None):
        if data_dir is None:
            import os
            data_dir = os.path.join(os.path.expanduser("~"), ".vntrader", "factors")
        self.data_dir = data_dir
        self.pipelines: dict[str, FactorPipeline] = {}

    def register(
        self,
        name: str,
        fetcher: DataFetcher,
        computer: FactorComputer,
        storage: FactorStorage,
    ) -> None:
        """注册一个因子维度的完整管线"""
        self.pipelines[name] = FactorPipeline(name, fetcher, computer, storage)
        logger.info(f"FactorEngine: 注册管线 '{name}'")

    def run_daily(self, symbols: list[str], trade_date: str) -> dict:
        """执行日终因子更新

        参数:
            symbols: 股票池代码列表
            trade_date: 交易日 'YYYYMMDD'
        返回:
            {pipeline_name: stats_dict}
        """
        results = {}
        for name, pipeline in self.pipelines.items():
            logger.info(f"FactorEngine: 执行管线 '{name}' 日频更新")
            try:
                stats = self._run_daily_pipeline(pipeline, symbols, trade_date)
                results[name] = stats
            except Exception as e:
                logger.error(f"管线 '{name}' 日频更新失败: {e}")
                results[name] = {"error": str(e)}
        return results

    def run_quarterly(self, symbols: list[str], end_date: str) -> dict:
        """执行季频因子更新（仅基本面维度）

        参数:
            symbols: 股票池代码列表
            end_date: 报告期截止日 'YYYYMMDD'
        """
        results = {}
        for name, pipeline in self.pipelines.items():
            logger.info(f"FactorEngine: 执行管线 '{name}' 季频更新")
            try:
                stats = self._run_quarterly_pipeline(pipeline, symbols, end_date)
                results[name] = stats
            except Exception as e:
                logger.error(f"管线 '{name}' 季频更新失败: {e}")
                results[name] = {"error": str(e)}
        return results

    # ---- 因子矩阵输出 ----

    def get_factor_matrix(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        """输出标准化的日频因子宽表，供 AlphaDataset 注入

        宽表格式: datetime | vt_symbol | 因子1 | 因子2 | ...

        AlphaDataset 用法:
          for factor_name in factor_columns:
              factor_df = matrix.select(["datetime", "vt_symbol", factor_name])
              factor_df = factor_df.rename({factor_name: "data"})
              dataset.add_feature(factor_name, result=factor_df)
        """
        frames = []
        for pipeline in self.pipelines.values():
            try:
                df = pipeline.storage.load(symbols, start, end)
                if not df.is_empty():
                    frames.append(df)
            except FileNotFoundError:
                logger.warning(f"管线 '{pipeline.name}': 数据文件不存在，跳过")
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames)

    def get_latest_snapshot(self, symbols: list[str]) -> pl.DataFrame:
        """获取最新交易日因子快照（供 Web API）"""
        frames = []
        for pipeline in self.pipelines.values():
            try:
                df = pipeline.storage.get_latest(symbols)
                if not df.is_empty():
                    frames.append(df)
            except FileNotFoundError:
                pass
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames)

    # ---- 内部方法 ----

    def _run_daily_pipeline(
        self,
        pipeline: FactorPipeline,
        symbols: list[str],
        trade_date: str,
    ) -> dict:
        """执行单个管线的日频更新"""
        # 只有基本面管线有日频逻辑（daily_basic）
        if pipeline.name == "fundamental":
            from vnpy.alpha.factors.fundamental.fetcher import FundamentalFetcher
            from vnpy.alpha.factors.fundamental.factors import FundamentalComputer

            if not isinstance(pipeline.fetcher, FundamentalFetcher):
                return {"error": "fetcher 类型不匹配"}
            if not isinstance(pipeline.computer, FundamentalComputer):
                return {"error": "computer 类型不匹配"}

            raw = pipeline.fetcher.fetch_daily_basic(trade_date)
            if raw.is_empty():
                return {"fetched": 0, "stored": 0}
            factors = pipeline.computer.compute_daily(raw)
            pipeline.storage.save_daily(factors)
            return {"fetched": len(raw), "stored": len(factors)}

        # 其他管线（二期、三期）在此扩展
        return {"skipped": True}

    def _run_quarterly_pipeline(
        self,
        pipeline: FactorPipeline,
        symbols: list[str],
        end_date: str,
    ) -> dict:
        """执行单个管线的季频更新"""
        if pipeline.name != "fundamental":
            return {"skipped": True}

        from vnpy.alpha.factors.fundamental.fetcher import FundamentalFetcher, _to_tushare_code
        from vnpy.alpha.factors.fundamental.factors import FundamentalComputer

        if not isinstance(pipeline.fetcher, FundamentalFetcher):
            return {"error": "fetcher 类型不匹配"}
        if not isinstance(pipeline.computer, FundamentalComputer):
            return {"error": "computer 类型不匹配"}

        total_computed = 0
        for symbol in symbols:
            ts_code = _to_tushare_code(symbol)
            try:
                income_raw = pipeline.fetcher.fetch_income(ts_code)
                fina_raw = pipeline.fetcher.fetch_fina_indicator(ts_code)
                disc_raw = pipeline.fetcher.fetch_disclosure_dates(ts_code)

                quarterly = pipeline.computer.compute_quarterly(
                    income_raw, fina_raw, disc_raw
                )
                if not quarterly.is_empty():
                    pipeline.storage.save_quarterly(quarterly)
                    total_computed += 1
            except Exception as e:
                logger.warning(f"季频因子计算失败 {symbol}: {e}")
                continue

        return {"symbols_updated": total_computed}
```

- [ ] **Step 2: 验证语法**

```bash
uv run python -c "from vnpy.alpha.factors.engine import FactorEngine, FactorPipeline; print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add vnpy/alpha/factors/engine.py && git commit -m "feat: 新增 FactorEngine 因子引擎调度器"
```

---

### 任务 8：更新包入口 `__init__.py`

**文件：**
- 修改: `vnpy/alpha/factors/__init__.py`

- [ ] **Step 1: 写入包导出**

```python
"""前瞻指标因子引擎"""

from vnpy.alpha.factors.engine import FactorEngine
from vnpy.alpha.factors.base import DataFetcher, FactorComputer, FactorStorage

__all__ = [
    "FactorEngine",
    "DataFetcher",
    "FactorComputer",
    "FactorStorage",
]
```

- [ ] **Step 2: 验证**

```bash
uv run python -c "from vnpy.alpha.factors import FactorEngine; print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add vnpy/alpha/factors/__init__.py && git commit -m "feat: 更新前瞻因子引擎包导出"
```

---

### 任务 9：实现信号融合层（`fusion.py`）

**文件：**
- 创建: `vnpy/alpha/factors/fusion.py`

- [ ] **Step 1: 写入融合层**

```python
"""
信号融合层

将多维度因子评分融合为单一综合评分，支持等权加权和可配置权重。
核心理念：排名标准化后等权融合，权重暴露为策略 Setting 参数。
"""

import json
import logging
from datetime import datetime
from typing import Optional

import polars as pl

logger = logging.getLogger(__name__)

# 默认权重：各维度等权
DEFAULT_WEIGHTS = {
    "technical": 0.5,
    "fundamental": 0.5,
    "flow": 0.0,
    "sentiment": 0.0,
}


class DimensionScorer:
    """单维度内因子评分器

    将原始因子值通过截面排名标准化为 0-100 分。
    """

    def score(
        self,
        factor_wide_df: pl.DataFrame,
        factor_names: list[str],
        weights: Optional[dict[str, float]] = None,
    ) -> pl.DataFrame:
        """计算维度综合评分

        参数:
            factor_wide_df: 宽表，列含 vt_symbol + 各因子值
            factor_names: 要评分的因子列名列表
            weights: 因子权重 dict，默认等权
        返回:
            vt_symbol, dimension_score 两列 DataFrame
        """
        if factor_wide_df.is_empty() or not factor_names:
            return pl.DataFrame()

        if weights is None:
            weights = {n: 1.0 / len(factor_names) for n in factor_names}

        df = factor_wide_df.clone()
        total_score = pl.lit(0.0)

        for name in factor_names:
            if name not in df.columns:
                continue
            w = weights.get(name, 0.0)
            if w == 0.0:
                continue

            # 截面排名标准化: rank / total * 100
            rank_expr = (
                pl.col(name).rank("ordinal", descending=True)
                / pl.col(name).count()
                * 100.0
            )
            norm = rank_expr.fill_nan(50.0).fill_null(50.0)
            total_score = total_score + norm * pl.lit(w)

        return df.select(["vt_symbol"]).with_columns(
            total_score.cast(pl.Float64, strict=False).alias("dimension_score")
        )


class SignalFusion:
    """策略层面的多维度信号融合器

    两层架构:
      Layer 1: DimensionScorer 计算每个维度的综合分
      Layer 2: 跨维度加权融合 → final_score
    """

    def __init__(self, weights: Optional[dict[str, float]] = None):
        """
        参数:
            weights: 维度权重，如 {"technical": 0.5, "fundamental": 0.5}
        """
        self.weights = weights or dict(DEFAULT_WEIGHTS)
        self.scorer = DimensionScorer()

    def fuse(
        self,
        date: datetime,
        symbols: list[str],
        dimension_scores: dict[str, pl.DataFrame],
    ) -> pl.DataFrame:
        """融合多维度评分

        参数:
            date: 当前日期
            symbols: 股票池
            dimension_scores: {"fundamental": df, "flow": df, ...}
                每个 df 需包含: vt_symbol, dimension_score
        返回:
            综合信号 DataFrame: vt_symbol, final_score, detail_json
        """
        if not dimension_scores or not symbols:
            return pl.DataFrame()

        # 按 vt_symbol 合并各维度评分
        all_frames = []
        for dim_name, dim_df in dimension_scores.items():
            if dim_df.is_empty():
                continue
            w = self.weights.get(dim_name, 0.0)
            if w == 0.0:
                continue
            dim_df = dim_df.select([
                pl.col("vt_symbol"),
                pl.col("dimension_score").alias(f"{dim_name}_score"),
                pl.lit(w).alias(f"{dim_name}_weight"),
            ])
            all_frames.append(dim_df)

        if not all_frames:
            return pl.DataFrame()

        merged = all_frames[0]
        for frame in all_frames[1:]:
            merged = merged.join(frame, on="vt_symbol", how="outer")

        # 计算加权总分
        total = pl.lit(0.0)
        for dim_name in dimension_scores:
            score_col = f"{dim_name}_score"
            weight_col = f"{dim_name}_weight"
            if score_col in merged.columns and weight_col in merged.columns:
                part = (
                    pl.col(score_col).fill_null(50.0)
                    * pl.col(weight_col).fill_null(0.0)
                )
                total = total + part

        merged = merged.with_columns(
            total.cast(pl.Float64, strict=False).alias("final_score")
        )

        # 构建 detail JSON 列
        detail_cols = []
        for dim_name in dimension_scores:
            sc = f"{dim_name}_score"
            wc = f"{dim_name}_weight"
            if sc in merged.columns and wc in merged.columns:
                detail_cols.extend([sc, wc])

        merged = merged.with_columns(
            pl.concat_str(
                [
                    pl.lit('{"dimensions":{'),
                    *self._build_detail_expr(dimension_scores),
                    pl.lit('},"final_score":'),
                    pl.col("final_score").round(2).cast(pl.Utf8),
                    pl.lit("}"),
                ],
                separator="",
            ).alias("detail_json")
        )

        keep_cols = ["vt_symbol", "final_score", "detail_json"]
        # 也保留中间列
        for c in detail_cols:
            keep_cols.append(c)

        result = merged.select([c for c in keep_cols if c in merged.columns])
        return result.with_columns(
            pl.lit(str(date.date())).alias("date")
        ).sort("final_score", descending=True)

    @staticmethod
    def _build_detail_expr(
        dimension_scores: dict[str, pl.DataFrame],
    ) -> list[pl.Expr]:
        """构建 detail_json 中各维度的键值对表达式"""
        exprs = []
        names = list(dimension_scores.keys())
        for i, dim_name in enumerate(names):
            sc = f"{dim_name}_score"
            wc = f"{dim_name}_weight"
            comma = "," if i < len(names) - 1 else ""
            exprs.append(
                pl.concat_str([
                    pl.lit(f'"{dim_name}":{{"score":'),
                    pl.col(sc).fill_null(0.0).round(2).cast(pl.Utf8),
                    pl.lit(',"weight":'),
                    pl.col(wc).fill_null(0.0).cast(pl.Utf8),
                    pl.lit('}')
                    + pl.lit(comma),
                ], separator=""),
            )
        return exprs

    def update_weights(self, weights: dict[str, float]) -> None:
        """动态更新权重（供回测参数调整）"""
        self.weights = dict(weights)
```

- [ ] **Step 2: 验证语法**

```bash
uv run python -c "from vnpy.alpha.factors.fusion import SignalFusion, DimensionScorer; print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add vnpy/alpha/factors/fusion.py && git commit -m "feat: 新增信号融合层 (DimensionScorer + SignalFusion)"
```

---

### 任务 10：实现 Web API（`web_app/factor_api.py`）

**文件：**
- 创建: `web_app/factor_api.py`

- [ ] **Step 1: 写入 API 端点**

```python
"""
前瞻因子 Web API

提供 3 个端点:
  GET /api/factors/snapshot       — 最新因子快照
  GET /api/factors/history        — 单只股票因子历史
  GET /api/factors/detail         — 单只股票维度贡献分解
"""

import logging
from datetime import datetime

import polars as pl
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

factor_bp = Blueprint("factors", __name__, url_prefix="/api/factors")


def get_engine():
    """延迟初始化 FactorEngine (导入 Tushare 较慢)"""
    from vnpy.alpha.factors import FactorEngine
    from vnpy.alpha.factors.fundamental import (
        FundamentalFetcher,
        FundamentalComputer,
        FundamentalStorage,
    )

    engine = FactorEngine()
    engine.register(
        "fundamental",
        FundamentalFetcher(),
        FundamentalComputer(),
        FundamentalStorage(),
    )
    return engine


def get_stock_pool():
    """从候选股模块获取股票池"""
    try:
        from web_app.candidate.screening_engine import STOCK_POOL
        return STOCK_POOL
    except ImportError:
        return []


@factor_bp.route("/snapshot")
def snapshot():
    """获取最新因子快照

    Query params:
        date: 可选，指定日期 YYYY-MM-DD，默认最新
        sort: 排序字段，默认 final_score
    """
    try:
        symbols = get_stock_pool()
        if not symbols:
            return jsonify({"error": "无可用股票池"}), 500

        engine = get_engine()
        latest = engine.get_latest_snapshot(symbols)

        # 如果没有融合层，先做基本面维度评分
        from vnpy.alpha.factors.fusion import DimensionScorer

        if not latest.is_empty():
            daily_factors = ["pe_ttm", "pb", "ps_ttm"]
            existing = [c for c in daily_factors if c in latest.columns]
            if existing:
                scorer = DimensionScorer()
                fund_score = scorer.score(latest, existing)
                # 合并
                latest = latest.join(fund_score, on="vt_symbol", how="left")
                latest = latest.with_columns(
                    pl.col("dimension_score").alias("fundamental_score")
                )
                latest = latest.with_columns(
                    pl.col("fundamental_score").alias("final_score")
                )

            # 排序
            sort_col = request.args.get("sort", "final_score")
            if sort_col in latest.columns:
                latest = latest.sort(sort_col, descending=True)

        result = latest.head(50).to_dicts()
        return jsonify({"count": len(result), "data": result})
    except Exception as e:
        logger.error(f"因子快照 API 异常: {e}")
        return jsonify({"error": str(e)}), 500


@factor_bp.route("/history")
def history():
    """获取单只股票因子历史序列

    Query params:
        symbol: 000001.SZSE
        days: 最大天数，默认 60
    """
    symbol = request.args.get("symbol", "")
    days = int(request.args.get("days", 60))

    if not symbol:
        return jsonify({"error": "缺少 symbol 参数"}), 400

    try:
        engine = get_engine()
        end = datetime.now()
        from datetime import timedelta
        start = end - timedelta(days=days)

        matrix = engine.get_factor_matrix([symbol], start, end)
        if matrix.is_empty():
            return jsonify({"count": 0, "data": [], "message": "无数据"})

        matrix = matrix.sort("trade_date")
        result = matrix.to_dicts()
        return jsonify({"count": len(result), "data": result})
    except Exception as e:
        logger.error(f"因子历史 API 异常: {e}")
        return jsonify({"error": str(e)}), 500


@factor_bp.route("/detail")
def detail():
    """获取单只股票维度贡献分解

    Query params:
        symbol: 600036.SSE
        date: YYYY-MM-DD
    """
    symbol = request.args.get("symbol", "")
    query_date = request.args.get("date", "")

    if not symbol:
        return jsonify({"error": "缺少 symbol 参数"}), 400

    try:
        engine = get_engine()
        latest = engine.get_latest_snapshot([symbol])

        if latest.is_empty() or len(latest) == 0:
            return jsonify({"message": "无数据"})

        row = latest.row(0, named=True)

        # 构建维度贡献分解
        detail = {
            "symbol": symbol,
            "date": str(row.get("trade_date", "")),
            "pe_ttm": row.get("pe_ttm"),
            "pb": row.get("pb"),
            "ps_ttm": row.get("ps_ttm"),
        }

        return jsonify({"data": detail})
    except Exception as e:
        logger.error(f"因子详情 API 异常: {e}")
        return jsonify({"error": str(e)}), 500
```

- [ ] **Step 2: 验证语法**

```bash
uv run python -c "from web_app.factor_api import factor_bp; print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add web_app/factor_api.py && git commit -m "feat: 新增前瞻因子 Web API（snapshot/history/detail）"
```

---

### 任务 11：在 `web_app/app.py` 中注册 API Blueprint

**文件：**
- 修改: `web_app/app.py`

- [ ] **Step 1: 注册 factor_bp**

找到 app.py 中注册 Blueprint 的区域（约第 48 行，在 `app.register_blueprint(position_bp)` 等之后），添加一行：

```python
# 注册前瞻因子API蓝图
from web_app.factor_api import factor_bp
app.register_blueprint(factor_bp)
```

注意：`from web_app.factor_api import factor_bp` 应添加到文件顶部的 import 区域（与其他 `from web_app.xxx import xxx_bp` 放在一起），而 `app.register_blueprint(factor_bp)` 放在其他 Blueprint 注册语句之后。

具体操作：

在文件顶部 import 区（约第 40 行后），在其他 blueprint import 之后添加：
```python
from web_app.factor_api import factor_bp
```

在 Blueprint 注册区（约第 50 行后），在其他 `app.register_blueprint` 之后添加：
```python
app.register_blueprint(factor_bp)
```

- [ ] **Step 2: 验证语法**

```bash
uv run python -c "from web_app.app import app; print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add web_app/app.py && git commit -m "feat: 在 app.py 注册前瞻因子 API Blueprint"
```

---

### 任务 12：集成定时任务（`scheduler_tasks.py`）

**文件：**
- 修改: `web_app/scheduler_tasks.py`

- [ ] **Step 1: 新增日终因子更新任务函数**

在 `scheduler_tasks.py` 文件末尾（`shutdown_scheduler` 函数之前），添加一个新的任务函数：

```python
def run_daily_factor_update():
    """日终增量更新前瞻因子（交易日 15:30 之后）"""
    try:
        from web_app.candidate.screening_engine import STOCK_POOL
        from datetime import date

        today = date.today().strftime("%Y%m%d")

        from vnpy.alpha.factors import FactorEngine
        from vnpy.alpha.factors.fundamental import (
            FundamentalFetcher,
            FundamentalComputer,
            FundamentalStorage,
        )
        from vnpy.alpha.factors.fundamental.fetcher import FundamentalFetcher as FF

        engine = FactorEngine()
        engine.register(
            "fundamental",
            FundamentalFetcher(),
            FundamentalComputer(),
            FundamentalStorage(),
        )

        # 日频估值数据更新（每次必跑）
        daily_result = engine.run_daily(STOCK_POOL, today)
        logger.info(f"日频因子更新完成: {daily_result}")

        # 季频财务数据仅在财报旺季窗口更新
        from datetime import datetime as dt
        now = dt.now()
        if FF.is_earnings_window(now):
            logger.info("进入财报旺季窗口，执行季频因子更新")
            quarterly_result = engine.run_quarterly(STOCK_POOL, today)
            logger.info(f"季频因子更新完成: {quarterly_result}")
        else:
            logger.info("非财报旺季窗口，跳过季频因子更新")

    except Exception as e:
        logger.error(f"因子更新任务失败: {e}")
```

- [ ] **Step 2: 注册新定时任务**

在 `init_scheduler()` 函数中（在第 136 行 `scheduler.start()` 之前），添加：

```python
    # 日终前瞻因子更新：交易日 15:30（在候选股筛选之前）
    scheduler.add_job(
        func=run_daily_factor_update,
        trigger=CronTrigger(day_of_week="mon-fri", hour=15, minute=35),
        id="daily_factor_update",
        name="日终前瞻因子更新",
    )
```

- [ ] **Step 3: 验证语法**

```bash
uv run python -c "from web_app.scheduler_tasks import run_daily_factor_update; print('OK')"
```

- [ ] **Step 4: 提交**

```bash
git add web_app/scheduler_tasks.py && git commit -m "feat: 集成前瞻因子日终更新定时任务"
```

---

### 任务 13：Web 前端 —「前瞻指标」标签页

**文件：**
- 修改: `web_app/templates/index.html`

在 `index.html` 中新增「前瞻指标」页面。需要添加：导航标签、页面容器 div、CSS 样式、JavaScript 逻辑。

- [ ] **Step 1: 添加导航标签**

在导航栏的 `<ul class="nav nav-tabs">` 中找到候选股标签，在其后添加：

```html
<li class="nav-item">
    <a class="nav-link" href="#" onclick="showPage('indicators')">
        前瞻指标
    </a>
</li>
```

- [ ] **Step 2: 添加页面容器**

在 `<!-- 股票候选页面 -->` div 之后添加：

```html
<!-- 前瞻指标页面 -->
<div id="indicators-page" class="page-content" style="display:none;">
    <div class="container-fluid mt-3">
        <div class="row mb-3">
            <div class="col-12">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5 class="mb-0">前瞻指标仪表盘</h5>
                        <small id="indicator-date" class="text-muted"></small>
                    </div>
                    <div class="card-body p-0">
                        <table class="table table-hover mb-0" id="indicator-table">
                            <thead>
                                <tr>
                                    <th>排名</th>
                                    <th>代码</th>
                                    <th>名称</th>
                                    <th>综合评分</th>
                                    <th>PE倒数</th>
                                    <th>PB倒数</th>
                                    <th>PS倒数</th>
                                    <th>基本面评分</th>
                                </tr>
                            </thead>
                            <tbody id="indicator-tbody"></tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <!-- 因子历史曲线 -->
        <div class="row mb-3">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">因子评分历史曲线</h5>
                    </div>
                    <div class="card-body">
                        <div class="row mb-2">
                            <div class="col-md-3">
                                <input type="text" class="form-control" id="chart-symbol"
                                       placeholder="输入股票代码，如 600036.SSE">
                            </div>
                            <div class="col-md-2">
                                <button class="btn btn-primary btn-sm" onclick="loadFactorHistory()">
                                    查询历史
                                </button>
                            </div>
                        </div>
                        <div style="height:350px;">
                            <canvas id="factor-history-chart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
```

- [ ] **Step 3: 添加 JavaScript 逻辑**

在 `index.html` 的 `<script>` 标签末尾添加：

```javascript
// ============ 前瞻指标页面 ============
let historyChart = null;

async function loadFactorSnapshot() {
    try {
        const resp = await fetch('/api/factors/snapshot');
        const data = await resp.json();
        if (!data.data) return;

        // 更新日期
        if (data.data.length > 0) {
            $('#indicator-date').text('数据日期: ' + (data.data[0].trade_date || '-'));
        }

        // 渲染表格
        const tbody = $('#indicator-tbody');
        tbody.empty();

        data.data.forEach((row, i) => {
            const pe = row.pe_ttm ? parseFloat(row.pe_ttm).toFixed(4) : '-';
            const pb = row.pb ? parseFloat(row.pb).toFixed(4) : '-';
            const ps = row.ps_ttm ? parseFloat(row.ps_ttm).toFixed(4) : '-';
            const fScore = row.fundamental_score
                ? parseFloat(row.fundamental_score).toFixed(1)
                : '-';
            const final = row.final_score
                ? parseFloat(row.final_score).toFixed(1)
                : '-';

            const scoreColor = parseFloat(final) >= 70 ? 'text-success'
                : parseFloat(final) >= 40 ? 'text-warning' : 'text-danger';

            tbody.append(`
                <tr style="cursor:pointer" onclick="$('#chart-symbol').val('${row.vt_symbol}'); loadFactorHistory();">
                    <td>${i + 1}</td>
                    <td><strong>${row.vt_symbol}</strong></td>
                    <td>-</td>
                    <td class="${scoreColor} fw-bold">${final}</td>
                    <td>${pe}</td>
                    <td>${pb}</td>
                    <td>${ps}</td>
                    <td>${fScore}</td>
                </tr>
            `);
        });
    } catch (err) {
        console.error('加载因子快照失败:', err);
    }
}

async function loadFactorHistory() {
    const symbol = $('#chart-symbol').val().trim();
    if (!symbol) {
        alert('请输入股票代码');
        return;
    }

    try {
        const resp = await fetch(`/api/factors/history?symbol=${encodeURIComponent(symbol)}&days=60`);
        const data = await resp.json();
        if (!data.data || data.data.length === 0) {
            alert('无历史数据');
            return;
        }

        const dates = data.data.map(r => r.trade_date);
        const peSeries = data.data.map(r => r.pe_ttm ? parseFloat(r.pe_ttm).toFixed(4) : null);
        const pbSeries = data.data.map(r => r.pb ? parseFloat(r.pb).toFixed(4) : null);
        const psSeries = data.data.map(r => r.ps_ttm ? parseFloat(r.ps_ttm).toFixed(4) : null);

        const ctx = document.getElementById('factor-history-chart').getContext('2d');
        if (historyChart) historyChart.destroy();

        historyChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: dates,
                datasets: [
                    {
                        label: '1/PE_TTM',
                        data: peSeries,
                        borderColor: '#4CAF50',
                        tension: 0.2,
                        spanGaps: true,
                    },
                    {
                        label: '1/PB',
                        data: pbSeries,
                        borderColor: '#2196F3',
                        tension: 0.2,
                        spanGaps: true,
                    },
                    {
                        label: '1/PS_TTM',
                        data: psSeries,
                        borderColor: '#FF9800',
                        tension: 0.2,
                        spanGaps: true,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: { display: true, text: symbol + ' 估值因子历史' },
                },
            },
        });
    } catch (err) {
        console.error('加载因子历史失败:', err);
    }
}

// 在 showPage 函数中注册 indicators 页面切换
// 找到原有的 showPage 函数，在其中添加:
const _originalShowPage = showPage;
showPage = function(pageName) {
    _originalShowPage(pageName);
    if (pageName === 'indicators') {
        loadFactorSnapshot();
        $('#indicator-date').text('');
    }
};
```

- [ ] **Step 2: 验证前端页面**

```bash
echo "已修改 index.html，请启动 Web 服务后访问 / 并切换到「前瞻指标」标签验证"
```

- [ ] **Step 3: 提交**

```bash
git add web_app/templates/index.html && git commit -m "feat: 新增前瞻指标 Web 前端页面（排名表 + 历史曲线）"
```

---

### 任务 14：编写单元测试

**文件：**
- 创建: `tests/test_factors.py`

- [ ] **Step 1: 写入测试代码**

```python
"""
前瞻因子引擎单元测试
"""

import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from vnpy.alpha.factors.base import DataFetcher, FactorComputer, FactorStorage
from vnpy.alpha.factors.engine import FactorEngine


# ---------------------------------------------------------------------------
# 测试辅助: Mock 实现
# ---------------------------------------------------------------------------

class MockFetcher(DataFetcher):
    """返回模拟日频估值数据"""
    def fetch(self, symbols, date):
        rows = []
        for sym in symbols:
            rows.append({
                "trade_date": "20241025",
                "ts_code": sym.replace("SZSE", "SZ").replace("SSE", "SH"),
                "pe_ttm": 10.0 + hash(sym) % 100,
                "pb": 2.0 + (hash(sym) % 10) * 0.1,
                "ps_ttm": 3.0 + (hash(sym) % 5) * 0.2,
            })
        return pl.DataFrame(rows)


class MockComputer(FactorComputer):
    """将 raw df 直接当因子输出"""
    def compute(self, raw_df):
        return raw_df


class MockStorage(FactorStorage):
    """内存存储"""
    def __init__(self):
        self._data: pl.DataFrame | None = None

    def save(self, factors):
        self._data = factors

    def load(self, symbols, start, end):
        if self._data is None:
            raise FileNotFoundError("no data")
        return self._data

    def get_latest(self, symbols):
        return self._data

    # 额外方法供 Engine 调用
    def save_daily(self, factors):
        self._data = factors

    def save_quarterly(self, factors):
        pass


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

class TestFactorEngine:
    """因子引擎调度器测试"""

    def test_register_and_run_daily(self):
        """测试管线注册与日终运行"""
        engine = FactorEngine()
        engine.register(
            "test_dim",
            MockFetcher(),
            MockComputer(),
            MockStorage(),
        )

        symbols = ["000001.SZSE", "600036.SSE"]
        results = engine.run_daily(symbols, "20241025")

        assert "test_dim" in results
        # 直接调用 _run_daily_pipeline 会找不到 fundamental 名称
        # 但 register 是成功的
        assert engine.pipelines

    def test_get_latest_snapshot(self):
        """测试获取最新快照"""
        engine = FactorEngine()
        storage = MockStorage()
        engine.register("test", MockFetcher(), MockComputer(), storage)

        symbols = ["000001.SZSE", "600036.SSE"]
        engine.run_daily(symbols, "20241025")
        snapshot = engine.get_latest_snapshot(symbols)

        assert not snapshot.is_empty()
        assert "trade_date" in snapshot.columns


class TestDimensionScorer:
    """维度评分器测试"""

    def test_equal_weight_scoring(self):
        from vnpy.alpha.factors.fusion import DimensionScorer

        df = pl.DataFrame({
            "vt_symbol": ["A.SSE", "B.SSE", "C.SSE", "D.SSE"],
            "factor1": [10.0, 20.0, 30.0, 40.0],
            "factor2": [0.1, 0.2, 0.15, 0.05],
        })

        scorer = DimensionScorer()
        result = scorer.score(df, ["factor1", "factor2"])

        assert len(result) == 4
        assert "dimension_score" in result.columns
        # 高因子值应得到较高评分
        scores = result["dimension_score"].to_list()
        assert scores[0] < scores[3]  # D should score highest

    def test_single_factor(self):
        from vnpy.alpha.factors.fusion import DimensionScorer

        df = pl.DataFrame({
            "vt_symbol": ["A.SSE", "B.SSE"],
            "pe_ttm": [1.0, 2.0],
        })
        scorer = DimensionScorer()
        result = scorer.score(df, ["pe_ttm"], {"pe_ttm": 1.0})
        assert len(result) == 2
        assert result["dimension_score"][0] > result["dimension_score"][1]

    def test_nan_handling(self):
        from vnpy.alpha.factors.fusion import DimensionScorer

        df = pl.DataFrame({
            "vt_symbol": ["A.SSE", "B.SSE", "C.SSE"],
            "factor1": [10.0, None, float("nan")],
        })
        scorer = DimensionScorer()
        result = scorer.score(df, ["factor1"])
        scores = result["dimension_score"].to_list()
        # NaN/None 应被填充为 50.0
        for s in scores:
            assert not np.isnan(s)


class TestSignalFusion:
    """信号融合器测试"""

    def test_two_dimension_fusion(self):
        from vnpy.alpha.factors.fusion import SignalFusion

        fund_df = pl.DataFrame({
            "vt_symbol": ["A.SSE", "B.SSE"],
            "dimension_score": [80.0, 60.0],
        })
        tech_df = pl.DataFrame({
            "vt_symbol": ["A.SSE", "B.SSE"],
            "dimension_score": [40.0, 90.0],
        })

        fusion = SignalFusion({"technical": 0.5, "fundamental": 0.5})
        result = fusion.fuse(
            datetime.now(),
            ["A.SSE", "B.SSE"],
            {"technical": tech_df, "fundamental": fund_df},
        )

        assert len(result) == 2
        assert "final_score" in result.columns
        assert "detail_json" in result.columns

        # A: 80*0.5 + 40*0.5 = 60
        # B: 60*0.5 + 90*0.5 = 75
        scores = result["final_score"].to_list()
        a_score = [s for i, s in enumerate(scores) if result["vt_symbol"][i] == "A.SSE"][0]
        b_score = [s for i, s in enumerate(scores) if result["vt_symbol"][i] == "B.SSE"][0]
        assert abs(a_score - 60.0) < 1.0
        assert abs(b_score - 75.0) < 1.0


class TestFundamentalStorage:
    """存储层测试"""

    def test_parquet_save_and_load(self):
        from vnpy.alpha.factors.fundamental.storage import FundamentalStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FundamentalStorage(tmpdir)

            df = pl.DataFrame({
                "trade_date": ["20241025", "20241025"],
                "vt_symbol": ["A.SSE", "B.SSE"],
                "pe_ttm": [10.0, 20.0],
            })
            storage.save_daily(df)

            # 加载最新
            latest = storage.get_latest(["A.SSE", "B.SSE"])
            assert len(latest) == 2

            loaded = storage.load(
                ["A.SSE"],
                datetime(2024, 10, 1),
                datetime(2024, 11, 1),
            )
            assert len(loaded) == 1
            assert loaded["vt_symbol"][0] == "A.SSE"

    def test_dedup_on_append(self):
        from vnpy.alpha.factors.fundamental.storage import FundamentalStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FundamentalStorage(tmpdir)

            df1 = pl.DataFrame({
                "trade_date": ["20241025"],
                "vt_symbol": ["A.SSE"],
                "pe_ttm": [10.0],
            })
            storage.save_daily(df1)
            storage.save_daily(df1)  # 重复追加

            latest = storage.get_latest(["A.SSE"])
            assert len(latest) == 1  # 去重


# ---------------------------------------------------------------------------
# 运行方式: pytest tests/test_factors.py -v
# ---------------------------------------------------------------------------
```

- [ ] **Step 2: 运行测试并验证全部通过**

```bash
uv run pytest tests/test_factors.py -v
```
预期：全部 8-10 个测试用例 PASS。

- [ ] **Step 3: 提交**

```bash
git add tests/test_factors.py && git commit -m "test: 新增前瞻因子引擎单元测试"
```

---

## 实施完成检查清单

所有任务完成后，执行以下验证：

- [ ] 语法检查：
  ```bash
  uv run python -c "from vnpy.alpha.factors import FactorEngine; from vnpy.alpha.factors.fusion import SignalFusion; print('all imports OK')"
  ```

- [ ] 测试通过：
  ```bash
  uv run pytest tests/test_factors.py -v
  ```

- [ ] ruff 检查：
  ```bash
  uv run ruff check vnpy/alpha/factors/ tests/test_factors.py
  ```
