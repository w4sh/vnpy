#!/usr/bin/env python3
"""基于前瞻因子的 Top 20 股票推荐（含市值过滤）

使用方法:
    python scripts/top20_recommend.py

推荐逻辑:
    1. 加载最新交易日的日频因子 (pe_ttm / pb / ps_ttm) 和季频因子 (roe / gross_margin / ...)
    2. 从 Tushare daily_basic 获取最新市值 (total_mv)
    3. 剔除市值排名后 30% 的股票（微盘股过滤）
    4. 按 IC_IR 加权百分位计算综合得分，取 Top 20
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

import polars as pl
import numpy as np

# ---- 因子权重：来自 8 因子评估结果 (IC_IR, 绝对值) ----
# 方向: ic_mean > 0 → 正向 (因子值越大越好), ic_mean < 0 → 反向 (因子值越小越好)
FACTOR_WEIGHTS: dict[str, tuple[float, int]] = {
    #                        IC_IR       方向 (-1=反向, +1=正向)
    "pe_ttm": (0.2369, +1),  # PE 越高越好 (A 股 IC_mean=+0.0401)
    "pb": (0.5166, +1),  # PB 越高越好 (A 股特殊)
    "ps_ttm": (0.4357, +1),  # PS 越高越好
    "roe": (0.1953, -1),  # ROE 越低越好 (A 股特殊)
    "gross_margin": (0.2488, -1),  # 毛利率越低越好
    "debt_to_assets": (0.1682, +1),  # 负债率越高越好
    "revenue_yoy_growth": (0.1728, -1),  # 收入增速越低越好
    "net_profit_yoy_growth": (0.1123, -1),  # 净利增速越低越好
}

# 市值过滤: 只保留市值排名前 70% 的股票（剔除最小 30%）
MARKET_CAP_TOP_PCT = 0.70


def load_daily_factors(latest_date: str) -> pl.DataFrame:
    """加载最新交易日的日频因子"""
    daily_path = Path.home() / ".vntrader" / "factors" / "fundamental_daily.parquet"
    df = pl.read_parquet(daily_path)
    daily_factors = [f for f in ["pe_ttm", "pb", "ps_ttm"] if f in FACTOR_WEIGHTS]
    id_cols = ["trade_date", "vt_symbol"]
    result = df.filter(pl.col("trade_date") == latest_date).select(
        id_cols + daily_factors
    )
    logger.info("日频因子: %d 只股票, 日期=%s", result.shape[0], latest_date)
    return result


def load_quarterly_factors(latest_date: str) -> pl.DataFrame:
    """加载最新季频因子（前值填充到 latest_date）"""
    q_path = Path.home() / ".vntrader" / "factors" / "fundamental_quarterly.parquet"
    qdf = pl.read_parquet(q_path)
    quarterly_factors = [
        f for f in FACTOR_WEIGHTS if f not in ("pe_ttm", "pb", "ps_ttm")
    ]
    qdf = qdf.filter(pl.col("factor_name").is_in(quarterly_factors))

    # 对每只股票×因子，取 pub_date ≤ latest_date 的最新值
    qdf = qdf.filter(pl.col("pub_date") <= latest_date)
    qdf = qdf.sort(
        ["vt_symbol", "factor_name", "pub_date"], descending=[False, False, True]
    )
    qdf = qdf.unique(subset=["vt_symbol", "factor_name"], keep="first")
    qdf = qdf.select(["vt_symbol", "factor_name", "factor_value"])

    # 长表 → 宽表
    wide = qdf.pivot(values="factor_value", index="vt_symbol", on="factor_name")
    wide = wide.with_columns(pl.lit(latest_date).alias("trade_date"))
    logger.info("季频因子: %d 只股票, %d 个因子", wide.shape[0], len(quarterly_factors))
    return wide


def fetch_market_cap(latest_date: str) -> pl.DataFrame:
    """从 Tushare 获取最新总市值（亿元）"""
    from vnpy.alpha.factors.tushare_config import get_pro_api

    api = get_pro_api()
    # daily_basic 返回 total_mv 单位为万元，转为亿元方便阅读
    raw = api.daily_basic(trade_date=latest_date, fields="ts_code,total_mv")
    if raw is None or raw.empty:
        logger.error("Tushare daily_basic 返回空数据，跳过市值过滤")
        return pl.DataFrame()

    df = pl.from_pandas(raw)
    # Tushare 后缀 (.SH/.SZ) -> VeighNa 后缀 (.SSE/.SZSE)
    symbol = (
        pl.col("ts_code").str.replace(r"\.SH$", ".SSE").str.replace(r"\.SZ$", ".SZSE")
    )
    df = df.with_columns(
        [
            symbol.alias("vt_symbol"),
            (pl.col("total_mv") / 1e4).alias("market_cap_yi"),  # 万元 → 亿元
        ]
    )
    df = df.select(["vt_symbol", "market_cap_yi"])
    logger.info(
        "市值数据: %d 只股票, 中位数=%.0f 亿", df.shape[0], df["market_cap_yi"].median()
    )
    return df


def filter_by_market_cap(df: pl.DataFrame, market_cap: pl.DataFrame) -> pl.DataFrame:
    """只保留市值排名前 MARKET_CAP_TOP_PCT 的股票，并附加市值列"""
    if market_cap.is_empty():
        logger.warning("无市值数据，跳过市值过滤")
        return df

    # 计算市值阈值: 只保留前 70%
    threshold = market_cap["market_cap_yi"].quantile(1 - MARKET_CAP_TOP_PCT)
    logger.info(
        "市值阈值: ≥ %.2f 亿 (保留前 %.0f%%)", threshold, MARKET_CAP_TOP_PCT * 100
    )

    qualified = market_cap.filter(pl.col("market_cap_yi") >= threshold)
    result = df.join(qualified, on="vt_symbol", how="inner")
    logger.info("市值过滤后: %d → %d 只股票", market_cap.shape[0], result.shape[0])
    return result


# ---- 行业中性化 ----
INDUSTRY_CACHE = Path.home() / ".vntrader" / "factors" / "industry_map.parquet"


def fetch_industry_map() -> dict[str, str]:
    """获取股票→申万一级行业映射，优先用本地缓存"""
    if INDUSTRY_CACHE.exists():
        df = pl.read_parquet(INDUSTRY_CACHE)
        return dict(zip(df["vt_symbol"].to_list(), df["industry"].to_list()))

    from vnpy.alpha.factors.tushare_config import get_pro_api

    api = get_pro_api()
    raw = api.stock_basic(list_status="L", fields="ts_code,industry")
    if raw is None or raw.empty:
        logger.warning("Tushare stock_basic 返回空，无法获取行业数据")
        return {}

    df = pl.from_pandas(raw)
    symbol = (
        pl.col("ts_code").str.replace(r"\.SH$", ".SSE").str.replace(r"\.SZ$", ".SZSE")
    )
    df = df.with_columns(
        [symbol.alias("vt_symbol"), pl.col("industry").fill_null("未知")]
    )
    df = df.filter(pl.col("industry") != "未知")
    df = df.select(["vt_symbol", "industry"])

    # 缓存到本地
    df.write_parquet(INDUSTRY_CACHE)
    logger.info(
        "行业分类: %d 只股票, %d 个行业 (已缓存)",
        df.shape[0],
        df["industry"].n_unique(),
    )
    return dict(zip(df["vt_symbol"].to_list(), df["industry"].to_list()))


def compute_composite_score(df: pl.DataFrame) -> pl.DataFrame:
    """计算 IC_IR 加权的综合得分（行业中性化：行业内百分位排名）"""
    scores = df.select(["vt_symbol"])

    for factor_name, (ic_ir, direction) in FACTOR_WEIGHTS.items():
        if factor_name not in df.columns:
            scores = scores.with_columns(pl.lit(0.0).alias(f"score_{factor_name}"))
            continue

        # 行业内排名: group_by industry, 在组内按 factor_value 排序取百分位
        rank_expr = pl.col(factor_name).rank(
            "ordinal", descending=(direction == -1)
        ).over("industry") / pl.col(factor_name).count().over("industry")
        factor_score = df.select(["vt_symbol", "industry", factor_name]).with_columns(
            (rank_expr * abs(ic_ir)).alias(f"score_{factor_name}")
        )
        factor_score = factor_score.select(["vt_symbol", f"score_{factor_name}"])

        scores = scores.join(factor_score, on="vt_symbol", how="left").with_columns(
            pl.col(f"score_{factor_name}").fill_null(0)
        )

    # 综合得分 = 各因子得分之和 / 总权重
    score_cols = [c for c in scores.columns if c.startswith("score_")]
    total_weight = sum(abs(w[0]) for w in FACTOR_WEIGHTS.values())
    scores = scores.with_columns(
        pl.sum_horizontal(score_cols).alias("composite_score")
    ).with_columns((pl.col("composite_score") / total_weight).alias("composite_score"))

    return scores


def main() -> None:
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

    # 1. 确定最新交易日
    daily_path = Path.home() / ".vntrader" / "factors" / "fundamental_daily.parquet"
    if not daily_path.exists():
        logger.error("日频因子文件不存在: %s", daily_path)
        sys.exit(1)

    latest_date = pl.read_parquet(daily_path)["trade_date"].max()
    logger.info("最新交易日: %s", latest_date)

    # 2. 加载因子
    daily = load_daily_factors(latest_date)
    quarterly = load_quarterly_factors(latest_date)
    factor_df = daily.join(quarterly, on=["trade_date", "vt_symbol"], how="left")

    # 2b. 数据质量过滤: 剔除最强因子 (PE/PB) 缺失的股票
    before_qc = factor_df.shape[0]
    factor_df = factor_df.filter(
        pl.col("pe_ttm").is_not_null() & pl.col("pb").is_not_null()
    )
    logger.info(
        "数据质量过滤 (PE/PB 非空): %d → %d 只股票", before_qc, factor_df.shape[0]
    )

    # 2c. 行业分类（行业中性化用）
    industry_map = fetch_industry_map()
    if industry_map:
        factor_df = factor_df.with_columns(
            pl.col("vt_symbol")
            .replace_strict(industry_map, default="未知")
            .alias("industry")
        )
        # 剔除未知行业和行业样本太少的
        ind_counts = factor_df.group_by("industry").len()
        small_inds = ind_counts.filter(pl.col("len") < 5)["industry"].to_list()
        if small_inds:
            factor_df = factor_df.filter(~pl.col("industry").is_in(small_inds))
            logger.info(
                "剔除样本 <5 的行业: %s → %d 只", small_inds, factor_df.shape[0]
            )
    else:
        factor_df = factor_df.with_columns(pl.lit("无分类").alias("industry"))

    # 3. 获取市值并过滤
    market_cap = fetch_market_cap(latest_date)
    factor_df = filter_by_market_cap(factor_df, market_cap)

    if factor_df.is_empty():
        logger.error("过滤后无股票")
        sys.exit(1)

    # 4. 计算综合得分
    scored = compute_composite_score(factor_df)
    merged = factor_df.join(scored, on="vt_symbol", how="inner")

    # 5. Top 20
    result = merged.sort("composite_score", descending=True).head(20)

    # 显示
    def _fmt(v, width: int = 8, decimals: int = 1) -> str:
        """格式化数值，None → -"""
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return f"{'-':>{width}s}"
        return f"{v:>{width}.{decimals}f}"

    # 修正: pe_ttm None 被 float(None) 转为 NaN
    import math

    def _is_null(v) -> bool:
        return v is None or (isinstance(v, float) and math.isnan(v))

    print(f"\n{'=' * 120}")
    print(
        f"  Top 20 股票推荐 (基于 {len(FACTOR_WEIGHTS)} 个前瞻因子, IC_IR 加权, 行业中性化)"
    )
    print(f"  日期: {latest_date}")
    print(f"  市值过滤: 保留前 {MARKET_CAP_TOP_PCT * 100:.0f}% 大市值股票")
    print(f"{'=' * 120}")
    print(
        f"{'#':<4s} {'代码':<12s} {'行业':<10s} {'综合分':>6s} {'PE':>6s} {'PB':>6s} {'PS':>6s} "
        f"{'ROE%':>7s} {'毛利率%':>8s} {'负债率%':>8s}"
    )
    print(f"{'-' * 120}")

    for i, row in enumerate(result.iter_rows(named=True)):
        ind = row.get("industry", "?")[:8]
        pe = row.get("pe_ttm")
        pb = row.get("pb")
        ps = row.get("ps_ttm")
        roe = row.get("roe")
        gm = row.get("gross_margin")
        da = row.get("debt_to_assets")
        print(
            f"{i + 1:<4d} {row['vt_symbol']:<12s} {ind:<10s} {row['composite_score']:>6.4f} "
            f"{_fmt(pe, width=6, decimals=1) if not _is_null(pe) else _fmt(None, width=6):>6s} "
            f"{_fmt(pb, width=6, decimals=2) if not _is_null(pb) else _fmt(None, width=6):>6s} "
            f"{_fmt(ps, width=6, decimals=2) if not _is_null(ps) else _fmt(None, width=6):>6s} "
            f"{_fmt(roe, width=7, decimals=1) if not _is_null(roe) else _fmt(None, width=7):>7s} "
            f"{_fmt(gm, width=8, decimals=1) if not _is_null(gm) else _fmt(None, width=8):>8s} "
            f"{_fmt(da, width=8, decimals=1) if not _is_null(da) else _fmt(None, width=8):>8s}"
        )

    print()

    # 保存 CSV
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    csv_path = output_dir / f"top20_recommend_{latest_date}.csv"
    result.write_csv(csv_path)
    logger.info("结果已保存: %s", csv_path)


if __name__ == "__main__":
    main()
