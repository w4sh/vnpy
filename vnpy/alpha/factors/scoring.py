"""多维基本面评分系统

基于行业中性化截面百分位归一化的三维评分:

| 维度 | 权重 | 因子 | 行业中性化 |
|------|------|------|-----------|
| 估值 | 25% | PE_ttm倒数, PB倒数, PS_ttm倒数 | 是 |
| 质量 | 35% | ROE, 毛利率, 资产负债率(反向) | 是 |
| 成长 | 25% | 营收同比增速, 净利润同比增速 | 是 |
| 动量 | 15% | 60日涨跌幅 | 否(全局) |

综合评分 = 估值×0.25 + 质量×0.35 + 成长×0.25 + 动量×0.15
"""

from __future__ import annotations

import logging

import polars as pl

from vnpy.alpha.factors.industry import get_industry_df

logger = logging.getLogger(__name__)

# ---- 权重配置 ----
DEFAULT_WEIGHTS: dict[str, float] = {
    "valuation": 0.25,
    "quality": 0.35,
    "growth": 0.25,
    "momentum": 0.15,
}

MIN_GROUP_SIZE = 3  # 行业分组最小数量，不足时回退到全局百分位


# ---- 百分位归一化（表达式级别） ----


def _global_percentile(factor_col: str) -> pl.Expr:
    """全局百分位排名 (0-100)，排名 1 → 100 分"""
    return (
        (
            (
                pl.col(factor_col).count()
                - pl.col(factor_col).rank("ordinal", descending=True)
                + 1
            )
            / pl.col(factor_col).count()
            * 100.0
        )
        .fill_nan(50.0)
        .fill_null(50.0)
    )


def _industry_percentile(factor_col: str) -> pl.Expr:
    """行业中性化百分位排名表达式 (0-100)

    在行业内做百分位归一化。若行业分组太小或行业为 None，回退到全局百分位。
    """
    count_expr = pl.col("industry").count().over("industry")
    rank_expr = (
        (
            count_expr
            - pl.col(factor_col).rank("ordinal", descending=True).over("industry")
            + 1
        )
        / count_expr
        * 100.0
    )

    # 只有有效行业且分组 >= MIN_GROUP_SIZE 时用行业百分位
    use_industry = (
        pl.col("industry").is_not_null()
        & (pl.col("industry") != "")
        & (count_expr >= MIN_GROUP_SIZE)
    )
    industry_rank = pl.when(use_industry).then(rank_expr)

    # 回退到全局百分位
    global_rank = _global_percentile(factor_col)
    return industry_rank.fill_null(global_rank).fill_null(50.0)


# ---- 单维度评分器（均返回 pl.Expr） ----


def _score_valuation(available_cols: set[str]) -> pl.Expr:
    """估值维度: PE倒数 + PB倒数 + PS倒数，行业中性化"""
    valid = [c for c in ["pe_ttm", "pb", "ps_ttm"] if c in available_cols]
    if not valid:
        return pl.lit(50.0, dtype=pl.Float64)
    scores = pl.lit(0.0, dtype=pl.Float64)
    for col in valid:
        scores = scores + _industry_percentile(col)
    return (scores / len(valid)).cast(pl.Float64)


def _score_quality(available_cols: set[str]) -> pl.Expr:
    """质量维度: ROE + 毛利率 + 资产负债率(反向)，行业中性化"""
    scores = pl.lit(0.0, dtype=pl.Float64)
    n = 0

    if "roe" in available_cols:
        scores = scores + _industry_percentile("roe")
        n += 1
    if "gross_margin" in available_cols:
        scores = scores + _industry_percentile("gross_margin")
        n += 1
    if "debt_to_assets" in available_cols:
        # 资产负债率：越低越好 → 取负值做百分位
        neg_expr = _industry_percentile_with_neg("debt_to_assets")
        scores = scores + neg_expr
        n += 1

    return (
        pl.when(n > 0)
        .then(scores / n)
        .otherwise(pl.lit(50.0, dtype=pl.Float64))
        .cast(pl.Float64)
    )


def _industry_percentile_with_neg(factor_col: str) -> pl.Expr:
    """资产负债率专用：取负值后做行业百分位"""
    count_expr = pl.col("industry").count().over("industry")
    neg_col = pl.col(factor_col) * (-1)
    rank_expr = (
        (count_expr - neg_col.rank("ordinal", descending=True).over("industry") + 1)
        / count_expr
        * 100.0
    )
    use_industry = (
        pl.col("industry").is_not_null()
        & (pl.col("industry") != "")
        & (count_expr >= MIN_GROUP_SIZE)
    )
    industry_rank = pl.when(use_industry).then(rank_expr)

    # 全局百分位（取负值）
    global_rank = (
        (
            (pl.col(factor_col).count() - neg_col.rank("ordinal", descending=True) + 1)
            / pl.col(factor_col).count()
            * 100.0
        )
        .fill_nan(50.0)
        .fill_null(50.0)
    )

    return industry_rank.fill_null(global_rank).fill_null(50.0)


