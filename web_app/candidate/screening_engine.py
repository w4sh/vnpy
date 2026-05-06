#!/usr/bin/env python3
"""候选股筛选引擎 — 调度入口

每日收盘后：
1. 获取候选池股票日线数据（Tushare Pro）          → engine.py
2. 计算四类技术因子得分（动量/趋势/量价/波动）      → factors.py
3. 归一化 + 排名                                    → scoring.py
4. 结果存入 CandidateStock 数据库表                 → scoring.py
"""

from __future__ import annotations

import logging
import time
from datetime import date

from web_app.candidate.candidate_types import CandidateResult
from web_app.candidate.engine import (
    STOCK_POOL,
    fetch_all_stocks_data,
    fetch_daily_data,
)
from web_app.candidate.factors import score_stock
from web_app.candidate.scoring import score_and_rank, save_results_to_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 筛选主流程
# ---------------------------------------------------------------------------


def run_screening(
    stock_pool: list[str] | None = None,
    top_n: int = 30,
    mode: str = "pool",
) -> tuple[list[dict], int, float]:
    """执行一次完整筛选

    Args:
        stock_pool: 股票池列表，仅 mode="pool" 时使用
        top_n: 返回 Top N 只
        mode: "pool" 使用手动股票池逐只获取，"full" 全市场批量获取

    返回: (results, pool_size, elapsed_seconds)
    """
    start = time.time()
    results: list[CandidateResult] = []

    # --- 1. 获取日线数据 ---
    if mode == "full":
        all_data = fetch_all_stocks_data()
        pool_size = len(all_data)
        logger.info(f"开始全市场筛选，股票池 {pool_size} 只")
    else:
        if stock_pool is None:
            stock_pool = STOCK_POOL
        pool_size = len(stock_pool)
        all_data = {}
        logger.info(f"开始筛选，股票池 {pool_size} 只")
        for symbol in stock_pool:
            data = fetch_daily_data(symbol)
            if data is None:
                continue
            time.sleep(0.2)
            all_data[data["symbol"]] = data

    # --- 2. 因子打分 ---
    for _symbol, data in all_data.items():
        result = score_stock(data)
        if result:
            results.append(result)

    # --- 3. 评分 + 排名 ---
    top = score_and_rank(results, top_n=top_n)

    elapsed = round(time.time() - start, 1)
    logger.info(
        f"筛选完成：{len(results)} 只有效股票 → Top {len(top)}，耗时 {elapsed}s"
    )

    return _results_to_dicts(top), pool_size, elapsed


def _results_to_dicts(candidates: list[CandidateResult]) -> list[dict]:
    """将 CandidateResult 列表转为 API 兼容的 dict 列表"""
    return [
        {
            "symbol": r.symbol,
            "name": r.name,
            "score": r.combined_score,
            "technical_score": r.technical_score,
            "performance_score": r.performance_score,
            "combined_score": r.combined_score,
            "rank": r.rank,
            "momentum_score": r.momentum_score,
            "trend_score": r.trend_score,
            "volume_score": r.volume_score,
            "volatility_score": r.volatility_score,
            "current_price": r.current_price,
            "total_return": r.total_return,
            "max_drawdown": r.max_drawdown,
            "sharpe_ratio": r.sharpe_ratio,
        }
        for r in candidates
    ]


# ---------------------------------------------------------------------------
# 每日调度入口
# ---------------------------------------------------------------------------


def run_daily_screening():
    """每日筛选主入口 — 由调度器调用"""
    logger.info("=== 开始每日候选股筛选 ===")
    try:
        results, pool_size, elapsed = run_screening()
        _save_daily_results(results)
        logger.info(
            f"=== 每日候选股筛选完成，股票池 {pool_size}，"
            f"Top {len(results)}，耗时 {elapsed}s ==="
        )
        return results, pool_size, elapsed
    except Exception as e:
        logger.error(f"每日候选股筛选失败: {e}")
        raise


def _save_daily_results(results: list[dict]) -> None:
    """将 dict 列表转为 CandidateResult 并存入 DB"""
    candidates = [
        CandidateResult(
            symbol=r["symbol"],
            name=r["name"],
            momentum_score=r["momentum_score"],
            trend_score=r["trend_score"],
            volume_score=r["volume_score"],
            volatility_score=r["volatility_score"],
            technical_score=r["technical_score"],
            performance_score=r.get("performance_score", 0.0),
            combined_score=r["combined_score"],
            rank=r["rank"],
            current_price=r["current_price"],
            total_return=r["total_return"],
            max_drawdown=r["max_drawdown"],
            sharpe_ratio=r["sharpe_ratio"],
        )
        for r in results
    ]
    save_results_to_db(candidates, date.today())
