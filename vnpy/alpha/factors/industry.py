"""行业分类映射模块

从 Tushare stock_basic 获取全量 A 股的行业分类（申万一级行业），
缓存到本地 parquet，用于行业中性化评分。

数据来源: stock_basic.industry 字段（Tushare 2000 积分可用）
"""

import logging
import os
from pathlib import Path

import polars as pl

from vnpy.alpha.factors.tushare_config import get_pro_api

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".vntrader", "factors")
INDUSTRY_CACHE = os.path.join(CACHE_DIR, "industry_map.parquet")


def _fetch_industry_map() -> pl.DataFrame:
    """从 Tushare stock_basic 拉取行业分类

    返回: [vt_symbol, industry, name]
    """
    pro = get_pro_api()
    raw = pro.stock_basic()
    if raw is None or len(raw) == 0:
        raise RuntimeError("stock_basic 返回空数据，无法获取行业分类")

    from vnpy.alpha.factors.fundamental.fetcher import _to_vnpy_code

    df = pl.from_pandas(raw)
    return df.with_columns(
        pl.col("ts_code")
        .map_elements(_to_vnpy_code, return_dtype=pl.Utf8)
        .alias("vt_symbol"),
    ).select(
        [
            pl.col("vt_symbol"),
            pl.col("industry"),
            pl.col("name"),
        ]
    )


def get_industry_map() -> dict[str, str]:
    """获取 {vt_symbol: industry_name} 映射

    优先从本地 parquet 缓存加载；缓存不存在时从 Tushare 拉取。
    行业字段来自 stock_basic.industry（申万一级行业分类）。
    """
    cache_path = Path(INDUSTRY_CACHE)
    if cache_path.exists():
        df = pl.read_parquet(str(INDUSTRY_CACHE))
    else:
        df = _fetch_industry_map()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(str(INDUSTRY_CACHE))
        logger.info("行业映射已缓存到 %s", INDUSTRY_CACHE)

    return {row["vt_symbol"]: row["industry"] for row in df.iter_rows(named=True)}


def get_industry_df() -> pl.DataFrame:
    """获取行业分类 DataFrame

    返回: [vt_symbol, industry]
    """
    cache_path = Path(INDUSTRY_CACHE)
    if cache_path.exists():
        return pl.read_parquet(str(INDUSTRY_CACHE))
    df = _fetch_industry_map()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(str(INDUSTRY_CACHE))
    return df
