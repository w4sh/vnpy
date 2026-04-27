"""
资金流向因子计算器

从沪深港通资金流数据计算市场情绪因子:
  - north_net: 北向资金当日净流入(亿元)
  - north_ma5: 5日均线
  - north_ma10: 10日均线
  - north_ma20: 20日均线
  - flow_score: 资金流向市场情绪评分 (0-100)
"""

import logging

import polars as pl

from vnpy.alpha.factors.base import FactorComputer

logger = logging.getLogger(__name__)


class FlowComputer(FactorComputer):
    """资金流向因子计算器"""

    def compute(self, raw_df: pl.DataFrame) -> pl.DataFrame:
        """从 raw 数据计算因子

        输入: trade_date, north_cum, north_net, south_cum, south_net
        输出: trade_date, north_net, north_ma5, north_ma10, north_ma20, flow_score
        """
        return self.compute_flow(raw_df)

    def compute_flow(self, raw_df: pl.DataFrame) -> pl.DataFrame:
        """计算资金流向因子"""
        if raw_df.is_empty():
            return pl.DataFrame()

        df = raw_df.sort("trade_date")

        # 计算移动均线
        if "north_net" not in df.columns or df["north_net"].null_count() == len(df):
            return pl.DataFrame()

        df = df.with_columns(
            pl.col("north_net").rolling_mean(5, min_periods=1).alias("north_ma5"),
            pl.col("north_net").rolling_mean(10, min_periods=1).alias("north_ma10"),
            pl.col("north_net").rolling_mean(20, min_periods=1).alias("north_ma20"),
        )

        # 对周/月均值做标准化: 偏离0轴的程度
        df = df.with_columns(
            (pl.col("north_ma5") / (pl.col("north_ma5").abs().mean() + 1e-6)).alias(
                "ma5_norm"
            ),
            (pl.col("north_ma10") / (pl.col("north_ma10").abs().mean() + 1e-6)).alias(
                "ma10_norm"
            ),
            (pl.col("north_ma20") / (pl.col("north_ma20").abs().mean() + 1e-6)).alias(
                "ma20_norm"
            ),
        )

        # 市场情绪评分: MA 趋势的综合判断
        # 使用 sigmoid 映射到 0-100
        signal = (
            pl.col("ma5_norm") * 0.4
            + pl.col("ma10_norm") * 0.3
            + pl.col("ma20_norm") * 0.3
        )
        df = df.with_columns(
            (50.0 + 40.0 * (signal / (1.0 + signal.abs())))
            .cast(pl.Float64)
            .alias("flow_score")
        )

        keep_cols = [
            "trade_date",
            "north_net",
            "north_ma5",
            "north_ma10",
            "north_ma20",
            "flow_score",
        ]
        existing = [c for c in keep_cols if c in df.columns]

        return df.select(existing).with_columns(
            pl.col("trade_date").cast(pl.Utf8),
            *[
                pl.col(c).cast(pl.Float64, strict=False)
                for c in existing
                if c != "trade_date"
            ],
        )
