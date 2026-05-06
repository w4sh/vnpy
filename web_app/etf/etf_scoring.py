"""ETF 评分与排名引擎

职责:
1. 截面百分位归一化 — 8 因子
2. 技术分计算 — 因子加权和
3. 绩效分计算 — 夏普 0.5 + 总收益 0.3 + 最大回撤 0.2
4. 综合分计算 — 技术分 × 0.5 + 绩效分 × 0.5
5. 排名 + DB 存储

与 candidate/scoring.py 管道模式一致，但使用 ETF 专属因子和权重。
"""

from __future__ import annotations

import logging
from datetime import date

import numpy as np

from web_app.candidate.backtest import cross_sectional_rank
from web_app.etf.etf_types import EtfCandidateResult
from web_app.models import EtfCandidate, get_db_session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 可调整参数
# ---------------------------------------------------------------------------

TECHNICAL_WEIGHT = 0.5
PERFORMANCE_WEIGHT = 0.5

PERF_WEIGHTS = {
    "sharpe": 0.50,
    "total_return": 0.30,
    "max_drawdown": 0.20,
}

FACTOR_WEIGHTS = {
    "liquidity": 0.20,
    "size": 0.15,
    "cost": 0.10,
    "tracking": 0.10,
    "premium": 0.05,
    "yield": 0.10,
    "momentum": 0.20,
    "volatility": 0.10,
}

MIN_RESULTS_FOR_NORMALIZE = 3

# ---------------------------------------------------------------------------
# 归一化
# ---------------------------------------------------------------------------


def _normalize_factors(results: list[EtfCandidateResult]) -> None:
    """截面百分位归一化 — 8 个因子

    注意: cost, premium, tracking 是越低越好，需反向归一化。
    volatility 也是越低越好。
    """
    if len(results) < MIN_RESULTS_FOR_NORMALIZE:
        return

    liq_arr = np.array([r.avg_daily_volume for r in results])
    size_arr = np.array([r.fund_size for r in results])
    cost_arr = np.array([r.expense_ratio for r in results])
    track_arr = np.array([r.tracking_error for r in results])
    prem_arr = np.array([abs(r.premium_discount) for r in results])
    yield_arr = np.array([r.dividend_yield for r in results])
    mom_arr = np.array([r.raw_momentum for r in results])
    vol_arr = np.array([r.raw_volatility for r in results])

    # 越高越好
    liq_norm = cross_sectional_rank(liq_arr, higher_is_better=True)
    size_norm = cross_sectional_rank(size_arr, higher_is_better=True)
    yield_norm = cross_sectional_rank(yield_arr, higher_is_better=True)
    mom_norm = cross_sectional_rank(mom_arr, higher_is_better=True)

    # 越低越好（费率、跟踪误差、折溢价绝对值、波动率）
    cost_norm = cross_sectional_rank(cost_arr, higher_is_better=False)
    track_norm = cross_sectional_rank(track_arr, higher_is_better=False)
    prem_norm = cross_sectional_rank(prem_arr, higher_is_better=False)
    vol_norm = cross_sectional_rank(vol_arr, higher_is_better=False)

    for i, r in enumerate(results):
        r.liquidity_score = round(float(liq_norm[i]), 2)
        r.size_score = round(float(size_norm[i]), 2)
        r.cost_score = round(float(cost_norm[i]), 2)
        r.tracking_score = round(float(track_norm[i]), 2)
        r.premium_score = round(float(prem_norm[i]), 2)
        r.yield_score = round(float(yield_norm[i]), 2)
        r.momentum_score = round(float(mom_norm[i]), 2)
        r.volatility_score = round(float(vol_norm[i]), 2)


# ---------------------------------------------------------------------------
# 技术分
# ---------------------------------------------------------------------------


def _compute_technical_score(results: list[EtfCandidateResult]) -> None:
    """因子分加权合成技术分"""
    for r in results:
        score = (
            r.liquidity_score * FACTOR_WEIGHTS["liquidity"]
            + r.size_score * FACTOR_WEIGHTS["size"]
            + r.cost_score * FACTOR_WEIGHTS["cost"]
            + r.tracking_score * FACTOR_WEIGHTS["tracking"]
            + r.premium_score * FACTOR_WEIGHTS["premium"]
            + r.yield_score * FACTOR_WEIGHTS["yield"]
            + r.momentum_score * FACTOR_WEIGHTS["momentum"]
            + r.volatility_score * FACTOR_WEIGHTS["volatility"]
        )
        r.technical_score = round(score, 2)


