"""ETF 数据获取引擎

负责：
- 通过 Tushare fund_basic 获取 ETF 池
- 获取 ETF 日行情和基本面数据
- ETF 池管理

与候选股 engine.py 职责类似但使用 Tushare fund 相关 API。
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 全局配置
# ---------------------------------------------------------------------------

# ETF 池缓存（调用 refresh_etf_pool 更新）
_ETF_POOL_CACHE: list[dict[str, Any]] = []
_ETF_POOL_DATE: date | None = None

# 最小规模（亿），低于此的 ETF 剔除
MIN_FUND_SIZE_BILLION = 1.0

# ---------------------------------------------------------------------------
# Tushare API
# ---------------------------------------------------------------------------


def _get_pro_api():
    """获取 Tushare Pro API 实例"""
    from vnpy.alpha.factors.tushare_config import get_pro_api

    return get_pro_api()


# ---------------------------------------------------------------------------
# ETF 池管理
# ---------------------------------------------------------------------------


def get_etf_pool(force_refresh: bool = False) -> list[dict[str, Any]]:
    """获取 ETF 基础信息列表

    优先使用缓存，每日自动刷新。

    返回:
        list[dict]，每项包含 ts_code, name, fund_size, management_fee, custodian_fee 等
    """
    global _ETF_POOL_CACHE, _ETF_POOL_DATE

    today = date.today()
    if not force_refresh and _ETF_POOL_DATE == today and _ETF_POOL_CACHE:
        return _ETF_POOL_CACHE

    return _fetch_and_cache_etf_pool()


def _fetch_and_cache_etf_pool() -> list[dict[str, Any]]:
    """通过 Tushare fund_basic 拉取全市场 ETF"""
    global _ETF_POOL_CACHE, _ETF_POOL_DATE

    pro = _get_pro_api()
    pool: list[dict[str, Any]] = []

    try:
        # 拉取全部上市交易的交易所交易基金
        df = pro.fund_basic(market="E", list_status="L")

        if df is None or len(df) == 0:
            logger.warning("fund_basic 返回空数据，使用上次缓存")
            return _ETF_POOL_CACHE if _ETF_POOL_CACHE else []

        # 过滤：仅保留 ETF 类型
        for _, row in df.iterrows():
            fund_type = str(row.get("fund_type", ""))
            name = str(row.get("name", ""))

            # 判断是否是指数型 ETF（fund_type 包含 ETF 或 指数）
            is_etf = (
                "ETF" in fund_type.upper()
                or "指数" in fund_type
                or "ETF" in name.upper()
            )
            if not is_etf:
                continue

            try:
                fund_size = float(row.get("fund_size", 0) or 0)
            except (ValueError, TypeError):
                fund_size = 0

            if fund_size < MIN_FUND_SIZE_BILLION:
                continue

            try:
                mgmt_fee = float(row.get("management_fee", 0) or 0)
            except (ValueError, TypeError):
                mgmt_fee = 0
            try:
                cust_fee = float(row.get("custodian_fee", 0) or 0)
            except (ValueError, TypeError):
                cust_fee = 0

            pool.append(
                {
                    "ts_code": str(row["ts_code"]),
                    "name": name,
                    "fund_size": fund_size,
                    "management_fee": mgmt_fee,
                    "custodian_fee": cust_fee,
                    "expense_ratio": mgmt_fee + cust_fee,
                }
            )

        logger.info("ETF 池加载完成: %d 只（fund_basic 共 %d 条）", len(pool), len(df))

    except Exception as e:
        logger.error("ETF 池加载失败: %s", e)
        if _ETF_POOL_CACHE:
            logger.info("使用上次缓存: %d 只", len(_ETF_POOL_CACHE))
            return _ETF_POOL_CACHE
        return pool

    _ETF_POOL_CACHE = pool
    _ETF_POOL_DATE = date.today()
    return pool


# ---------------------------------------------------------------------------
# ETF 日行情获取
# ---------------------------------------------------------------------------


def _format_ts_code(ts_code: str) -> str:
    """确保 ts_code 格式为 '510050.SH'（Tushare 格式）"""
    if "." not in ts_code:
        return ts_code
    return ts_code


def fetch_daily_data(ts_code: str, lookback: int = 120) -> dict | None:
    """获取单只 ETF 日线行情数据

    使用 pro.fund_daily 获取行情（优先）或 fallback 到 pro_bar(asset="FD")。

    返回:
        dict 包含 dates[], close[], open[], high[], low[], volume[], amount[]
        或 None
    """
    from tushare import pro_bar

    max_retries = 3
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            end_str = date.today().strftime("%Y%m%d")
            start_str = (date.today() - timedelta(days=lookback * 2)).strftime("%Y%m%d")

            df = pro_bar(
                ts_code=ts_code,
                start_date=start_str,
                end_date=end_str,
                asset="FD",
                freq="D",
            )

            if df is None or len(df) < 20:
                return None

            df = df.sort_values("trade_date").reset_index(drop=True)

            return {
                "ts_code": ts_code,
                "dates": df["trade_date"].tolist(),
                "open": df["open"].astype(float).tolist(),
                "close": df["close"].astype(float).tolist(),
                "high": df["high"].astype(float).tolist(),
                "low": df["low"].astype(float).tolist(),
                "volume": df["vol"].astype(float).tolist(),
                "amount": (df["amount"] * 10000).astype(float).tolist()
                if "amount" in df.columns
                else df["vol"].astype(float).tolist(),
            }

        except Exception as e:
            last_error = e
            if attempt < max_retries:
                time.sleep(2**attempt)

    logger.warning("获取 ETF %s 数据失败: %s", ts_code, last_error)
    return None


def fetch_all_etf_daily(
    trade_date: str | None = None,
) -> dict[str, dict]:
    """按交易日批量获取全部 ETF 日行情

    调用 pro.fund_daily(trade_date=xxx) 一次性拉取。

    返回:
        dict[ts_code, dict] 包含行情数据
    """
    _get_pro_api()
    import tushare as ts

    pro = ts.pro_api()

    if trade_date is None:
        trade_date = date.today().strftime("%Y%m%d")

    etf_data: dict[str, dict] = {}

    try:
        df = pro.fund_daily(trade_date=trade_date)

        if df is not None and len(df) > 0:
            for _, row in df.iterrows():
                ts_code = str(row["ts_code"])
                etf_data[ts_code] = {
                    "ts_code": ts_code,
                    "trade_date": trade_date,
                    "open": float(row.get("open", 0) or 0),
                    "high": float(row.get("high", 0) or 0),
                    "low": float(row.get("low", 0) or 0),
                    "close": float(row.get("close", 0) or 0),
                    "pre_close": float(row.get("pre_close", 0) or 0),
                    "change": float(row.get("change", 0) or 0),
                    "pct_chg": float(row.get("pct_chg", 0) or 0),
                    "vol": float(row.get("vol", 0) or 0),
                    "amount": float(row.get("amount", 0) or 0),
                }

        logger.info(
            "ETF 日行情获取完成: trade_date=%s, count=%d",
            trade_date,
            len(etf_data),
        )

    except Exception as e:
        logger.error("ETF 日行情获取失败: %s", e)

    return etf_data


def fetch_etf_nav(trade_date: str | None = None) -> dict[str, float]:
    """获取 ETF 净值数据（用于计算折溢价率）

    返回:
        dict[ts_code, nav]
    """
    pro = _get_pro_api()

    if trade_date is None:
        trade_date = date.today().strftime("%Y%m%d")

    nav_data: dict[str, float] = {}

    try:
        df = pro.fund_nav(trade_date=trade_date)

        if df is not None and len(df) > 0:
            for _, row in df.iterrows():
                try:
                    nav_data[str(row["ts_code"])] = float(row.get("nav", 0) or 0)
                except (ValueError, TypeError):
                    continue

        logger.info(
            "ETF 净值获取完成: trade_date=%s, count=%d", trade_date, len(nav_data)
        )

    except Exception as e:
        logger.warning("ETF 净值获取失败（可能无权限）: %s", e)

    return nav_data


# ---------------------------------------------------------------------------
# 组合函数
# ---------------------------------------------------------------------------


def build_etf_daily_snapshot(
    trade_date: str | None = None,
) -> list[dict]:
    """构建当日 ETF 快照：合并 ETF 池 + 日行情 + 净值

    返回:
        list[dict] 每项包含基础信息 + 当日行情
    """
    pool = get_etf_pool()
    if not pool:
        logger.warning("ETF 池为空")
        return []

    daily = fetch_all_etf_daily(trade_date)
    nav = fetch_etf_nav(trade_date)

    snapshot = []
    for info in pool:
        ts_code = info["ts_code"]
        if ts_code not in daily:
            continue

        row = dict(info)
        row.update(daily[ts_code])

        # 合并净值计算折溢价
        nav_val = nav.get(ts_code)
        if nav_val and nav_val > 0 and row.get("close", 0) > 0:
            row["nav"] = nav_val
            row["premium_discount"] = (row["close"] - nav_val) / nav_val * 100
        else:
            row["nav"] = 0
            row["premium_discount"] = 0

        snapshot.append(row)

    logger.info(
        "ETF 快照构建完成: trade_date=%s, count=%d",
        trade_date or "today",
        len(snapshot),
    )
    return snapshot
