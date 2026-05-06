"""ETF 指数基金推荐模块

提供每日 ETF 评分排名 + 配置建议。
"""

from web_app.etf.etf_screening_engine import run_daily_etf_screening, run_etf_screening
from web_app.etf.etf_scoring import save_results_to_db, score_and_rank
from web_app.etf.etf_types import EtfCandidateResult

__all__ = [
    "run_etf_screening",
    "run_daily_etf_screening",
    "score_and_rank",
    "save_results_to_db",
    "EtfCandidateResult",
]
