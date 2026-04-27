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
        # Normalize date params to strings for comparison with string columns
        start_str = (
            start.strftime("%Y%m%d") if isinstance(start, datetime) else str(start)
        )
        end_str = end.strftime("%Y%m%d") if isinstance(end, datetime) else str(end)
        return df.filter(
            pl.col("vt_symbol").is_in(symbols)
            & (pl.col("trade_date") >= start_str)
            & (pl.col("trade_date") <= end_str)
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