# ---------------------------------------------------------------------------
# 绩效分
# ---------------------------------------------------------------------------


def _compute_performance_score(results: list[EtfCandidateResult]) -> None:
    """绩效分：夏普 0.5 + 收益 0.3 + 回撤 0.2，均做截面百分位归一化"""
    if len(results) < MIN_RESULTS_FOR_NORMALIZE:
        for r in results:
            r.performance_score = 0.0
        return

    sharpe_arr = np.array([r.sharpe_ratio for r in results])
    ret_arr = np.array([r.total_return for r in results])
    dd_arr = np.array([r.max_drawdown for r in results])

    sharpe_rank = cross_sectional_rank(sharpe_arr, higher_is_better=True)
    ret_rank = cross_sectional_rank(ret_arr, higher_is_better=True)
    dd_rank = cross_sectional_rank(dd_arr, higher_is_better=True)

    for i, r in enumerate(results):
        r.performance_score = round(
            float(sharpe_rank[i]) * PERF_WEIGHTS["sharpe"]
            + float(ret_rank[i]) * PERF_WEIGHTS["total_return"]
            + float(dd_rank[i]) * PERF_WEIGHTS["max_drawdown"],
            2,
        )


# ---------------------------------------------------------------------------
# 综合分 + 排名
# ---------------------------------------------------------------------------


def _compute_combined_score(results: list[EtfCandidateResult]) -> None:
    for r in results:
        r.combined_score = round(
            r.technical_score * TECHNICAL_WEIGHT
            + r.performance_score * PERFORMANCE_WEIGHT,
            2,
        )


def _assign_ranks(
    results: list[EtfCandidateResult], top_n: int
) -> list[EtfCandidateResult]:
    results.sort(key=lambda x: x.combined_score, reverse=True)
    top = results[:top_n]
    for i, r in enumerate(top):
        r.rank = i + 1
    return top


# ---------------------------------------------------------------------------
# 管道函数
# ---------------------------------------------------------------------------


def _score_pipeline(
    results: list[EtfCandidateResult],
    top_n: int,
) -> list[EtfCandidateResult]:
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
    results: list[EtfCandidateResult],
    top_n: int = 30,
) -> list[EtfCandidateResult]:
    """ETF 评分排名 — 8 因子加权"""
    return _score_pipeline(results, top_n)


# ---------------------------------------------------------------------------
# DB 存储
# ---------------------------------------------------------------------------


def save_results_to_db(
    results: list[EtfCandidateResult],
    screening_date: date,
    session=None,
) -> None:
    """将排名结果存入 EtfCandidate 表（幂等：先删当日再插入）"""
    close_session = False
    if session is None:
        session = get_db_session()
        close_session = True

    try:
        # 先删当日已有数据（幂等）
        session.query(EtfCandidate).filter(
            EtfCandidate.screening_date == screening_date
        ).delete()
        session.flush()

        for r in results:
            candidate = EtfCandidate(
                ts_code=r.ts_code,
                name=r.name,
                fund_size=r.fund_size if r.fund_size else None,
                expense_ratio=r.expense_ratio if r.expense_ratio else None,
                avg_daily_volume=r.avg_daily_volume if r.avg_daily_volume else None,
                premium_discount=r.premium_discount if r.premium_discount else None,
                dividend_yield=r.dividend_yield if r.dividend_yield else None,
                liquidity_score=r.liquidity_score if r.liquidity_score else None,
                size_score=r.size_score if r.size_score else None,
                cost_score=r.cost_score if r.cost_score else None,
                yield_score=r.yield_score if r.yield_score else None,
                momentum_score=r.momentum_score if r.momentum_score else None,
                volatility_score=r.volatility_score if r.volatility_score else None,
                technical_score=r.technical_score if r.technical_score else None,
                performance_score=r.performance_score if r.performance_score else None,
                combined_score=r.combined_score,
                rank=r.rank,
                screening_date=screening_date,
                current_price=r.current_price if r.current_price else None,
                total_return=r.total_return if r.total_return else None,
                max_drawdown=r.max_drawdown if r.max_drawdown else None,
                sharpe_ratio=r.sharpe_ratio if r.sharpe_ratio else None,
                annual_volatility=r.annual_volatility if r.annual_volatility else None,
            )
            session.add(candidate)

        session.commit()
        logger.info(
            "已保存 %d 条 ETF 候选数据到数据库 (date=%s)", len(results), screening_date
        )
    except Exception as e:
        logger.error("保存 ETF 结果失败: %s", e)
        session.rollback()
        raise
    finally:
        if close_session:
            session.close()
