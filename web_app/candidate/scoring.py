"""评分与排名引擎

职责:
1. 截面百分位归一化 — 4 因子
2. 技术分计算 — 等权合成
3. 绩效分计算 — 夏普 0.5 + 回撤 0.3 + 总收益 0.2
4. 综合分计算 — 技术分 × 0.5 + 绩效分 × 0.5
5. 排名 + DB 存储
"""

from __future__ import annotations

import logging
from datetime import date

import numpy as np

from web_app.candidate.candidate_types import CandidateResult
from web_app.candidate.engine import FACTOR_WEIGHTS
from web_app.candidate.backtest import cross_sectional_rank
from web_app.models import CandidateStock, get_db_session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 可调整参数
# ---------------------------------------------------------------------------

TECHNICAL_WEIGHT = 0.5
PERFORMANCE_WEIGHT = 0.5

PERF_WEIGHTS = {
    "sharpe": 0.50,
    "max_drawdown": 0.30,
    "total_return": 0.20,
}

MIN_RESULTS_FOR_NORMALIZE = 3


# ---------------------------------------------------------------------------
# 归一化
# ---------------------------------------------------------------------------


def _normalize_factors(results: list[CandidateResult]) -> None:
    """截面百分位归一化 — 4 个技术因子"""
    if len(results) < MIN_RESULTS_FOR_NORMALIZE:
        return

    m_arr = np.array([r.raw_momentum for r in results])
    t_arr = np.array([r.raw_trend for r in results])
    v_arr = np.array([r.raw_volume for r in results])
    vl_arr = np.array([r.raw_volatility for r in results])

    m_norm = cross_sectional_rank(m_arr)
    t_norm = cross_sectional_rank(t_arr)
    v_norm = cross_sectional_rank(v_arr)
    vl_norm = cross_sectional_rank(vl_arr)

    for i, r in enumerate(results):
        r.momentum_score = round(float(m_norm[i]), 2)
        r.trend_score = round(float(t_norm[i]), 2)
        r.volume_score = round(float(v_norm[i]), 2)
        r.volatility_score = round(float(vl_norm[i]), 2)


# ---------------------------------------------------------------------------
# 技术分
# ---------------------------------------------------------------------------


def _compute_technical_score(results: list[CandidateResult]) -> None:
    """因子分合成技术分"""
    for r in results:
        r.technical_score = round(
            r.momentum_score * FACTOR_WEIGHTS["momentum"]
            + r.trend_score * FACTOR_WEIGHTS["trend"]
            + r.volume_score * FACTOR_WEIGHTS["volume"]
            + r.volatility_score * FACTOR_WEIGHTS["volatility"],
            2,
        )


# ---------------------------------------------------------------------------
# 绩效分
# ---------------------------------------------------------------------------


def _compute_performance_score(results: list[CandidateResult]) -> None:
    """绩效分：夏普 0.5 + 回撤 0.3 + 总收益 0.2，均做截面百分位归一化"""
    if len(results) < MIN_RESULTS_FOR_NORMALIZE:
        for r in results:
            r.performance_score = 0.0
        return

    sharpe_arr = np.array([r.sharpe_ratio for r in results])
    dd_arr = np.array([r.max_drawdown for r in results])
    ret_arr = np.array([r.total_return for r in results])

    sharpe_rank = cross_sectional_rank(sharpe_arr, higher_is_better=True)
    dd_rank = cross_sectional_rank(dd_arr, higher_is_better=False)
    ret_rank = cross_sectional_rank(ret_arr, higher_is_better=True)

    for i, r in enumerate(results):
        r.performance_score = round(
            float(sharpe_rank[i]) * PERF_WEIGHTS["sharpe"]
            + float(dd_rank[i]) * PERF_WEIGHTS["max_drawdown"]
            + float(ret_rank[i]) * PERF_WEIGHTS["total_return"],
            2,
        )


# ---------------------------------------------------------------------------
# 综合分 + 排名
# ---------------------------------------------------------------------------


def _compute_combined_score(results: list[CandidateResult]) -> None:
    for r in results:
        r.combined_score = round(
            r.technical_score * TECHNICAL_WEIGHT
            + r.performance_score * PERFORMANCE_WEIGHT,
            2,
        )


def _assign_ranks(results: list[CandidateResult], top_n: int) -> list[CandidateResult]:
    results.sort(key=lambda x: x.combined_score, reverse=True)
    top = results[:top_n]
    for i, r in enumerate(top):
        r.rank = i + 1
    return top


# ---------------------------------------------------------------------------
# 管道函数
# ---------------------------------------------------------------------------


def _score_pipeline(
    results: list[CandidateResult],
    top_n: int,
) -> list[CandidateResult]:
    """对一组结果执行完整评分管道"""
    if not results:
        return []

    _normalize_factors(results)
    _compute_technical_score(results)
    _compute_performance_score(results)
    _compute_combined_score(results)

    return _assign_ranks(results, top_n)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def score_and_rank(
    results: list[CandidateResult],
    top_n: int = 20,
) -> list[CandidateResult]:
    """单榜评分排名 — 4 因子等权"""
    return _score_pipeline(results, top_n)


# ---------------------------------------------------------------------------
# DB 存储
# ---------------------------------------------------------------------------


def save_results_to_db(
    results: list[CandidateResult],
    screening_date: date,
    session=None,
) -> None:
    """将排名结果存入 CandidateStock 表"""
    close_session = False
    if session is None:
        session = get_db_session()
        close_session = True

    try:
        for r in results:
            candidate = CandidateStock(
                symbol=r.symbol,
                name=r.name,
                score=r.combined_score,
                technical_score=r.technical_score,
                performance_score=r.performance_score,
                combined_score=r.combined_score,
                rank=r.rank,
                screening_date=screening_date,
                momentum_score=r.momentum_score,
                trend_score=r.trend_score,
                volume_score=r.volume_score,
                volatility_score=r.volatility_score,
                current_price=r.current_price,
                total_return=r.total_return,
                max_drawdown=r.max_drawdown,
                sharpe_ratio=r.sharpe_ratio,
            )
            session.add(candidate)

        session.commit()
        logger.info(f"已保存 {len(results)} 条候选股推荐到数据库")
    except Exception as e:
        logger.error(f"保存结果失败: {e}")
        session.rollback()
        raise
    finally:
        if close_session:
            session.close()
