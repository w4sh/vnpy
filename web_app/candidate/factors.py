"""技术因子计算引擎

四个经典技术因子：
- 动量 (momentum): 5/10/20 日收益率加权
- 趋势 (trend): 价格相对均线位置 + 均线多头排列
- 量能 (volume): 5/20 日均量比值
- 波动 (volatility): 布林带位置 + ATR 波动率

输出原始因子值（未经归一化），由 scoring.py 统一做截面标准化。
"""

from __future__ import annotations

import logging

import numpy as np

from web_app.candidate.candidate_types import CandidateResult
from web_app.candidate.engine import MIN_BARS_REQUIRED
from web_app.candidate.backtest import calculate_backtest_metrics
from web_app.stock_names import get_stock_name

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 因子计算函数
# ---------------------------------------------------------------------------


def calc_momentum(close_arr: np.ndarray) -> float:
    """动量因子：5/10/20 日收益率加权"""
    if len(close_arr) < 21:
        return 0.0

    ret_5d = close_arr[-1] / close_arr[-6] - 1
    ret_10d = close_arr[-1] / close_arr[-11] - 1
    ret_20d = close_arr[-1] / close_arr[-21] - 1

    return float(ret_5d * 0.5 + ret_10d * 0.3 + ret_20d * 0.2)


def calc_trend(close_arr: np.ndarray) -> float:
    """趋势因子：价格相对 5/10/20/60 均线位置 + 均线排列"""
    if len(close_arr) < 60:
        return 0.0

    price = close_arr[-1]
    mas = {
        "ma5": np.mean(close_arr[-5:]),
        "ma10": np.mean(close_arr[-10:]),
        "ma20": np.mean(close_arr[-20:]),
        "ma60": np.mean(close_arr[-60:]),
    }

    deviations = [(price / v - 1) for v in mas.values()]

    alignment = 0
    if mas["ma5"] > mas["ma10"]:
        alignment += 1
    if mas["ma10"] > mas["ma20"]:
        alignment += 1
    if mas["ma20"] > mas["ma60"]:
        alignment += 1

    avg_dev = np.mean(deviations) * 100
    return float(max(-10, min(10, avg_dev)) * 5 + alignment * 10 + 50)


def calc_volume(volume_arr: np.ndarray) -> float:
    """量能因子：5 日均量 / 20 日均量"""
    if len(volume_arr) < 20:
        return 0.0

    vol_5 = np.mean(volume_arr[-5:])
    vol_20 = np.mean(volume_arr[-20:])

    if vol_20 == 0:
        return 0.0

    ratio = vol_5 / vol_20
    return float(50 + (ratio - 1) * 30)


def calc_volatility(close_arr: np.ndarray) -> float:
    """波动率因子：布林带位置 + ATR 波动评估"""
    if len(close_arr) < 20:
        return 0.0

    recent = close_arr[-20:]
    ma = np.mean(recent)
    std = np.std(recent)

    if ma == 0:
        return 0.0

    price = close_arr[-1]
    upper = ma + 2 * std
    lower = ma - 2 * std

    if upper - lower > 0:
        bb_pos = (price - ma) / (upper - lower)
    else:
        bb_pos = 0.0

    bb_score = bb_pos * 40 + 50

    atr = np.mean(np.abs(np.diff(recent))) / ma * 100

    if atr < 1.0:
        atr_score = 25
    elif atr < 2.5:
        atr_score = 30 - (atr - 1.0) * 10
    elif atr < 5.0:
        atr_score = 15 - (atr - 2.5) * 4
    else:
        atr_score = 0

    return float(bb_score * 0.6 + atr_score * 0.4)


# ---------------------------------------------------------------------------
# 单只股票打分入口
# ---------------------------------------------------------------------------


def score_stock(data: dict) -> CandidateResult | None:
    """对单只股票计算因子 + 回测绩效

    输入:
        data: engine.py 产的 OHLCV dict
    输出: CandidateResult（原始因子值 + 绩效指标）
    """
    symbol = data["symbol"]
    close_arr = np.array(data["close"], dtype=np.float64)
    volume_arr = np.array(data["volume"], dtype=np.float64)
    dates_arr = np.array(data["dates"])

    if len(close_arr) < MIN_BARS_REQUIRED:
        return None

    backtest = calculate_backtest_metrics(close_arr, dates_arr)

    return CandidateResult(
        symbol=symbol,
        name=get_stock_name(symbol),
        raw_momentum=round(calc_momentum(close_arr), 6),
        raw_trend=round(calc_trend(close_arr), 6),
        raw_volume=round(calc_volume(volume_arr), 6),
        raw_volatility=round(calc_volatility(close_arr), 6),
        current_price=round(float(close_arr[-1]), 2),
        total_return=round(backtest["total_return"], 4),
        max_drawdown=round(backtest["max_drawdown"], 4),
        sharpe_ratio=round(backtest["sharpe_ratio"], 4),
    )
