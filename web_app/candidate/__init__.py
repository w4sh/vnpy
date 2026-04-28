"""候选股推荐模块

提供每日自动筛选 + 回测绩效指标的计算能力。
"""

from web_app.candidate.screening_engine import (
    run_screening,
    run_daily_screening,
    save_results_to_db,
    fetch_daily_data,
    fetch_all_stocks_data,
    get_recent_trade_dates,
    STOCK_POOL,
    FACTOR_WEIGHTS,
)
from web_app.candidate.backtest import (
    calculate_backtest_metrics,
    normalize_score,
)

__all__ = [
    "run_screening",
    "run_daily_screening",
    "save_results_to_db",
    "fetch_daily_data",
    "fetch_all_stocks_data",
    "get_recent_trade_dates",
    "calculate_backtest_metrics",
    "normalize_score",
    "STOCK_POOL",
    "FACTOR_WEIGHTS",
]
