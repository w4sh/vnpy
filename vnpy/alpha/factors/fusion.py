"""
信号融合层

将多维度因子评分融合为单一综合评分，支持等权加权和可配置权重。
核心理念：排名标准化后等权融合，权重暴露为策略 Setting 参数。
"""

import logging
from datetime import datetime

import polars as pl

logger = logging.getLogger(__name__)

# 默认权重：各维度等权
DEFAULT_WEIGHTS = {
    "technical": 0.45,
    "fundamental": 0.40,
    "flow": 0.15,
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
        weights: dict[str, float] | None = None,
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

            # 截面排名标准化: rank 1 → 100, last rank → 0
            rank_expr = (
                (
                    pl.col(name).count()
                    - pl.col(name).rank("ordinal", descending=True)
                    + 1
                )
                / pl.col(name).count()
                * 100.0
            )
            norm = rank_expr.fill_nan(50.0).fill_null(50.0)
            total_score = total_score + norm * pl.lit(w)

        return df.select(
            pl.col("vt_symbol"),
            total_score.cast(pl.Float64, strict=False).alias("dimension_score"),
        )


class SignalFusion:
    """策略层面的多维度信号融合器

    两层架构:
      Layer 1: DimensionScorer 计算每个维度的综合分
      Layer 2: 跨维度加权融合 → final_score
    """

    def __init__(self, weights: dict[str, float] | None = None):
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
            dim_df = dim_df.select(
                [
                    pl.col("vt_symbol"),
                    pl.col("dimension_score").alias(f"{dim_name}_score"),
                    pl.lit(w).alias(f"{dim_name}_weight"),
                ]
            )
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
                part = pl.col(score_col).fill_null(50.0) * pl.col(weight_col).fill_null(
                    0.0
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
        return result.with_columns(pl.lit(str(date.date())).alias("date")).sort(
            "final_score", descending=True
        )

    @staticmethod
    def _build_detail_expr(
        dimension_scores: dict[str, pl.DataFrame],
    ) -> list:
        """构建 detail_json 中各维度的键值对表达式"""
        exprs = []
        names = list(dimension_scores.keys())
        for i, dim_name in enumerate(names):
            sc = f"{dim_name}_score"
            wc = f"{dim_name}_weight"
            comma = "," if i < len(names) - 1 else ""
            exprs.append(
                pl.concat_str(
                    [
                        pl.lit(f'"{dim_name}":{{"score":'),
                        pl.col(sc).fill_null(0.0).round(2).cast(pl.Utf8),
                        pl.lit(',"weight":'),
                        pl.col(wc).fill_null(0.0).cast(pl.Utf8),
                        pl.lit("}") + pl.lit(comma),
                    ],
                    separator="",
                ),
            )
        return exprs

    def update_weights(self, weights: dict[str, float]) -> None:
        """动态更新权重（供回测参数调整）"""
        self.weights = dict(weights)
