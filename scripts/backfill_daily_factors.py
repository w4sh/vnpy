#!/usr/bin/env python3
"""
日频基本面因子历史回填脚本

从 Tushare daily_basic 接口逐日拉取全市场估值数据，
计算 pe_ttm/pb/ps_ttm 三个日频因子，写入 fundamental_daily.parquet。

特点:
- 自动跳过已有日期的数据（增量回填）
- 200 次/分钟限流
- 交易日列表从本地 bar 数据提取（与 lab_data 完全对齐）
"""

from __future__ import annotations

import logging
import sys
import time

from pathlib import Path

import polars as pl

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def collect_trade_dates(lab_data_dir: str) -> list[str]:
    """从本地 bar 数据收集所有交易日"""
    daily_dir = Path(lab_data_dir) / "daily"
    if not daily_dir.exists():
        logger.error("bar 数据目录不存在: %s", daily_dir)
        return []

    all_dates: set[str] = set()
    for f in daily_dir.glob("*.parquet"):
        df = pl.read_parquet(f, columns=["datetime"])
        for dt in df["datetime"].unique().to_list():
            all_dates.add(dt.strftime("%Y%m%d"))

    dates = sorted(all_dates)
    logger.info(
        "从 %d 个 bar 文件中收集到 %d 个交易日",
        len(list(daily_dir.glob("*.parquet"))),
        len(dates),
    )
    return dates


def collect_existing_dates(daily_path: str) -> set[str]:
    """从已有 daily factor 文件中收集已存在的日期"""
    path = Path(daily_path)
    if not path.exists():
        return set()
    df = pl.read_parquet(path, columns=["trade_date"])
    existing = set(df["trade_date"].unique().to_list())
    logger.info("已有日频因子覆盖 %d 个交易日", len(existing))
    return existing


def backfill(
    dates: list[str],
    sleep_per_call: float = 0.3,
    dry_run: bool = False,
) -> None:
    """执行日频因子历史回填"""
    from vnpy.alpha.factors.fundamental.fetcher import FundamentalFetcher
    from vnpy.alpha.factors.fundamental.factors import FundamentalComputer
    from vnpy.alpha.factors.fundamental.storage import FundamentalStorage

    fetcher = FundamentalFetcher()
    computer = FundamentalComputer()
    storage = FundamentalStorage()

    existing = collect_existing_dates(str(storage.daily_path))
    pending = [d for d in dates if d not in existing]
    if not pending:
        logger.info("所有交易日已覆盖，无需回填")
        return

    logger.info("待回填: %d 个交易日 (已覆盖: %d)", len(pending), len(existing))

    if dry_run:
        logger.info("[DRY RUN] 不会实际调用 API，仅列出待回填日期:")
        for d in pending[:10]:
            logger.info("  %s", d)
        if len(pending) > 10:
            logger.info("  ... 共 %d 天", len(pending))
        return

    success_count = 0
    empty_count = 0
    error_count = 0
    start_time = time.time()

    for i, trade_date in enumerate(pending):
        try:
            # 200次/分钟 = 0.3s/次
            time.sleep(sleep_per_call)

            raw = fetcher.fetch_daily_basic(trade_date)
            if raw.is_empty():
                logger.warning(
                    "[%d/%d] %s: 无数据（非交易日或 API 返回空）",
                    i + 1,
                    len(pending),
                    trade_date,
                )
                empty_count += 1
                continue

            factors = computer.compute_daily(raw)
            storage.save_daily(factors)

            success_count += 1

            if (i + 1) % 50 == 0 or i == len(pending) - 1:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed * 60 if elapsed > 0 else 0
                logger.info(
                    "进度 %d/%d (%.1f%%)  成功=%d 空=%d 失败=%d  速率=%.0f天/分  日期=%s",
                    i + 1,
                    len(pending),
                    (i + 1) / len(pending) * 100,
                    success_count,
                    empty_count,
                    error_count,
                    rate,
                    trade_date,
                )

        except Exception as e:
            logger.error("[%d/%d] %s: %s", i + 1, len(pending), trade_date, e)
            error_count += 1
            # 连续 5 个错误则暂停 5 秒
            consecutive = getattr(backfill, "_consecutive_errors", 0) + 1
            backfill._consecutive_errors = consecutive  # noqa: B010
            if consecutive >= 5:
                logger.warning("连续 %d 个错误，暂停 5 秒...", consecutive)
                time.sleep(5)
            continue
        else:
            backfill._consecutive_errors = 0  # noqa: B010

    elapsed = time.time() - start_time
    logger.info(
        "回填完成: 成功=%d, 空数据=%d, 失败=%d, 总耗时=%.1f 分钟",
        success_count,
        empty_count,
        error_count,
        elapsed / 60,
    )


def main() -> None:
    script_dir = Path(__file__).parent.parent
    lab_data_dir = str(script_dir / "lab_data")

    logger.info("日频基本面因子历史回填")
    logger.info("lab_data: %s", lab_data_dir)
    logger.info("因子输出: ~/.vntrader/factors/fundamental_daily.parquet")

    dates = collect_trade_dates(lab_data_dir)
    if not dates:
        logger.error("未找到交易日数据")
        sys.exit(1)

    logger.info("交易日范围: %s ~ %s", dates[0], dates[-1])

    backfill(dates)


if __name__ == "__main__":
    main()
