"""回溯过去 N 个交易日的前瞻因子（daily_basic）数据

用法: python scripts/backfill_factors.py [--days 30]

遍历指定天数范围内的交易日，对缺失的日期逐天拉取 daily_basic
数据，计算日频因子并追加到 parquet 存储。
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_trade_days(days_back: int = 30) -> list[str]:
    """获取过去 N 个交易日列表（从昨天开始倒推）"""
    from web_app.candidate.engine import ts_code_to_symbol  # 用于复用 Tushare
    from vnpy.alpha.factors.tushare_config import get_pro_api

    pro = get_pro_api()
    today = date.today()
    start = today - timedelta(days=days_back * 2)  # 扩大范围确保够
    end = today

    try:
        df = pro.trade_cal(
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
        cal = df[df["is_open"] == 1]
        all_days = sorted(cal["cal_date"].tolist(), reverse=True)
        # 排除今天（交易日尚未结束）
        today_str = today.strftime("%Y%m%d")
        result = [d for d in all_days if d < today_str][:days_back]
        return result
    except Exception as e:
        logger.warning(f"获取交易日历失败: {e}，使用连续日期代替")
        result = []
        d = today - timedelta(days=1)
        while len(result) < days_back:
            result.append(d.strftime("%Y%m%d"))
            d -= timedelta(days=1)
        return result


def get_existing_dates() -> set[str]:
    """获取 parquet 中已有的交易日"""
    from vnpy.alpha.factors.fundamental import FundamentalStorage

    storage = FundamentalStorage()
    dates = storage.get_available_dates()
    existing = set()
    for d in dates:
        # d from parquet is YYYYMMDD string
        if len(d) == 8:
            existing.add(d)
        elif "-" in d:
            existing.add(d.replace("-", ""))
    return existing


def backfill_daily_factors(days_back: int = 30) -> None:
    """回填 past_days 的 daily_basic 因子数据"""
    logger.info("=== 前瞻因子数据回填 ===")
    logger.info("参数: days_back=%d", days_back)

    # 1. 确定需要回填的日期
    existing = get_existing_dates()
    target_dates = get_trade_days(days_back)
    missing = [d for d in target_dates if d not in existing]

    logger.info(
        "目标 %d 个交易日, 已有 %d 个, 缺失 %d 个",
        len(target_dates),
        len(target_dates) - len(missing),
        len(missing),
    )

    if not missing:
        logger.info("所有日期数据已存在，无需回填")
        return

    # 2. 逐日回填
    from vnpy.alpha.factors.fundamental import (
        FundamentalComputer,
        FundamentalFetcher,
        FundamentalStorage,
    )
    from vnpy.alpha.factors.stock_pool import StockPoolManager

    fetcher = FundamentalFetcher()
    computer = FundamentalComputer()
    storage = FundamentalStorage()

    pool_manager = StockPoolManager()
    _ = pool_manager.get_full_pool()  # 确保股票池初始化

    t0 = time.time()
    success = 0
    failed = 0

    for i, td in enumerate(missing):
        try:
            logger.info("  [%d/%d] 拉取 %s ...", i + 1, len(missing), td)
            raw = fetcher.fetch_daily_basic(td)
            if raw.is_empty():
                logger.warning("    %s 无数据", td)
                failed += 1
                continue

            factors = computer.compute_daily(raw)
            if factors.is_empty():
                logger.warning("    %s 计算无产出", td)
                failed += 1
                continue

            storage.save_daily(factors)
            success += 1
            logger.info("    ✓ %s: %d 只股票", td, len(factors))
        except Exception as e:
            logger.error("    ✗ %s: %s", td, e)
            failed += 1

    elapsed = time.time() - t0
    logger.info(
        "=== 回填完成: 成功 %d, 失败 %d, 耗时 %.0fs ===",
        success,
        failed,
        elapsed,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="回溯前瞻因子数据")
    parser.add_argument("--days", type=int, default=30, help="回溯天数")
    args = parser.parse_args()

    backfill_daily_factors(days_back=args.days)
