"""ETF 筛选结果数据类型"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EtfCandidateResult:
    """ETF 评分管道输出 — 与 CandidateResult 风格一致但使用 ETF 专属因子"""

    ts_code: str
    name: str

    # 原始因子值
    fund_size: float = 0.0
    expense_ratio: float = 0.0
    avg_daily_volume: float = 0.0
    premium_discount: float = 0.0
    tracking_error: float = 0.0
    dividend_yield: float = 0.0
    raw_momentum: float = 0.0
    raw_volatility: float = 0.0

    # 归一化评分 (0-100)
    liquidity_score: float = 0.0
    size_score: float = 0.0
    cost_score: float = 0.0
    tracking_score: float = 0.0
    premium_score: float = 0.0
    yield_score: float = 0.0
    momentum_score: float = 0.0
    volatility_score: float = 0.0

    # 上层评分
    technical_score: float = 0.0
    performance_score: float = 0.0
    combined_score: float = 0.0
    rank: int = 0

    # 行情 + 绩效
    current_price: float = 0.0
    total_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    annual_volatility: float = 0.0

    def to_dict(self) -> dict:
        return {
            "ts_code": self.ts_code,
            "name": self.name,
            "fund_size": self.fund_size,
            "expense_ratio": self.expense_ratio,
            "avg_daily_volume": self.avg_daily_volume,
            "premium_discount": self.premium_discount,
            "tracking_error": self.tracking_error,
            "dividend_yield": self.dividend_yield,
            "liquidity_score": self.liquidity_score,
            "size_score": self.size_score,
            "cost_score": self.cost_score,
            "tracking_score": self.tracking_score,
            "premium_score": self.premium_score,
            "yield_score": self.yield_score,
            "momentum_score": self.momentum_score,
            "volatility_score": self.volatility_score,
            "technical_score": self.technical_score,
            "performance_score": self.performance_score,
            "combined_score": self.combined_score,
            "rank": self.rank,
            "current_price": self.current_price,
            "total_return": self.total_return,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "annual_volatility": self.annual_volatility,
        }
