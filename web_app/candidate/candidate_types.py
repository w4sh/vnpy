"""候选股筛选共享数据结构

本模块仅包含 CandidateResult dataclass，供 engine / factors / scoring 三个模块共用，
避免循环引用。
"""

from dataclasses import dataclass


@dataclass
class CandidateResult:
    """单只股票的筛选与打分结果"""

    symbol: str
    name: str

    # 原始因子值 (factors.py 产出)
    raw_momentum: float = 0.0
    raw_trend: float = 0.0
    raw_volume: float = 0.0
    raw_volatility: float = 0.0
    raw_northbound_stock: float = 0.0
    raw_northbound_flow: float = 0.0

    # 归一化因子分 (scoring.py 填充)
    momentum_score: float = 0.0
    trend_score: float = 0.0
    volume_score: float = 0.0
    volatility_score: float = 0.0
    northbound_stock_score: float = 0.0
    northbound_flow_score: float = 0.0

    # 北向标的标记
    has_northbound: bool = False

    # 绩效
    current_price: float = 0.0
    total_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0

    # 基本面四维综合评分 (100-0, screening_engine.py 注入)
    fundamental_score: float = 0.0

    # 二级分数 (scoring.py 填充)
    technical_score: float = 0.0
    performance_score: float = 0.0
    combined_score: float = 0.0

    # 最终排名
    rank: int = 0
