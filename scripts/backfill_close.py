"""
回填 close 列到 daily 因子 Parquet

对最近 60 个交易日回填 close 价格数据，使动量因子 (momentum_60d) 恢复正常计算。

策略:
1. 读取现有 daily parquet
2. 从 Tushare 拉取最近 60 个交易日的 daily_basic 数据（含 close）
3. 用 compute_daily 做格式转换
4. 给旧数据添加 close 列（null），删除旧行，合并写入
"""

import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import polars as pl
from vnpy.alpha.factors.fundamental.fetcher import FundamentalFetcher
from vnpy.alpha.factors.fundamental.factors import FundamentalComputer
from vnpy.alpha.factors.fundamental.storage import FundamentalStorage

DATA_DIR = os.path.join(os.path.expanduser("~"), ".vntrader", "factors")
DAILY_PATH = os.path.join(DATA_DIR, "fundamental_daily.parquet")
BACKFILL_DAYS = 60


def get_recent_dates(n: int) -> list[str]:
    """从现有 parquet 中获取最近 n 个交易日"""
    if not os.path.exists(DAILY_PATH):
        print(f"❌ {DAILY_PATH} 不存在，无法获取交易日列表")
        sys.exit(1)
    df = pl.read_parquet(DAILY_PATH)
    return df["trade_date"].unique().sort(descending=True).head(n).to_list()


def main():
    dates = get_recent_dates(BACKFILL_DAYS)
    print(f"需要回填 {len(dates)} 个交易日: {dates[-1]} ~ {dates[0]}")

    fetcher = FundamentalFetcher()
    computer = FundamentalComputer()

    all_new = []
    success = 0
    fail = 0

    for i, td in enumerate(dates):
        print(f"  [{i + 1}/{len(dates)}] 拉取 {td}...", end=" ", flush=True)
        raw = fetcher.fetch_daily_basic(td)
        if raw.is_empty():
            print("⚠️ 无数据")
            fail += 1
            continue

        factors = computer.compute_daily(raw)
        if factors.is_empty():
            print("⚠️ 计算后为空")
            fail += 1
            continue

        # 确保有关闭列
        if "close" not in factors.columns:
            print("⚠️ 无 close 列")
            fail += 1
            continue

        all_new.append(factors)
        success += 1
        print(f"OK ({len(factors)} rows)")

        # 限频
        if i < len(dates) - 1:
            time.sleep(0.25)

    if not all_new:
        print("❌ 无有效数据，退出")
        return

    new_df = pl.concat(all_new)
    print(f"\n新数据: {len(new_df)} 行, 列: {new_df.columns}")

    # ---- 合并到现有 parquet ----
    print("\n合并到现有 parquet...")
    old_df = pl.read_parquet(DAILY_PATH)
    print(f"旧数据: {len(old_df)} 行")

    # 给旧数据添加 close 列
    old_df = old_df.with_columns(pl.lit(None, dtype=pl.Float64).alias("close"))

    # 删除旧行（被回填的日期）
    backfill_dates_set = set(new_df["trade_date"].unique().to_list())
    old_filtered = old_df.filter(~pl.col("trade_date").is_in(list(backfill_dates_set)))
    removed = len(old_df) - len(old_filtered)
    print(f"删除旧行: {removed}, 保留旧行: {len(old_filtered)}")

    # 合并
    combined = pl.concat([old_filtered, new_df])
    combined = combined.unique(subset=["trade_date", "vt_symbol"])
    combined = combined.sort(["trade_date", "vt_symbol"])

    # 写入
    combined.write_parquet(DAILY_PATH)
    print(f"✅ 写入完成: {len(combined)} 行")

    # 验证
    verify = pl.read_parquet(DAILY_PATH)
    has_close = verify["close"].drop_nulls().len()
    print(f"验证: {len(verify)} 行, {has_close} 行有 close 值")


if __name__ == "__main__":
    main()
