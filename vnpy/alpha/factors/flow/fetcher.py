"""
资金流向 Tushare 数据拉取器

数据来源: moneyflow_hsgt (沪深港通资金流向)
提供北向/南向资金的累计净买入数据，通过差分计算每日净流入。
"""

import logging
import time
from datetime import datetime, timedelta

import polars as pl

from vnpy.alpha.factors.base import DataFetcher
from vnpy.alpha.factors.tushare_config import get_pro_api

logger = logging.getLogger(__name__)


class FlowFetcher(DataFetcher):
    """资金流向数据拉取器"""

    def __init__(self):
        self.pro = get_pro_api()

    def fetch(self, symbols: list[str], date: datetime) -> pl.DataFrame:
        """统一拉取入口"""
        return self.fetch_hsgt_flow(str(date.date()).replace("-", ""))

    def fetch_hsgt_flow(self, end_date: str, lookback_days: int = 90) -> pl.DataFrame:
        """拉取沪深港通资金流向历史序列

        参数:
            end_date: 截止日期 YYYYMMDD
            lookback_days: 回溯天数

        返回:
            DataFrame: trade_date, north_money(累计), south_money(累计),
                       north_net(当日净流入), south_net(当日净流入)
        """
        start_dt = datetime.strptime(end_date, "%Y%m%d") - timedelta(days=lookback_days)
        start_date = start_dt.strftime("%Y%m%d")

        try:
            raw = self.pro.moneyflow_hsgt(start_date=start_date, end_date=end_date)
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"拉取 moneyflow_hsgt 失败: {e}")
            return pl.DataFrame()

        if raw is None or len(raw) == 0:
            return pl.DataFrame()

        df = pl.from_pandas(raw)
        df = df.sort("trade_date")

        # 保留核心列
        keep_cols = ["trade_date", "north_money", "south_money"]
        existing = [c for c in keep_cols if c in df.columns]
        df = df.select(existing)

        # 差分得到当日净流入 (单位: 亿元)
        if "north_money" in df.columns:
            df = df.with_columns(
                pl.col("north_money").cast(pl.Float64).alias("north_cum"),
                pl.col("north_money").cast(pl.Float64).diff().alias("north_net"),
            ).drop("north_money")

        if "south_money" in df.columns:
            df = df.with_columns(
                pl.col("south_money").cast(pl.Float64).alias("south_cum"),
                pl.col("south_money").cast(pl.Float64).diff().alias("south_net"),
            ).drop("south_money")

        return df.with_columns(pl.col("trade_date").cast(pl.Utf8))
