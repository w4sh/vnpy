"""ETF 指数基金推荐引擎

基于每日 ETF 评分排名生成配置建议：
  - Top 5 (score >= 80)       → STRONG_BUY（核心配置）
  - Rank 6-15 (score >= 60)   → BUY（卫星配置）
  - Score < 60                → SELL（回避）
  - 其余                      → HOLD（持有观望）

仓位按评分比例从可投资金中分配。

持仓联动：
  - 已持仓 ETF 排名跌出 Top 30 → SELL 信号
  - 已持仓且排名靠前的维持推荐
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from web_app.models import EtfCandidate, Position, Strategy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 可调阈值
# ---------------------------------------------------------------------------

SCORE_STRONG_BUY = 80
SCORE_SELL = 60
TOP_N_HELD = 5  # STRONG_BUY 数量
BUY_N = 15  # 总推荐数量（含 STRONG_BUY）
RANK_OUT_SELL = 30  # 持仓 ETF 排名超过此值 → SELL
CASH_RESERVE_RATIO = 0.10
DEFAULT_CAPITAL = 1_000_000

# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------


@dataclass
class EtfRecommendationResult:
    ts_code: str
    name: str
    recommendation_type: str  # STRONG_BUY / BUY / HOLD / SELL
    combined_score: float
    current_price: float
    is_held: bool = False
    target_position_pct: float = 0.0
    target_amount: float = 0.0
    suggested_quantity: int = 0
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "ts_code": self.ts_code,
            "name": self.name,
            "recommendation_type": self.recommendation_type,
            "combined_score": self.combined_score,
            "current_price": self.current_price,
            "is_held": self.is_held,
            "target_position_pct": self.target_position_pct,
            "target_amount": self.target_amount,
            "suggested_quantity": self.suggested_quantity,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# 核心逻辑
# ---------------------------------------------------------------------------


def _classify_action_by_rank(rank: int, score: float, is_held: bool) -> str:
    """根据排名、评分和持仓状态判定操作类型"""
    # 已持仓但排名很差 → SELL
    if is_held and (rank > RANK_OUT_SELL or score < SCORE_SELL):
        return "SELL"
    if rank <= TOP_N_HELD and score >= SCORE_STRONG_BUY:
        return "STRONG_BUY"
    if score < SCORE_SELL:
        return "SELL"
    return "BUY" if rank <= BUY_N else "HOLD"


def _build_reason(action: str, name: str, score: float, rank: int) -> str:
    if action == "STRONG_BUY":
        return f"综合评分{score:.1f}，排名第{rank}，流动性好规模大，建议核心配置"
    if action == "BUY":
        return f"综合评分{score:.1f}，排名第{rank}，建议卫星配置"
    if action == "SELL":
        return f"综合评分{score:.1f}，低于卖出阈值{SCORE_SELL}，建议回避"
    return f"综合评分{score:.1f}，排名第{rank}，建议持有观望"


def _normalize_ts_code(ts_code: str) -> str:
    """统一 ts_code 格式，用于持仓匹配"""
    # "510050.SH" → "510050", "510050" → "510050"
    return ts_code.split(".")[0] if "." in ts_code else ts_code


def _calculate_sizing(
    recommendations: list[EtfRecommendationResult], total_capital: float
) -> None:
    """按评分比例分配仓位"""
    investable = total_capital * (1 - CASH_RESERVE_RATIO)
    investable = max(investable, 0.0)

    # 只对 BUY 和 STRONG_BUY 分配资金
    buys = [
        r for r in recommendations if r.recommendation_type in ("STRONG_BUY", "BUY")
    ]
    total_score = sum(r.combined_score for r in buys)

    for r in recommendations:
        if r.recommendation_type in ("STRONG_BUY", "BUY") and total_score > 0:
            weight = r.combined_score / total_score
            r.target_amount = round(weight * investable, 2)
            r.target_position_pct = round(weight, 4)
            if r.current_price > 0:
                r.suggested_quantity = (
                    int(r.target_amount / r.current_price / 100) * 100
                )
        else:
            r.target_amount = 0.0
            r.target_position_pct = 0.0
            r.suggested_quantity = 0


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def generate_etf_recommendations(
    session: Any,
    screening_date: date | None = None,
) -> list[EtfRecommendationResult]:
    """生成 ETF 投资组合推荐

    参数:
        session: SQLAlchemy 数据库会话
        screening_date: ETF 筛选日期，默认使用最新日期

    返回:
        EtfRecommendationResult 列表
    """
    if screening_date is None:
        latest = (
            session.query(EtfCandidate.screening_date)
            .order_by(EtfCandidate.screening_date.desc())
            .first()
        )
        if latest is None:
            logger.warning("无 ETF 候选数据，跳过推荐生成")
            return []
        screening_date = latest[0]

    # 获取当日 ETF 评分排名
    candidates = (
        session.query(EtfCandidate)
        .filter(EtfCandidate.screening_date == screening_date)
        .order_by(EtfCandidate.rank)
        .all()
    )

    if not candidates:
        logger.warning("ETF 候选数据为空 (date=%s)，跳过推荐生成", screening_date)
        return []

    # 总资金
    strategies = session.query(Strategy).filter(Strategy.status == "active").all()
    total_capital = (
        sum(float(s.current_capital or s.initial_capital) for s in strategies)
        if strategies
        else DEFAULT_CAPITAL
    )

    # 查询已持仓的股票（按股票代码简写匹配）
    held_positions = session.query(Position).filter(Position.status == "holding").all()
    # 归一化持仓代码用于匹配
    held_symbols: set[str] = set()
    for p in held_positions:
        sym = _normalize_ts_code(p.symbol)
        if sym:
            held_symbols.add(sym)

    results: list[EtfRecommendationResult] = []

    for c in candidates:
        score = float(c.combined_score or 0)
        rank = c.rank or 999
        is_held = _normalize_ts_code(c.ts_code) in held_symbols
        action = _classify_action_by_rank(rank, score, is_held)
        name = c.name or c.ts_code

        results.append(
            EtfRecommendationResult(
                ts_code=c.ts_code,
                name=name,
                recommendation_type=action,
                combined_score=score,
                current_price=float(c.current_price or 0),
                is_held=is_held,
                reason=_build_reason(action, name, score, rank),
            )
        )

    # 计算仓位
    _calculate_sizing(results, total_capital)

    return results
