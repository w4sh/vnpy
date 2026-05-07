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
from datetime import date, datetime, timedelta
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

# 多日行情获取参数（用于动量/波动率因子计算）
_MULTI_DAY_MAX_CALENDAR = 80  # 最多回溯日历天数
_MULTI_DAY_SLEEP = 0.2  # API 调用间隔（秒）
_MULTI_DAY_MIN_BARS = 20  # 最少需要的数据条数

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
        df = pro.fund_basic(
            market="E",
            list_status="L",
            fields="ts_code,name,management,custodian,fund_type,found_date,list_date,issue_amount,m_fee,c_fee,invest_type,type,market",
        )

        if df is None or len(df) == 0:
            logger.warning("fund_basic 返回空数据，使用上次缓存")
            return _ETF_POOL_CACHE if _ETF_POOL_CACHE else []

        for _, row in df.iterrows():
            fund_type = str(row.get("fund_type", ""))
            invest_type = str(row.get("invest_type", ""))
            name = str(row.get("name", ""))

            # 识别 ETF：name 含 "ETF" 或 invest_type 为被动指数型/ETF联接
            name_has_etf = "ETF" in name.upper()
            is_index_fund = "指数" in invest_type or "被动" in invest_type
            if not (name_has_etf or is_index_fund):
                continue

            # 跳过 REITs 和货币市场型
            if fund_type in ("REITs", "货币市场型"):
                continue

            try:
                issue_amount = float(row.get("issue_amount", 0) or 0)
            except (ValueError, TypeError):
                issue_amount = 0
            # issue_amount 单位为亿份，近似作为规模（亿），不做精确过滤
            if issue_amount < MIN_FUND_SIZE_BILLION:
                continue

            try:
                mgmt_fee = float(row.get("m_fee", 0) or 0)
            except (ValueError, TypeError):
                mgmt_fee = 0
            try:
                cust_fee = float(row.get("c_fee", 0) or 0)
            except (ValueError, TypeError):
                cust_fee = 0

            pool.append(
                {
                    "ts_code": str(row["ts_code"]),
                    "name": name,
                    "fund_size": issue_amount,
                    "management_fee": mgmt_fee,
                    "custodian_fee": cust_fee,
                    "expense_ratio": mgmt_fee + cust_fee,
                }
            )

        logger.info("ETF 池加载完成: %d 只", len(pool))
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
        df = pro.fund_nav(nav_date=trade_date)

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


def fetch_multi_day_etf_daily(
    trade_date: str | None = None,
) -> dict[str, dict]:
    """获取多日 ETF 行情数据，用于因子计算（动量、波动率等）

    通过逐日调用 fund_daily 构建 per-ETF 的收盘价和成交额时间序列。

    参数:
        trade_date: 参考日期 YYYYMMDD，从该日期往前回溯，默认今天

    返回:
        dict[ts_code, {"close": [float], "amount": [float]}]
        日期按升序排列，仅包含至少 _MULTI_DAY_MIN_BARS 个交易日数据的 ETF
    """
    pro = _get_pro_api()

    if trade_date:
        end = datetime.strptime(trade_date, "%Y%m%d").date()
    else:
        end = date.today()

    # 收集: {ts_code: [(trade_date, close, amount), ...]}
    raw: dict[str, list[tuple[str, float, float]]] = {}
    trading_days = 0

    for offset in range(_MULTI_DAY_MAX_CALENDAR):
        td = (end - timedelta(days=offset)).strftime("%Y%m%d")
        try:
            df = pro.fund_daily(trade_date=td)
        except Exception:
            time.sleep(_MULTI_DAY_SLEEP)
            continue

        if df is None or len(df) == 0:
            continue

        trading_days += 1
        for _, row in df.iterrows():
            ts_code = str(row["ts_code"])
            close_val = float(row.get("close", 0) or 0)
            amount_val = float(row.get("amount", 0) or 0)

            if ts_code not in raw:
                raw[ts_code] = []
            raw[ts_code].append((td, close_val, amount_val))

        time.sleep(_MULTI_DAY_SLEEP)

    logger.info(
        "多日 ETF 数据: %d 个交易日, %d 只基金 (%s ~ %s)",
        trading_days,
        len(raw),
        (end - timedelta(days=_MULTI_DAY_MAX_CALENDAR)).strftime("%Y%m%d"),
        end.strftime("%Y%m%d"),
    )

    # 按日期升序排列，过滤数据不足的基金
    result: dict[str, dict] = {}
    for ts_code, records in raw.items():
        if len(records) < _MULTI_DAY_MIN_BARS:
            continue
        records.sort(key=lambda x: x[0])
        result[ts_code] = {
            "close": [r[1] for r in records],
            "amount": [r[2] for r in records],
        }

    return result


def build_etf_daily_snapshot(
    trade_date: str | None = None,
) -> list[dict]:
    """构建当日 ETF 快照：合并 ETF 池 + 日行情 + 净值 + 多日行情

    返回:
        list[dict] 每项包含基础信息 + 当日行情 + 多日因子数据
    """
    pool = get_etf_pool()
    if not pool:
        logger.warning("ETF 池为空")
        return []

    daily = fetch_all_etf_daily(trade_date)
    nav = fetch_etf_nav(trade_date)

    # 获取多日行情用于动量/波动率因子计算
    try:
        multi_day = fetch_multi_day_etf_daily(trade_date)
    except Exception as e:
        logger.warning("获取多日 ETF 行情失败（降级为单日）: %s", e)
        multi_day = {}

    has_daily = bool(daily)

    snapshot = []
    for info in pool:
        ts_code = info["ts_code"]

        # 构建基础行
        row = dict(info)
        if has_daily and ts_code in daily:
            row.update(daily[ts_code])

        # 覆盖为多日时间序列（因子计算需要 20+ 数据点）
        md = multi_day.get(ts_code)
        if md:
            row["close"] = md["close"]
            row["amount"] = md["amount"]
        elif has_daily and ts_code in daily:
            # 单日数据降级为单元素列表（score_etf 会因数据不足跳过）
            row["close"] = (
                [row["close"]] if isinstance(row.get("close"), (int, float)) else []
            )
            row["amount"] = (
                [row["amount"]] if isinstance(row.get("amount"), (int, float)) else []
            )
        else:
            row["close"] = []
            row["amount"] = []

        # 如果没有多日数据且没有当日数据，跳过
        if not isinstance(row["close"], list) or len(row["close"]) == 0:
            continue

        # 合并净值计算折溢价
        nav_val = nav.get(ts_code)
        if nav_val and nav_val > 0:
            latest_close = float(row["close"][-1]) if row["close"] else 0
            if latest_close > 0:
                row["nav"] = nav_val
                row["premium_discount"] = (latest_close - nav_val) / nav_val * 100
            else:
                row["nav"] = 0
                row["premium_discount"] = 0
        else:
            row["nav"] = 0
            row["premium_discount"] = 0

        snapshot.append(row)

    logger.info(
        "ETF 快照构建完成: trade_date=%s, count=%d (daily_had_data=%s)",
        trade_date or "today",
        len(snapshot),
        has_daily,
    )
    return snapshot
