"""
基本面因子 Tushare 数据拉取器

拉取四类数据:
- income: 利润表（逐只拉取）
- fina_indicator: 财务指标（逐只拉取）
- daily_basic: 每日估值指标（批量拉取）
- disclosure_date: 财报实际公告日
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import TYPE_CHECKING

import polars as pl

from vnpy.alpha.factors.base import DataFetcher

if TYPE_CHECKING:
    from vnpy.alpha.factors.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


def _to_tushare_code(symbol: str) -> str:
    """vnpy 格式 (000001.SZSE) → tushare 格式 (000001.SZ)"""
    code, exchange = symbol.split(".")
    suffix = "SH" if exchange == "SSE" else "SZ"
    return f"{code}.{suffix}"


def _to_vnpy_code(ts_code: str) -> str:
    """tushare 格式 (000001.SZ) → vnpy 格式 (000001.SZSE)"""
    code, suffix = ts_code.split(".")
    exchange = "SSE" if suffix == "SH" else "SZSE"
    return f"{code}.{exchange}"


def get_pro_api():
    """获取 Tushare Pro API 实例"""
    import tushare as ts

    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 环境变量未设置")
    ts.set_token(token)
    return ts.pro_api()


class FundamentalFetcher(DataFetcher):
    """基本面数据拉取器

    支持注入 RateLimiter 控制逐只 API 调用频率。
    当 rate_limiter 为 None 时，回退到 time.sleep(0.3) 简单限频。
    """

    def __init__(self, rate_limiter: RateLimiter | None = None):
        self.pro = get_pro_api()
        self.rate_limiter = rate_limiter

    def fetch(self, symbols: list[str], date: datetime) -> pl.DataFrame:
        """统一拉取入口，返回原始数据 DataFrame"""
        raise NotImplementedError(
            "请调用具体的 fetch 方法: fetch_daily / fetch_quarterly"
        )

    # ---- 日频估值数据 ----

    def fetch_daily_basic(self, trade_date: str) -> pl.DataFrame:
        """批量拉取全市场日频估值数据

        参数:
            trade_date: '20241025' 格式
        返回:
            列: trade_date, ts_code, pe, pe_ttm, pb, ps, ps_ttm, total_mv, circ_mv, turnover_rate
        """
        try:
            raw = self.pro.daily_basic(trade_date=trade_date)
        except Exception as e:
            logger.warning(f"拉取 daily_basic(trade_date={trade_date}) 失败: {e}")
            return pl.DataFrame()

        if raw is None or len(raw) == 0:
            return pl.DataFrame()

        df = pl.from_pandas(raw)
        # 只保留需要的列
        keep_cols = [
            "trade_date",
            "ts_code",
            "pe",
            "pe_ttm",
            "pb",
            "ps",
            "ps_ttm",
            "total_mv",
            "circ_mv",
            "turnover_rate",
        ]
        existing = [c for c in keep_cols if c in df.columns]
        df = df.select(existing)

        df = df.with_columns(
            pl.col("trade_date").cast(pl.Utf8),
            pl.col("ts_code").cast(pl.Utf8),
        )
        return df

    # ---- 季频财务数据 ----

    def fetch_income(self, ts_code: str, start_date: str = "20180101") -> pl.DataFrame:
        """逐只拉取利润表

        返回:
            列: end_date, ts_code, revenue, n_income, total_cogs, operate_profit
        """
        try:
            raw = self.pro.income(
                ts_code=ts_code,
                start_date=start_date,
                fields="end_date,ts_code,revenue,n_income,total_cogs,operate_profit",
            )
            if self.rate_limiter:
                self.rate_limiter.acquire()
            else:
                time.sleep(0.3)
        except Exception as e:
            logger.warning(f"拉取 income({ts_code}) 失败: {e}")
            return pl.DataFrame()

        if raw is None or len(raw) == 0:
            return pl.DataFrame()

        df = pl.from_pandas(raw)
        cast_map = {}
        for col in ["revenue", "n_income", "total_cogs", "operate_profit"]:
            if col in df.columns:
                cast_map[col] = pl.col(col).cast(pl.Float64, strict=False)
        df = df.with_columns(
            pl.col("end_date").cast(pl.Utf8),
            pl.col("ts_code").cast(pl.Utf8),
            **cast_map,
        )
        return df

    def fetch_fina_indicator(
        self, ts_code: str, start_date: str = "20180101"
    ) -> pl.DataFrame:
        """逐只拉取财务指标

        返回:
            列: end_date, ts_code, roe, roa, grossprofit_margin,
                netprofit_margin, debt_to_assets
        """
        try:
            raw = self.pro.fina_indicator(
                ts_code=ts_code,
                start_date=start_date,
                fields="end_date,ts_code,roe,roa,grossprofit_margin,netprofit_margin,debt_to_assets",
            )
            if self.rate_limiter:
                self.rate_limiter.acquire()
            else:
                time.sleep(0.3)
        except Exception as e:
            logger.warning(f"拉取 fina_indicator({ts_code}) 失败: {e}")
            return pl.DataFrame()

        if raw is None or len(raw) == 0:
            return pl.DataFrame()

        df = pl.from_pandas(raw)
        numeric_cols = [
            "roe",
            "roa",
            "grossprofit_margin",
            "netprofit_margin",
            "debt_to_assets",
        ]
        cast_map = {}
        for col in numeric_cols:
            if col in df.columns:
                cast_map[col] = pl.col(col).cast(pl.Float64, strict=False)
        df = df.with_columns(
            pl.col("end_date").cast(pl.Utf8),
            pl.col("ts_code").cast(pl.Utf8),
            **cast_map,
        )
        return df

    def fetch_disclosure_dates(self, ts_code: str) -> pl.DataFrame:
        """拉取财报披露日期（预计 + 实际公告日）

        返回:
            列: ts_code, end_date, pre_date, actual_date
        """
        try:
            raw = self.pro.disclosure_date(
                ts_code=ts_code,
                fields="ts_code,end_date,pre_date,actual_date",
            )
            if self.rate_limiter:
                self.rate_limiter.acquire()
            else:
                time.sleep(0.2)
        except Exception as e:
            logger.warning(f"拉取 disclosure_date({ts_code}) 失败: {e}")
            return pl.DataFrame()

        if raw is None or len(raw) == 0:
            return pl.DataFrame()

        df = pl.from_pandas(raw)
        return df.with_columns(
            pl.col("end_date").cast(pl.Utf8),
            pl.col("ts_code").cast(pl.Utf8),
            pl.col("pre_date").cast(pl.Utf8),
            pl.col("actual_date").cast(pl.Utf8),
        )

    # ---- 财报旺季判断 ----

    @staticmethod
    def is_earnings_window(today: datetime, window_days: int = 5) -> bool:
        """判断今天是否在财报公告旺季窗口内

        旺季窗口: 4/30, 8/31, 10/31, 次年 4/30 前后 ±window_days 个自然日
        """
        earnings_deadlines = [
            datetime(today.year, 4, 30),
            datetime(today.year, 8, 31),
            datetime(today.year, 10, 31),
            datetime(today.year + 1, 4, 30),
        ]
        for deadline in earnings_deadlines:
            if abs((today - deadline).days) <= window_days:
                return True
        return False
