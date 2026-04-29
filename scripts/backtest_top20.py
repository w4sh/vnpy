#!/usr/bin/env python3
"""Top 20 推荐股票过往半年回测

使用方法:
    python scripts/backtest_top20.py

回测逻辑:
    1. 读取 top20_recommend CSV 中的股票列表
    2. 从 Tushare 获取股票中文名称
    3. 从 Tushare 获取过去 6 个月日线行情 (close)
    4. 等权组合计算累计收益 + 最大回撤
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

import polars as pl
import numpy as np

# 回测参数
BACKTEST_MONTHS = 6


def load_top20_symbols(csv_path: str) -> list[str]:
    """读取 Top 20 股票代码"""
    df = pl.read_csv(csv_path)
    return df["vt_symbol"].to_list()


def fetch_stock_names(symbols: list[str]) -> dict[str, str]:
    """从 Tushare stock_basic 获取中文名称"""
    from vnpy.alpha.factors.tushare_config import get_pro_api

    # 转回 Tushare 格式 (.SSE → .SH, .SZSE → .SZ)
    ts_codes = [s.replace(".SSE", ".SH").replace(".SZSE", ".SZ") for s in symbols]

    api = get_pro_api()
    # 批量查询
    raw = api.stock_basic(
        ts_code=",".join(ts_codes),
        fields="ts_code,name",
    )
    if raw is None or raw.empty:
        logger.warning("stock_basic 返回空")
        return {s: s for s in symbols}

    name_map = {}
    for _, row in raw.iterrows():
        ts_code = row["ts_code"].replace(".SH", ".SSE").replace(".SZ", ".SZSE")
        name_map[ts_code] = row["name"]

    # 补上未查询到的
    for s in symbols:
        if s not in name_map:
            name_map[s] = s
    return name_map


def fetch_daily_prices(
    symbols: list[str], start_date: str, end_date: str
) -> pl.DataFrame:
    """从 Tushare 获取日线收盘价"""
    from vnpy.alpha.factors.tushare_config import get_pro_api

    api = get_pro_api()
    ts_codes = [s.replace(".SSE", ".SH").replace(".SZSE", ".SZ") for s in symbols]

    all_frames = []
    batch_size = 5  # Tushare 单次查询限制

    for i in range(0, len(ts_codes), batch_size):
        batch = ts_codes[i : i + batch_size]
        code_str = ",".join(batch)
        logger.info(
            "  拉取行情 [%d/%d]: %s",
            min(i + batch_size, len(ts_codes)),
            len(ts_codes),
            batch[0],
        )
        try:
            raw = api.daily(
                ts_code=code_str,
                start_date=start_date,
                end_date=end_date,
                fields="ts_code,trade_date,close",
            )
            if raw is not None and not raw.empty:
                df = pl.from_pandas(raw)
                df = df.with_columns(
                    [
                        pl.col("ts_code")
                        .str.replace(r"\.SH$", ".SSE")
                        .str.replace(r"\.SZ$", ".SZSE")
                        .alias("vt_symbol"),
                        pl.col("trade_date").cast(pl.Utf8),
                        pl.col("close").cast(pl.Float64),
                    ]
                )
                df = df.select(["vt_symbol", "trade_date", "close"])
                all_frames.append(df)
            time.sleep(0.3)  # 限速
        except Exception as e:
            logger.warning("  拉取失败 %s: %s", batch[0], e)

    if not all_frames:
        logger.error("未获取到任何行情数据")
        sys.exit(1)

    result = pl.concat(all_frames)
    logger.info(
        "行情数据: %d 行, %d 只股票", result.shape[0], result["vt_symbol"].n_unique()
    )
    return result


def compute_backtest(prices: pl.DataFrame, symbols: list[str]) -> pl.DataFrame:
    """计算等权组合收益率和最大回撤"""
    # 宽表: 每列一只股票的收盘价
    wide = prices.pivot(values="close", index="trade_date", on="vt_symbol")
    wide = wide.sort("trade_date")

    dates = wide["trade_date"].to_list()

    # 确保所有 20 只都在（缺失的填 NaN）
    for sym in symbols:
        if sym not in wide.columns:
            wide = wide.with_columns(pl.lit(None).alias(sym))

    # 日收益率
    for sym in symbols:
        if sym in wide.columns:
            col = pl.col(sym)
            ret = (col / col.shift(1) - 1).alias(f"ret_{sym}")
            wide = wide.with_columns(ret)

    # 等权组合日收益
    ret_cols = [f"ret_{s}" for s in symbols if f"ret_{s}" in wide.columns]
    wide = wide.with_columns(pl.mean_horizontal(ret_cols).alias("portfolio_ret"))

    # 累计收益
    wide = wide.with_columns(
        (pl.col("portfolio_ret").fill_null(0) + 1).cum_prod().alias("portfolio_cumret")
    )

    # 最大回撤
    cumret = wide["portfolio_cumret"].to_numpy()
    peak = np.maximum.accumulate(cumret)
    drawdown = (cumret - peak) / peak

    # 每只股票的累计收益
    ind_returns = {}
    for sym in symbols:
        if sym in wide.columns:
            close = wide[sym].to_numpy()
            first_valid = None
            last_valid = None
            for j in range(len(close)):
                if not np.isnan(close[j]):
                    if first_valid is None:
                        first_valid = close[j]
                    last_valid = close[j]
            if first_valid is not None and last_valid is not None and first_valid > 0:
                ind_returns[sym] = last_valid / first_valid - 1

    return wide, dates, drawdown, ind_returns


def main() -> None:
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

    # 1. 读取 Top 20 CSV
    csv_path = Path("output/top20_recommend_20260427.csv")
    if not csv_path.exists():
        logger.error("未找到 %s，请先运行 top20_recommend.py", csv_path)
        sys.exit(1)

    symbols = load_top20_symbols(str(csv_path))
    logger.info("加载 Top 20: %d 只", len(symbols))

    # 2. 获取中文名称
    names = fetch_stock_names(symbols)

    # 3. 确定回测日期范围
    end_date = "20260427"
    # 计算起始日期（约 6 个月前）
    year = int(end_date[:4])
    month = int(end_date[4:6]) - BACKTEST_MONTHS
    while month <= 0:
        year -= 1
        month += 12
    start_date = f"{year}{month:02d}{end_date[6:]}"
    logger.info("回测区间: %s ~ %s", start_date, end_date)

    # 4. 拉取行情
    prices = fetch_daily_prices(symbols, start_date, end_date)

    # 5. 计算回测
    wide, dates, drawdown, ind_returns = compute_backtest(prices, symbols)

    max_dd = float(np.min(drawdown))
    final_cumret = float(wide["portfolio_cumret"].tail(1).to_numpy()[0])

    # 6. 显示结果
    print(f"\n{'=' * 100}")
    print(f"  Top 20 等权组合回测 — 过往 {BACKTEST_MONTHS} 个月")
    print(f"  区间: {dates[0]} ~ {dates[-1]}  交易日: {len(dates)}")
    print(f"{'=' * 100}")

    print(f"\n  组合累计收益: {final_cumret - 1:+.2%}")
    print(f"  组合最大回撤: {max_dd:+.2%}")
    print(f"  年化收益:     {((final_cumret) ** (252 / len(dates)) - 1):+.2%}")
    print(
        f"  收益/回撤比:  {abs((final_cumret - 1) / max_dd) if max_dd != 0 else float('inf'):.2f}"
    )

    print(f"\n  {'代码':<14s} {'名称':<10s} {'累计收益':>10s}")
    print(f"  {'-' * 36}")
    for sym in symbols:
        ret = ind_returns.get(sym, None)
        ret_str = f"{ret:+.2%}" if ret is not None else "无数据"
        name = names.get(sym, sym)
        print(f"  {sym:<14s} {name:<10s} {ret_str:>10s}")

    # 回撤曲线摘要
    print(f"\n  最大回撤日期: {dates[int(np.argmin(drawdown))]}")


if __name__ == "__main__":
    main()
