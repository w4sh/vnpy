"""
Rank IC 分析器

计算每个因子在截面上的 Rank Information Coefficient:
- 对每个交易日，计算 factor_value 与 forward_return 的 Spearman 秩相关系数
- 汇总 IC 均值、标准差、IC_IR、IC>0 比例
- 支持多持有期的 IC 衰减分析
"""

from __future__ import annotations

import logging

import polars as pl
from scipy.stats import spearmanr

logger = logging.getLogger(__name__)


class ICAnalyzer:
    """截面 Rank IC 分析器"""

    def compute_ic_series(
        self,
        factor_df: pl.DataFrame,
        returns_df: pl.DataFrame,
        return_col: str = "fwd_20d",
    ) -> dict:
        """计算单个因子的 IC 时间序列

        参数:
            factor_df: trade_date | vt_symbol | factor_value (多个因子)
            returns_df: trade_date | vt_symbol | fwd_5d | fwd_20d | fwd_60d
            return_col: 用于 IC 计算的前向收益列名

        返回:
            {
                "factor_name": {
                    "ic_series": [(date, ic_value), ...],
                    "ic_mean": float,
                    "ic_std": float,
                    "ic_ir": float,
                    "ic_positive_ratio": float,
                    "n_periods": int,
                }
            }
        """
        results = {}

        # 确认 factor_df 的结构
        if "factor_name" in factor_df.columns:
            # 长表格式: trade_date | vt_symbol | factor_name | factor_value
            factor_names = factor_df["factor_name"].unique().to_list()
            for fname in factor_names:
                f_df = factor_df.filter(pl.col("factor_name") == fname).select(
                    [
                        "trade_date",
                        "vt_symbol",
                        pl.col("factor_value").alias("value"),
                    ]
                )
                ic_info = self._compute_single_factor_ic(f_df, returns_df, return_col)
                results[fname] = ic_info
        else:
            # 宽表格式: trade_date | vt_symbol | factor_col1 | factor_col2 ...
            # 因子列 = 所有不是 trade_date/vt_symbol 的列
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
                ic_info = self._compute_single_factor_ic(f_df, returns_df, return_col)
                results[col] = ic_info

        return results

    def _compute_single_factor_ic(
        self,
        factor_df: pl.DataFrame,
        returns_df: pl.DataFrame,
        return_col: str,
    ) -> dict:
        """计算单个因子的 IC 时间序列"""
        if return_col not in returns_df.columns:
            logger.error("收益列 '%s' 不存在", return_col)
            return {
                "ic_mean": 0.0,
                "ic_std": 0.0,
                "ic_ir": 0.0,
                "ic_positive_ratio": 0.0,
                "n_periods": 0,
                "ic_series": [],
            }

        # 合并因子值和前向收益
        merged = factor_df.join(
            returns_df.select(["trade_date", "vt_symbol", return_col]),
            on=["trade_date", "vt_symbol"],
            how="inner",
        )

        if merged.is_empty():
            logger.warning("因子与收益交叉数据集为空")
            return {
                "ic_mean": 0.0,
                "ic_std": 0.0,
                "ic_ir": 0.0,
                "ic_positive_ratio": 0.0,
                "n_periods": 0,
                "ic_series": [],
            }

        # 过滤掉因子值或收益为 null 的行
        merged = merged.filter(
            pl.col("value").is_not_null() & pl.col(return_col).is_not_null()
        )

        # 按日期分组计算 Rank IC
        ic_series = []
        dates = merged["trade_date"].unique().sort().to_list()

        for d in dates:
            subset = merged.filter(pl.col("trade_date") == d)
            factor_vals = subset["value"].to_numpy()
            return_vals = subset[return_col].to_numpy()

            # 至少需要 5 个有效数据点才计算 IC
            if len(factor_vals) < 5:
                continue

            try:
                ic, _ = spearmanr(factor_vals, return_vals)
                if not (hasattr(ic, "__float__") and abs(ic) <= 1.0):
                    continue
                ic_series.append((str(d), float(ic)))
            except Exception:
                continue

        if not ic_series:
            return {
                "ic_mean": 0.0,
                "ic_std": 0.0,
                "ic_ir": 0.0,
                "ic_positive_ratio": 0.0,
                "n_periods": 0,
                "ic_series": [],
            }

        ic_values = [v for _, v in ic_series]
        ic_mean = float(sum(ic_values) / len(ic_values))
        import math

        ic_std = float(
            math.sqrt(sum((v - ic_mean) ** 2 for v in ic_values) / len(ic_values))
        )
        ic_ir = ic_mean / ic_std if ic_std > 0 else 0.0
        ic_pos_ratio = sum(1 for v in ic_values if v > 0) / len(ic_values)

        return {
            "ic_mean": round(ic_mean, 6),
            "ic_std": round(ic_std, 6),
            "ic_ir": round(ic_ir, 4),
            "ic_positive_ratio": round(ic_pos_ratio, 4),
            "n_periods": len(ic_series),
            "ic_series": ic_series,
        }

    def analyze_decay(
        self,
        factor_df: pl.DataFrame,
        returns_df: pl.DataFrame,
        return_cols: list[str] | None = None,
    ) -> dict:
        """IC 衰减分析：不同持有期的 IC 变化

        参数:
            factor_df: 因子值
            returns_df: 多持有期前向收益
            return_cols: 要分析的收益列，默认 ["fwd_5d", "fwd_20d", "fwd_60d"]

        返回:
            {factor_name: {horizon: ic_mean, ...}}
        """
        if return_cols is None:
            return_cols = [c for c in returns_df.columns if c.startswith("fwd_")]

        results = {}
        for rc in return_cols:
            if rc not in returns_df.columns:
                continue
            ic_info = self.compute_ic_series(factor_df, returns_df, return_col=rc)
            for fname, info in ic_info.items():
                if fname not in results:
                    results[fname] = {}
                results[fname][rc] = info["ic_mean"]

        return results
