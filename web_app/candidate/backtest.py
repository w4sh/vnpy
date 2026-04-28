"""Historical backtest performance metrics for a single stock.

Vectorized calculations using only numpy, no pandas/scipy required.
"""

import numpy as np


def calculate_backtest_metrics(
    prices: np.ndarray,
    dates: np.ndarray,
) -> dict:
    """Compute core backtest metrics from a series of daily close prices.

    Parameters
    ----------
    prices : np.ndarray
        1-D array of daily close prices, most recent last.
    dates : np.ndarray
        1-D array of corresponding dates (unused in calculations but
        accepted for caller convenience).

    Returns
    -------
    dict
        Keys: total_return, annual_return, max_drawdown, sharpe_ratio.
    """
    if len(prices) < 2:
        return {
            "total_return": 0.0,
            "annual_return": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
        }

    # Total return
    total_return = float(prices[-1] / prices[0] - 1)

    # Annualized return
    n_days = len(prices)
    annual_return = (1 + total_return) ** (252 / n_days) - 1
    # Clamp to reasonable range [-1, 10] (i.e. -100% to +1000%)
    annual_return = float(np.clip(annual_return, -1.0, 10.0))

    # Max drawdown (always negative, e.g. -0.15 means 15% drawdown)
    cumulative_max = np.maximum.accumulate(prices)
    drawdowns = (prices - cumulative_max) / cumulative_max
    max_drawdown = float(np.min(drawdowns))

    # Annualized Sharpe ratio (0 risk-free rate)
    daily_returns = np.diff(prices) / prices[:-1]
    daily_mean = np.mean(daily_returns)
    daily_std = np.std(daily_returns, ddof=1)
    if daily_std == 0:
        sharpe_ratio = 0.0
    else:
        sharpe_ratio = float(daily_mean / daily_std * np.sqrt(252))

    return {
        "total_return": round(total_return, 6),
        "annual_return": round(annual_return, 6),
        "max_drawdown": round(max_drawdown, 6),
        "sharpe_ratio": round(sharpe_ratio, 6),
    }


def normalize_score(values: np.ndarray) -> np.ndarray:
    """Min-max normalize an array to a 0-100 scale.

    If all values are identical, returns an array of zeros.

    Parameters
    ----------
    values : np.ndarray
        Raw numeric values.

    Returns
    -------
    np.ndarray
        Normalized values in [0, 100].
    """
    v_min = np.min(values)
    v_max = np.max(values)
    if v_max == v_min:
        return np.zeros_like(values, dtype=float)
    return (values - v_min) / (v_max - v_min) * 100.0
