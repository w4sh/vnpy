"""
前向收益计算器

从 bar 数据中按股票的收盘价计算多持有期的前向收益。
前向收益 = (close_{t+N} - close_t) / close_t
"""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)

# 常用持有期
DEFAULT_HORIZONS = [5, 20, 60]


class ForwardReturnCalculator:
    """前向收益计算器

    从本地 parquet 格式的 bar 数据中加载所有股票的收盘价，
    构建统一的价格时间序列，然后计算前向收益。

    用法:
        calc = ForwardReturnCalculator("/path/to/lab_data")
        returns = calc.calculate(symbols, dates, horizons=[5, 20, 60])
        # returns: trade_date | vt_symbol | fwd_5d | fwd_20d | fwd_60d
    """

    def __init__(self, lab_data_dir: str):
        self.lab_data_dir = Path(lab_data_dir)
        self.daily_dir = self.lab_data_dir / "daily"
        if not self.daily_dir.exists():
            raise FileNotFoundError(f"bar 数据目录不存在: {self.daily_dir}")

        self._price_df: pl.DataFrame | None = None

    def _load_prices(self, symbols: list[str], dates: list[str]) -> pl.DataFrame:
        """加载指定股票在指定日期范围内的收盘价，构建时间序列宽表

        返回:
            trade_date | symbol1 | symbol2 | ... (收盘价矩阵)
        """
        frames = []
        # 将 dates 转为 list[datetime] 用于过滤
        from datetime import datetime

        date_dts = [datetime.strptime(d, "%Y%m%d") for d in dates]
        min_date = min(date_dts)
        max_date = max(date_dts)

        for f in self.daily_dir.glob("*.parquet"):
            symbol = f.stem  # 文件名即代码
            if symbols and symbol not in symbols:
                continue

            try:
                df = pl.read_parquet(f, columns=["datetime", "close"])
                df = df.filter(
                    (pl.col("datetime") >= min_date) & (pl.col("datetime") <= max_date)
                )
                if df.is_empty():
                    continue

                df = df.with_columns(
                    pl.lit(symbol).alias("vt_symbol"),
                    pl.col("datetime").cast(pl.Date),
                )
                df = df.select(
                    [
                        pl.col("datetime"),
                        pl.col("vt_symbol"),
                        pl.col("close"),
                    ]
                )
                frames.append(df)
            except Exception as e:
                logger.warning("加载 bar 文件 %s 失败: %s", f.name, e)

        if not frames:
            return pl.DataFrame()

        return pl.concat(frames)

    def calculate(
        self,
        symbols: list[str] | None = None,
        dates: list[str] | None = None,
        horizons: list[int] | None = None,
    ) -> pl.DataFrame:
        """计算前向收益

        参数:
            symbols: 股票池列表，None 表示全部
            dates: 交易日列表 'YYYYMMDD'，None 表示全部
            horizons: 持有期列表，默认 [5, 20, 60]

        返回:
            trade_date | vt_symbol | fwd_5d | fwd_20d | fwd_60d
        """
        if horizons is None:
            horizons = DEFAULT_HORIZONS

        # 加载价格
        if symbols is None:
            symbols = []
        if dates is None:
            dates = []
            for f in self.daily_dir.glob("*.parquet"):
                df = pl.read_parquet(f, columns=["datetime"])
                for d in df["datetime"].unique():
                    dates.append(d.strftime("%Y%m%d"))
            dates = sorted(set(dates))

        price_df = self._load_prices(symbols, dates)

        if price_df.is_empty():
            logger.warning("价格数据为空")
            return pl.DataFrame()

        # 将 datetime 转为字符串 trade_date 以便对齐
        price_df = price_df.with_columns(
            pl.col("datetime").dt.strftime("%Y%m%d").alias("trade_date")
        )
        price_df = price_df.select(["trade_date", "vt_symbol", "close"])
        price_df = price_df.sort(["vt_symbol", "trade_date"])

        max_horizon = max(horizons)

        # 对每只股票独立计算前向收益（shift 向前看 N 天）
        result = price_df.with_columns(
            *[
                (
                    (pl.col("close").shift(-h) / pl.col("close") - 1.0)
                    .over("vt_symbol")
                    .alias(f"fwd_{h}d")
                )
                for h in horizons
            ]
        )

        # 过滤掉没有前向数据的最后几条记录
        result = result.filter(pl.col(f"fwd_{max_horizon}d").is_not_null())

        return result.select(
            ["trade_date", "vt_symbol"] + [f"fwd_{h}d" for h in horizons]
        )
