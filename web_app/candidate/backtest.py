"""回测绩效指标计算 + 截面百分位归一化"""

import numpy as np


def calculate_backtest_metrics(
    prices: np.ndarray,
    dates: np.ndarray,
) -> dict:
    """Compute core backtest metrics from daily close prices.

    Parameters
    ----------
    prices : np.ndarray
        1-D array of daily close prices, most recent last.
    dates : np.ndarray
        1-D array of corresponding dates.

    Returns
    -------
    dict
        Keys: total_return, max_drawdown, sharpe_ratio.
    """
    if len(prices) < 2:
        return {
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
        }

    total_return = float(prices[-1] / prices[0] - 1)

    cumulative_max = np.maximum.accumulate(prices)
    drawdowns = (prices - cumulative_max) / cumulative_max
    max_drawdown = float(np.min(drawdowns))

    daily_returns = np.diff(prices) / prices[:-1]
    daily_mean = np.mean(daily_returns)
    daily_std = np.std(daily_returns, ddof=1)
    if daily_std == 0:
        sharpe_ratio = 0.0
    else:
        sharpe_ratio = float(daily_mean / daily_std * np.sqrt(252))

    return {
        "total_return": round(total_return, 6),
        "max_drawdown": round(max_drawdown, 6),
        "sharpe_ratio": round(sharpe_ratio, 6),
    }


def normalize_score(values: np.ndarray) -> np.ndarray:
    """Min-max normalize to [0, 100] (legacy, will be replaced by cross_sectional_rank)."""
    v_min = np.min(values)
    v_max = np.max(values)
    if v_max == v_min:
        return np.zeros_like(values, dtype=float)
    return (values - v_min) / (v_max - v_min) * 100.0


def cross_sectional_rank(
    values: np.ndarray, higher_is_better: bool = True
) -> np.ndarray:
    """截面百分位排名 → [0, 100]

    当 higher_is_better=True:   值越大 → 分数越高
    当 higher_is_better=False:  值越小 → 分数越高（用于回撤等反向指标）

    参考: Fama-French (1992) portfolio sort, Barra 风险模型标准化层
    """
    if len(values) < 2:
        return np.zeros_like(values, dtype=float)

    if np.std(values) < 1e-12:
        return np.full_like(values, 50.0, dtype=float)

    if higher_is_better:
        ranks = np.argsort(np.argsort(values))
    else:
        ranks = np.argsort(np.argsort(-values))

    n = len(values)
    return ranks.astype(float) / (n - 1) * 100.0
