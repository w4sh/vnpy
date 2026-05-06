"""候选股推荐模块

提供每日自动筛选 + 回测绩效指标的计算能力。
"""

from web_app.candidate.engine import (
    STOCK_POOL,
    FACTOR_WEIGHTS,
    fetch_all_stocks_data,
    fetch_daily_data,
    get_recent_trade_dates,
)
from web_app.candidate.screening_engine import (
    run_daily_screening,
    run_screening,
)
from web_app.candidate.scoring import (
    score_and_rank,
    save_results_to_db,
)
from web_app.candidate.backtest import (
    calculate_backtest_metrics,
    cross_sectional_rank,
    normalize_score,
)
from web_app.candidate.candidate_types import CandidateResult

__all__ = [
    "run_screening",
    "run_daily_screening",
    "score_and_rank",
    "save_results_to_db",
    "fetch_daily_data",
    "fetch_all_stocks_data",
    "get_recent_trade_dates",
    "calculate_backtest_metrics",
    "cross_sectional_rank",
    "normalize_score",
    "CandidateResult",
    "STOCK_POOL",
    "FACTOR_WEIGHTS",
]
