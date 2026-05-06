"""ETF 筛选编排器

负责协调 ETF 筛选流程：
1. 获取 ETF 池 + 日行情
2. 逐只计算因子 → EtfCandidateResult
3. 评分排名
4. 存入 DB

与 candidate/screening_engine.py 的结构一致。
"""

from __future__ import annotations

import logging
import time
from datetime import date

from web_app.etf.etf_engine import build_etf_daily_snapshot, get_etf_pool
from web_app.etf.etf_factors import score_etf
from web_app.etf.etf_scoring import save_results_to_db, score_and_rank

logger = logging.getLogger(__name__)


def run_etf_screening(
    top_n: int = 30,
    trade_date: str | None = None,
) -> tuple[list[dict], int, float]:
    """执行完整 ETF 筛选流程

    参数:
        top_n: 保留前 N 只
        trade_date: 交易日 YYYYMMDD，默认今天

    返回:
        (结果列表 dict, 池大小, 耗时秒)
    """
    start = time.time()

    # 1. 获取 ETF 池
    pool = get_etf_pool()
    if not pool:
        logger.warning("ETF 池为空，跳过筛选")
        return [], 0, 0

    pool_size = len(pool)
    logger.info("ETF 筛选开始: pool=%d, top_n=%d", pool_size, top_n)

    # 2. 构建当日快照（基础信息 + 日行情 + 净值）
    snapshot = build_etf_daily_snapshot(trade_date)
    if not snapshot:
        logger.warning("当日 ETF 快照为空，跳过筛选")
        return [], pool_size, time.time() - start

    # 3. 逐只计算因子
    results = []
    for info in snapshot:
        try:
            result = score_etf(info)
            if result is not None:
                results.append(result)
        except Exception as e:
            logger.warning("ETF %s 因子计算失败: %s", info.get("ts_code", ""), e)
            continue

    logger.info("ETF 因子计算完成: %d / %d 只有效", len(results), len(snapshot))

    # 4. 评分排名
    ranked = score_and_rank(results, top_n)

    # 5. 存入 DB
    if trade_date:
        target_date = date.fromisoformat(trade_date[:10])
    else:
        target_date = date.today()
    save_results_to_db(ranked, target_date)

    elapsed = round(time.time() - start, 1)
    logger.info(
        "ETF 筛选完成: pool=%d, top=%d, elapsed=%.1fs", pool_size, len(ranked), elapsed
    )

    return [r.to_dict() for r in ranked], pool_size, elapsed


def run_daily_etf_screening() -> None:
    """每日 ETF 筛选入口（供定时任务调用）"""
    try:
        results, pool_size, elapsed = run_etf_screening()
        logger.info(
            "每日 ETF 筛选完成: pool=%d, top=%d, elapsed=%.1fs",
            pool_size,
            len(results),
            elapsed,
        )
    except Exception as e:
        logger.error("每日 ETF 筛选失败: %s", e)
