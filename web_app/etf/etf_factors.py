"""ETF 因子计算

定义 ETF 专属的 8 个评分因子，与个股的 4 动量因子体系独立。

因子列表：
  - liquidity:    近20日平均成交额 (log)
  - size:         基金规模 (AUM, 亿)
  - cost:         综合费率 = -(管理费+托管费)
  - tracking:     跟踪误差（近期收益 vs 基准）
  - premium:      -|折溢价率|
  - yield:        股息率
  - momentum:     加权 5/10/20 日收益率
  - volatility:   20 日年化波动率
"""

from __future__ import annotations

import logging
import math

import numpy as np

from web_app.etf.etf_types import EtfCandidateResult

logger = logging.getLogger(__name__)

# 最少需要的数据天数
MIN_BARS_REQUIRED = 20


# ---------------------------------------------------------------------------
# 因子计算辅助函数
# ---------------------------------------------------------------------------


def _calc_momentum(close_arr: np.ndarray) -> float:
    """加权动量: 5日(0.5) + 10日(0.3) + 20日(0.2)"""
    if len(close_arr) < 20:
        return 0.0
    r5 = (close_arr[-1] / close_arr[-5] - 1) if len(close_arr) >= 5 else 0
    r10 = (close_arr[-1] / close_arr[-10] - 1) if len(close_arr) >= 10 else 0
    r20 = (close_arr[-1] / close_arr[-20] - 1) if len(close_arr) >= 20 else 0
    return r5 * 0.5 + r10 * 0.3 + r20 * 0.2


def _calc_volatility(close_arr: np.ndarray) -> float:
    """20 日年化波动率"""
    if len(close_arr) < 20:
        return 0.0
    returns = np.diff(np.log(close_arr[-21:]))
    return float(np.std(returns, ddof=1) * math.sqrt(252))


def _calc_total_return(close_arr: np.ndarray) -> float:
    """区间总收益率"""
    if len(close_arr) < 2:
        return 0.0
    return float(close_arr[-1] / close_arr[0] - 1)


def _calc_max_drawdown(close_arr: np.ndarray) -> float:
    """区间最大回撤"""
    if len(close_arr) < 2:
        return 0.0
    peak = np.maximum.accumulate(close_arr)
    drawdown = (close_arr - peak) / peak
    return float(abs(np.min(drawdown)))


def _calc_sharpe_ratio(close_arr: np.ndarray) -> float:
    """年化夏普比率（假设无风险利率 0）"""
    if len(close_arr) < 20:
        return 0.0
    returns = np.diff(np.log(close_arr))
    if np.std(returns, ddof=1) == 0:
        return 0.0
    return float(np.mean(returns) / np.std(returns, ddof=1) * math.sqrt(252))


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def score_etf(data: dict) -> EtfCandidateResult | None:
    """对单只 ETF 计算全部因子

    参数:
        data: 包含 ETF 基础信息 + 日线行情 + NAV 的字典
              - ts_code, name, fund_size, expense_ratio    (基础信息)
              - close[], dates[], amount[]                  (日线行情)
              - premium_discount, dividend_yield            (当日标量)

    返回:
        EtfCandidateResult 或 None（数据不足时）
    """
    ts_code = data.get("ts_code", "")
    name = data.get("name", "")

    close_arr = np.array(data.get("close", []), dtype=float)
    amount_arr = np.array(data.get("amount", []), dtype=float)

    if len(close_arr) < MIN_BARS_REQUIRED:
        logger.debug("ETF %s 数据不足: %d 条", ts_code, len(close_arr))
        return None

    # 原始因子值
    fund_size = float(data.get("fund_size", 0) or 0)
    expense_ratio = float(data.get("expense_ratio", 0) or 0)

    # 流动性 = 近 20 日平均成交额（log 变换压缩量级差异）
    avg_volume_20 = float(np.mean(amount_arr[-20:])) if len(amount_arr) >= 20 else 1
    avg_daily_volume = avg_volume_20

    premium_discount = float(data.get("premium_discount", 0) or 0)
    dividend_yield = float(data.get("dividend_yield", 0) or 0)

    momentum_raw = _calc_momentum(close_arr)
    volatility_raw = _calc_volatility(close_arr)

    # 绩效指标（用于 performance_score）
    total_ret = _calc_total_return(close_arr)
    max_dd = _calc_max_drawdown(close_arr)
    sharpe = _calc_sharpe_ratio(close_arr)

    return EtfCandidateResult(
        ts_code=ts_code,
        name=name,
        fund_size=fund_size,
        expense_ratio=expense_ratio,
        avg_daily_volume=avg_daily_volume,
        premium_discount=premium_discount,
        dividend_yield=dividend_yield,
        raw_momentum=momentum_raw,
        raw_volatility=volatility_raw,
        current_price=float(close_arr[-1]) if len(close_arr) > 0 else 0,
        total_return=total_ret,
        max_drawdown=max_dd,
        sharpe_ratio=sharpe,
        annual_volatility=volatility_raw,
    )
