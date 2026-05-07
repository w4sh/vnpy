"""回溯过去 N 个交易日的候选股筛选

用法: python scripts/backfill_candidates.py [--days 30] [--top 30]

通过一次性拉取全市场 120 天日线数据，对每个交易日截断时间序列后重新执行
因子计算 → 评分排名 → DB 存储，避免前视偏差。
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import date

sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def truncate_to_date(stock_data: dict, target_date: str) -> dict | None:
    """截断股票数据到目标日期（含）

    二分查找 target_date 的位置，保留 dates[i] <= target_date 的部分。
    返回 None 如果剩余数据不足 MIN_BARS_REQUIRED。
    """
    from web_app.candidate.engine import MIN_BARS_REQUIRED

    dates = stock_data["dates"]
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if dates[mid] <= target_date:
            lo = mid + 1
        else:
            hi = mid
    trunc_idx = lo

    if trunc_idx < MIN_BARS_REQUIRED:
        return None

    return {
        "symbol": stock_data["symbol"],
        "dates": dates[:trunc_idx],
        "open": stock_data["open"][:trunc_idx],
        "close": stock_data["close"][:trunc_idx],
        "high": stock_data["high"][:trunc_idx],
        "low": stock_data["low"][:trunc_idx],
        "volume": stock_data["volume"][:trunc_idx],
    }


def run_backfill(top_n: int = 30, days_back: int = 30) -> None:
    """回溯筛选主流程"""
    logger.info("=== 候选股回溯筛选 ===")
    logger.info("参数: top_n=%d, days_back=%d", top_n, days_back)

    # 1. 获取全市场数据
    logger.info("步骤1/3: 拉取全市场 120 天日线数据...")
    t0 = time.time()
    from web_app.candidate.engine import fetch_all_stocks_data

    data = fetch_all_stocks_data()
    logger.info("拉取完成: %d 只股票, 耗时 %.0fs", len(data), time.time() - t0)

    # 2. 确定回溯日期（数据中存在的交易日）
    all_dates: set[str] = set()
    for sym_data in data.values():
        for d in sym_data["dates"]:
            all_dates.add(d)
    sorted_dates = sorted(all_dates, reverse=True)

    today_str = date.today().strftime("%Y%m%d")
    target_dates = [d for d in sorted_dates if d < today_str][:days_back]
    target_dates.reverse()  # 从旧到新

    logger.info(
        "步骤2/3: 发现 %d 个交易日, 回溯 %d 个 (%s ~ %s)",
        len(sorted_dates),
        len(target_dates),
        target_dates[0] if target_dates else "N/A",
        target_dates[-1] if target_dates else "N/A",
    )

    # 3. 逐日回溯
    from web_app.candidate.candidate_types import CandidateResult
    from web_app.candidate.factors import score_stock
    from web_app.candidate.scoring import score_and_rank, save_results_to_db

    logger.info("步骤3/3: 开始逐日回溯筛选...")
    pipeline_t0 = time.time()

    for i, td in enumerate(target_dates):
        day_t0 = time.time()
        results = []

        for symbol, sym_data in data.items():
            truncated = truncate_to_date(sym_data, td)
            if truncated is None:
                continue
            result = score_stock(truncated)
            if result:
                results.append(result)

        if not results:
            logger.warning("  [%d/%d] %s: 无有效股票", i + 1, len(target_dates), td)
            continue

        # 评分排名
        top = score_and_rank(results, top_n=top_n)

        # 转为 CandidateResult 用于存储
        candidates = [
            CandidateResult(
                symbol=r.symbol,
                name=r.name,
                momentum_score=r.momentum_score,
                trend_score=r.trend_score,
                volume_score=r.volume_score,
                volatility_score=r.volatility_score,
                technical_score=r.technical_score,
                performance_score=r.performance_score,
                combined_score=r.combined_score,
                rank=r.rank,
                current_price=r.current_price,
                total_return=r.total_return,
                max_drawdown=r.max_drawdown,
                sharpe_ratio=r.sharpe_ratio,
            )
            for r in top
        ]

        target_date_obj = date(int(td[:4]), int(td[4:6]), int(td[6:8]))
        save_results_to_db(candidates, target_date_obj)

        elapsed = time.time() - day_t0
        logger.info(
            "  [%d/%d] %s: %d 只 (pool=%d, %.1fs)",
            i + 1,
            len(target_dates),
            td,
            len(candidates),
            len(results),
            elapsed,
        )

    total_elapsed = time.time() - pipeline_t0
    logger.info(
        "=== 回溯筛选完成: %d 个交易日, 总耗时 %.0fs (平均 %.0fs/日) ===",
        len(target_dates),
        total_elapsed,
        total_elapsed / max(len(target_dates), 1),
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="回溯候选股筛选")
    parser.add_argument("--days", type=int, default=30, help="回溯天数")
    parser.add_argument("--top", type=int, default=30, help="Top N")
    args = parser.parse_args()

    run_backfill(top_n=args.top, days_back=args.days)
