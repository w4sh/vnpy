"""
分位分组收益分析器

按因子值将股票分为 N 组（默认5组），计算各组的平均前向收益。
支持多空收益（Q1 - Q5）和累计收益曲线。
"""

from __future__ import annotations

import logging

import numpy as np
import polars as pl

logger = logging.getLogger(__name__)


class QuantileAnalyzer:
    """分位分组收益分析器"""

    def group_returns(
        self,
        factor_df: pl.DataFrame,
        returns_df: pl.DataFrame,
        return_col: str = "fwd_20d",
        n_groups: int = 5,
    ) -> dict:
        """按因子值分 N 组，计算各组的平均前向收益

        参数:
            factor_df: trade_date | vt_symbol | factor_value
            returns_df: trade_date | vt_symbol | fwd_5d | fwd_20d | fwd_60d
            return_col: 前向收益列
            n_groups: 分组数，默认 5

        返回:
            {
                "factor_name": {
                    "group_returns": [(group_label, avg_return), ...],
                    "long_short": float,  # Q1 - Q5 多空收益
                    "cumulative": [(date, cum_return), ...],
                }
            }
        """
        results = {}

        if "factor_name" in factor_df.columns:
            # 长表格式
            factor_names = factor_df["factor_name"].unique().to_list()
            for fname in factor_names:
                f_df = factor_df.filter(pl.col("factor_name") == fname).select(
                    [
                        "trade_date",
                        "vt_symbol",
                        pl.col("factor_value").alias("value"),
                    ]
                )
                results[fname] = self._compute_single_group(
                    f_df, returns_df, return_col, n_groups
                )
        else:
            # 宽表格式
            factor_cols = [
                c for c in factor_df.columns if c not in ("trade_date", "vt_symbol")
            ]
            for col in factor_cols:
                f_df = factor_df.select(
                    [
                        "trade_date",
                        "vt_symbol",
                        pl.col(col).alias("value"),
                    ]
                )
                results[col] = self._compute_single_group(
                    f_df, returns_df, return_col, n_groups
                )

        return results

    def _compute_single_group(
        self,
        factor_df: pl.DataFrame,
        returns_df: pl.DataFrame,
        return_col: str,
        n_groups: int,
    ) -> dict:
        """单个因子的分组收益计算"""
        if return_col not in returns_df.columns:
            return {
                "group_returns": [],
                "long_short": 0.0,
                "cumulative": [],
            }

        # 合并
        merged = factor_df.join(
            returns_df.select(["trade_date", "vt_symbol", return_col]),
            on=["trade_date", "vt_symbol"],
            how="inner",
        )

        if merged.is_empty():
            return {
                "group_returns": [],
                "long_short": 0.0,
                "cumulative": [],
            }

        merged = merged.filter(
            pl.col("value").is_not_null() & pl.col(return_col).is_not_null()
        )

        # 按日期分组，计算截面上值
        dates = merged["trade_date"].unique().sort().to_list()

        # 累积各组的截面收益
        group_returns: dict[int, list[float]] = {i: [] for i in range(n_groups)}
        long_short_series: list[float] = []

        for d in dates:
            subset = merged.filter(pl.col("trade_date") == d)
            if subset.shape[0] < n_groups * 3:
                continue

            # 按因子值分 N 组
            values = subset["value"].to_numpy()
            returns = subset[return_col].to_numpy()

            # 使用 percentile 分位数边界，生成 n_groups 个等分位组
            percentiles = np.linspace(0, 100, n_groups + 1)
            # 排除 nan
            mask = ~np.isnan(values) & ~np.isnan(returns)
            values = values[mask]
            returns_arr = returns[mask]

            if len(values) < n_groups * 3:
                continue

            bins = np.percentile(values, percentiles)
            # digitize 返回 1..n_groups 的索引（0=小于最小边界, n_groups=大于最大边界）
            try:
                group_indices = np.digitize(values, bins) - 1
                # 将超出范围的裁剪到有效组
                group_indices = np.clip(group_indices, 0, n_groups - 1)
            except Exception:
                continue

            for g in range(n_groups):
                g_mask = group_indices == g
                if g_mask.sum() > 0:
                    avg_ret = float(np.mean(returns_arr[g_mask]))
                    group_returns[g].append(avg_ret)

            # Q1 (最高因子值组 = 第 n_groups-1 组) - Q5 (最低因子值组 = 第 0 组)
            q1_mask = group_indices == n_groups - 1
            q5_mask = group_indices == 0
            if q1_mask.sum() > 0 and q5_mask.sum() > 0:
                ls = float(np.mean(returns_arr[q1_mask])) - float(
                    np.mean(returns_arr[q5_mask])
                )
                long_short_series.append(ls)

        # 汇总
        avg_group_returns = []
        for g in range(n_groups):
            if group_returns[g]:
                avg = sum(group_returns[g]) / len(group_returns[g])
            else:
                avg = 0.0
            label = f"Q{g + 1}"
            avg_group_returns.append((label, round(avg, 6)))

        avg_long_short = (
            sum(long_short_series) / len(long_short_series)
            if long_short_series
            else 0.0
        )

        # 累计多空收益
        cumulative = []
        cum = 1.0
        for ls in long_short_series:
            cum *= 1.0 + ls
            cumulative.append(cum)

        return {
            "group_returns": avg_group_returns,
            "long_short": round(avg_long_short, 6),
            "cumulative": cumulative,
        }
