"""投资组合推荐引擎

将每日候选股筛选的 combined_score 映射到持仓操作建议。

评分阈值（带滞回）：
  - >= 80: STRONG_BUY
  - < 58: SELL（硬阈值）
  - 58-79: 看前一日操作，若为 SELL 且评分 < 63 → 维持 SELL（滞回）
  - 其余: HOLD

仓位计算：
  - 已持仓 STRONG_BUY: 加仓当前持仓的 50%
  - SELL: 减仓当前持仓的 50%
  - 新开仓 BUY: 从可投资金中按评分比例分配（单一行业 ≤ 3 只）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 可调阈值
# ---------------------------------------------------------------------------

SCORE_STRONG_BUY = 80
SCORE_SELL = 58  # 原 60，下调 2 点减少假信号
SCORE_BUY_HYSTERESIS = 63  # 从 SELL 回升到 HOLD 需 ≥ 63
TOP_N_NON_HELD = 10
MAX_PER_INDUSTRY = 3  # 单一行业最多推荐 N 只
CASH_RESERVE_RATIO = 0.10
POSITION_ADJUST_RATIO = 0.50
DEFAULT_CAPITAL = 1_000_000  # 当没有策略时使用默认总资金

# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------


@dataclass
class RecommendationResult:
    symbol: str
    name: str
    recommendation_type: str  # STRONG_BUY / BUY / HOLD / SELL
    combined_score: float
    current_price: float
    target_position_pct: float
    target_amount: float
    current_quantity: int
    suggested_quantity: int  # 正=加仓, 负=减仓, 0=维持
    is_held: bool
    position_id: int | None
    reason: str


# ---------------------------------------------------------------------------
# 核心逻辑
# ---------------------------------------------------------------------------


def _get_industry_for_symbol(symbol: str) -> str:
    """获取申万一级行业分类

    从行业数据 DataFrame 中查询。读取一次后缓存。
    """
    if not hasattr(_get_industry_for_symbol, "_cache"):
        try:
            from vnpy.alpha.factors.industry import get_industry_df

            df = get_industry_df()
            _get_industry_for_symbol._cache = {}
            for row in df.to_dicts():
                vt = row.get("vt_symbol", "")
                industry = row.get("industry", "")
                if vt and industry:
                    # 格式化匹配: xx.SSE → xx.SH
                    simple = vt.replace(".SSE", ".SH").replace(".SZSE", ".SZ")
                    _get_industry_for_symbol._cache[simple] = industry
                    _get_industry_for_symbol._cache[vt] = industry
        except Exception:
            _get_industry_for_symbol._cache = {}
    return _get_industry_for_symbol._cache.get(symbol, "")


def _classify_action(
    score: float | None, is_held: bool, prev_action: str | None = None
) -> str:
    """根据评分、持仓状态和前一日操作判定操作类型（带滞回）"""
    if score is None:
        if is_held:
            return "SELL"
        return "HOLD"
    if score >= SCORE_STRONG_BUY:
        return "STRONG_BUY"
    if score < SCORE_SELL:
        return "SELL"
    # 滞回: 上次为 SELL 且新分 < SCORE_BUY_HYSTERESIS → 维持 SELL
    if prev_action == "SELL" and score < SCORE_BUY_HYSTERESIS:
        return "SELL"
    return "HOLD"


def _build_reason(action: str, score: float | None, name: str) -> str:
    """生成操作原因描述"""
    if score is None:
        return f"{name}不在今日候选股评分中，建议减仓"
    if action == "STRONG_BUY":
        return f"综合评分{score:.1f}，动量+趋势+量价+波动率表现优异，建议加仓"
    if action == "SELL":
        return f"综合评分{score:.1f}，低于卖出阈值{SCORE_SELL}，建议减仓控制风险"
    return (
        f"综合评分{score:.1f}，处于持有区间"
        f"({SCORE_SELL}-{SCORE_STRONG_BUY})，建议维持当前仓位"
    )


def _get_prev_recommendations(session: Any, current_date: date) -> dict[str, str]:
    """获取前一个交易日的推荐类型，用于滞回判断

    首次运行时 PortfolioRecommendation 表可能为空或不存在，安全降级返回 {}。
    """
    from web_app.models import PortfolioRecommendation

    try:
        prev_date = current_date - timedelta(days=5)
        for d in range(1, 6):
            check_date = current_date - timedelta(days=d)
            rec = (
                session.query(PortfolioRecommendation.recommendation_date)
                .filter(PortfolioRecommendation.recommendation_date == check_date)
                .first()
            )
            if rec:
                prev_date = check_date
                break
        else:
            return {}

        prev_recs = (
            session.query(PortfolioRecommendation)
            .filter(PortfolioRecommendation.recommendation_date == prev_date)
            .all()
        )
        return {r.symbol: r.recommendation_type for r in prev_recs}
    except Exception:
        logger.debug("无法获取前一日推荐（首次运行或表不存在），滞回降级为纯阈值判断")
        return {}


def _calculate_sizing(
    recommendations: list[RecommendationResult],
    total_capital: float,
    total_market_value: float,
) -> None:
    """计算每只推荐股票的仓位

    对 SELL：减半仓
    对 STRONG_BUY（已持仓）：加仓当前持仓的 50%
    对 BUY（未持仓新开仓）：从可投资金中按评分比例分配
    """
    investable = total_capital * (1 - CASH_RESERVE_RATIO) - total_market_value
    investable = max(investable, 0.0)

    # 新开仓买入（未持仓）
    new_buys = [
        r
        for r in recommendations
        if r.recommendation_type in ("STRONG_BUY", "BUY") and not r.is_held
    ]
    total_buy_score = sum(r.combined_score for r in new_buys if r.combined_score)

    for r in recommendations:
        if r.recommendation_type == "SELL":
            r.suggested_quantity = (
                -int(r.current_quantity * POSITION_ADJUST_RATIO / 100) * 100
            )
            r.target_amount = 0
            r.target_position_pct = 0

        elif r.recommendation_type == "STRONG_BUY" and r.is_held:
            add_qty = int(r.current_quantity * POSITION_ADJUST_RATIO / 100) * 100
            r.suggested_quantity = add_qty
            r.target_amount = add_qty * r.current_price if r.current_price > 0 else 0
            r.target_position_pct = (
                r.target_amount / total_capital if total_capital > 0 else 0
            )

        elif r.recommendation_type in ("STRONG_BUY", "BUY") and not r.is_held:
            if total_buy_score > 0 and r.combined_score > 0 and investable > 0:
                weight = r.combined_score / total_buy_score
                r.target_amount = weight * investable
                r.target_position_pct = (
                    weight * investable / total_capital if total_capital > 0 else 0
                )
                if r.current_price > 0:
                    r.suggested_quantity = (
                        int(r.target_amount / r.current_price / 100) * 100
                    )
            else:
                r.target_amount = 0
                r.suggested_quantity = 0

        else:
            r.suggested_quantity = 0
            r.target_amount = 0
            r.target_position_pct = 0


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def generate_recommendations(
    session: Any,
    screening_date: date | None = None,
) -> list[RecommendationResult]:
    """生成投资组合推荐

    参数:
        session: SQLAlchemy 数据库会话
        screening_date: 候选股筛选日期，默认使用最新日期

    返回:
        RecommendationResult 列表
    """
    from web_app.models import CandidateStock, Position, Strategy

    if screening_date is None:
        latest = (
            session.query(CandidateStock.screening_date)
            .order_by(CandidateStock.screening_date.desc())
            .first()
        )
        if latest is None:
            logger.warning("无候选股数据，跳过推荐生成")
            return []
        screening_date = latest[0]

    candidates: dict[str, CandidateStock] = {}
    for c in (
        session.query(CandidateStock)
        .filter(CandidateStock.screening_date == screening_date)
        .all()
    ):
        candidates[c.symbol] = c

    if not candidates:
        logger.warning("候选股数据为空 (date=%s)，跳过推荐生成", screening_date)
        return []

    held_positions = session.query(Position).filter(Position.status == "holding").all()
    held_symbols = {p.symbol for p in held_positions}

    strategies = session.query(Strategy).filter(Strategy.status == "active").all()
    total_capital = (
        sum(float(s.current_capital or s.initial_capital) for s in strategies)
        if strategies
        else DEFAULT_CAPITAL
    )
    total_market_value = sum(float(p.market_value or 0) for p in held_positions)

    # 前一日推荐（滞回判断用）
    prev_actions = _get_prev_recommendations(session, screening_date)

    results: list[RecommendationResult] = []

    # 1. 处理持仓股票
    for pos in held_positions:
        candidate = candidates.get(pos.symbol)
        score = float(candidate.combined_score) if candidate else None
        action = _classify_action(
            score, is_held=True, prev_action=prev_actions.get(pos.symbol)
        )

        results.append(
            RecommendationResult(
                symbol=pos.symbol,
                name=candidate.name if candidate else (pos.name or pos.symbol),
                recommendation_type=action,
                combined_score=score or 0,
                current_price=(
                    float(candidate.current_price)
                    if candidate
                    else (float(pos.current_price or 0))
                ),
                target_position_pct=0,
                target_amount=0,
                current_quantity=pos.quantity,
                suggested_quantity=0,
                is_held=True,
                position_id=pos.id,
                reason=_build_reason(action, score, pos.symbol),
            )
        )

    # 2. 未持仓 Top N 买入推荐（带行业分散约束）
    non_held_sorted = sorted(
        [c for c in candidates.values() if c.symbol not in held_symbols],
        key=lambda x: float(x.combined_score or 0),
        reverse=True,
    )

    selected_industries: dict[str, int] = {}
    selected_non_held: list[CandidateStock] = []
    for c in non_held_sorted:
        if len(selected_non_held) >= TOP_N_NON_HELD:
            break
        # 行业分散约束
        industry = _get_industry_for_symbol(c.symbol)
        if industry and selected_industries.get(industry, 0) >= MAX_PER_INDUSTRY:
            continue
        selected_non_held.append(c)
        if industry:
            selected_industries[industry] = selected_industries.get(industry, 0) + 1

    for c in selected_non_held:
        score = float(c.combined_score or 0)
        name = c.name or c.symbol
        results.append(
            RecommendationResult(
                symbol=c.symbol,
                name=name,
                recommendation_type=(
                    "STRONG_BUY" if score >= SCORE_STRONG_BUY else "BUY"
                ),
                combined_score=score,
                current_price=float(c.current_price or 0),
                target_position_pct=0,
                target_amount=0,
                current_quantity=0,
                suggested_quantity=0,
                is_held=False,
                position_id=None,
                reason=_build_reason(
                    "STRONG_BUY" if score >= SCORE_STRONG_BUY else "BUY",
                    score,
                    name,
                ),
            )
        )

    # 3. 计算仓位
    _calculate_sizing(results, total_capital, total_market_value)

    return results
