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

    def load_quarterly_with_forward_fill(
        self, symbols: list[str], start: str, end: str
    ) -> pl.DataFrame:
        """加载季频因子长表，并前值填充至交易日序列

        前值填充策略：
        - 季频因子在 pub_date（公告日）当天开始生效
        - 至下一个 pub_date 之前保持不变
        - 若股票在某财报窗口前尚无公告，评分为 NaN

        参数:
            symbols: 股票代码列表
            start: 起始日期 'YYYYMMDD'
            end: 结束日期 'YYYYMMDD'

        返回:
            填充后的季频因子长表，包含 trade_date | vt_symbol | factor_name | factor_value
        """
        if not self.quarterly_path.exists():
            raise FileNotFoundError(f"{self.quarterly_path} 不存在")

        df = pl.read_parquet(self.quarterly_path)
        df = df.filter(pl.col("vt_symbol").is_in(symbols))

        if df.is_empty():
            return df

        # 构建完整交易日序列（按 symbol 分组）
        all_dates = pl.DataFrame(
            {"trade_date": list(range(int(start), int(end) + 1, 1))}
        ).with_columns(pl.col("trade_date").cast(str))

        # 将 pub_date 当作生效日期，对每个 symbol 做前值填充
        result_frames = []
        for sym in symbols:
            sym_df = df.filter(pl.col("vt_symbol") == sym).sort("pub_date")
            if sym_df.is_empty():
                continue

            # 构建该股票完整的日期-因子表
            sym_dates = all_dates.clone()
            sym_filled = sym_dates.join(
                sym_df.select(["pub_date", "factor_name", "factor_value"]),
                left_on="trade_date",
                right_on="pub_date",
                how="left",
            ).with_columns(pl.col("vt_symbol").fill_null(sym))

            # 按因子名分组前值填充
            for factor_name in sym_filled["factor_name"].unique().drop_nulls():
                factor_data = sym_filled.filter(pl.col("factor_name") == factor_name)
                factor_data = factor_data.sort("trade_date")
                # forward fill: 用前一个非空值填充 NaN
                factor_data = factor_data.with_columns(
                    pl.col("factor_value").forward_fill()
                )
                result_frames.append(factor_data)

        if not result_frames:
            return pl.DataFrame()

        return pl.concat(result_frames)