def _score_growth(available_cols: set[str]) -> pl.Expr:
    """成长维度: 营收增速 + 净利增速，行业中性化"""
    valid = [
        c
        for c in ["revenue_yoy_growth", "net_profit_yoy_growth"]
        if c in available_cols
    ]
    if not valid:
        return pl.lit(50.0, dtype=pl.Float64)
    scores = pl.lit(0.0, dtype=pl.Float64)
    for col in valid:
        scores = scores + _industry_percentile(col)
    return (scores / len(valid)).cast(pl.Float64)


def _score_momentum() -> pl.Expr:
    """动量维度: 60日涨跌幅，全局百分位（不行业中性化）"""
    return _global_percentile("momentum_60d")


# ---- 主评分函数 ----


def compute_multi_dimension_scores(
    df: pl.DataFrame,
    weights: dict[str, float] | None = None,
) -> pl.DataFrame:
    """对因子快照执行多维行业中性化评分

    参数:
        df: 因子宽表，需包含 vt_symbol + 各因子列
        weights: 维度权重字典，默认用 DEFAULT_WEIGHTS
    返回:
        vt_symbol | industry | valuation_score | quality_score | growth_score
        | momentum_score | final_score
    """
    if df.is_empty():
        return pl.DataFrame()

    w = dict(DEFAULT_WEIGHTS if weights is None else weights)

    # 1. 注入行业分类
    industry_df = get_industry_df()
    df_enhanced = df.join(
        industry_df.select(["vt_symbol", "industry"]),
        on="vt_symbol",
        how="left",
    )

    # 2. 逐维度评分（表达式级别），按实际存在的列动态构造
    cols = set(df_enhanced.columns)
    score_exprs = []
    if any(c in cols for c in ["pe_ttm", "pb", "ps_ttm"]):
        score_exprs.append(_score_valuation(cols).alias("valuation_score"))
    if any(c in cols for c in ["roe", "gross_margin", "debt_to_assets"]):
        score_exprs.append(_score_quality(cols).alias("quality_score"))
    if any(c in cols for c in ["revenue_yoy_growth", "net_profit_yoy_growth"]):
        score_exprs.append(_score_growth(cols).alias("growth_score"))
    if "momentum_60d" in cols:
        score_exprs.append(_score_momentum().alias("momentum_score"))

    df_with_scores = (
        df_enhanced.with_columns(score_exprs) if score_exprs else df_enhanced
    )

    # 4. 加权综合分
    final = pl.lit(0.0, dtype=pl.Float64)
    has_any_score = False
    for dim, weight in w.items():
        col = f"{dim}_score"
        if col in df_with_scores.columns and weight > 0:
            final = final + pl.col(col).fill_null(50.0) * weight
            has_any_score = True

    if has_any_score:
        df_with_scores = df_with_scores.with_columns(
            final.cast(pl.Float64).alias("final_score"),
        )

    # 5. 填充缺失维度分为默认值
    for dim in w:
        col = f"{dim}_score"
        if col not in df_with_scores.columns:
            df_with_scores = df_with_scores.with_columns(
                pl.lit(50.0, dtype=pl.Float64).alias(col),
            )

    keep_cols = [
        "vt_symbol",
        "industry",
        "valuation_score",
        "quality_score",
        "growth_score",
        "momentum_score",
        "final_score",
    ]
    # 保留原始因子列（方便前端展示）
    for c in [
        "pe_ttm",
        "pb",
        "ps_ttm",
        "roe",
        "gross_margin",
        "debt_to_assets",
        "revenue_yoy_growth",
        "net_profit_yoy_growth",
        "momentum_60d",
        "trade_date",
    ]:
        if c in df_with_scores.columns:
            keep_cols.append(c)

    return df_with_scores.select([c for c in keep_cols if c in df_with_scores.columns])


def compute_final_score_only(
    df: pl.DataFrame,
    weights: dict[str, float] | None = None,
) -> pl.DataFrame:
    """仅计算综合评分，不保留维度分解（轻量版）

    返回: vt_symbol | final_score
    """
    scored = compute_multi_dimension_scores(df, weights)
    if scored.is_empty():
        return scored
    return scored.select(["vt_symbol", "final_score"])
