#!/usr/bin/env python3
"""
个股数据对比验证脚本
功能：对比 Tushare 和 AKShare 下载数据的字段对齐情况
"""

import sys
from pathlib import Path
from datetime import datetime
import polars as pl

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from vnpy.alpha import AlphaLab


def compare_data_sources(stock_symbol: str, lab_path: str):
    """
    对比 Tushare 和 AKShare 数据
    :param stock_symbol: 股票代码（如 000001）
    :param lab_path: AlphaLab 路径
    """
    print(f"\n{'=' * 60}")
    print(f"数据对比：{stock_symbol}")
    print(f"{'=' * 60}\n")

    lab = AlphaLab(lab_path)

    # 尝试从两个数据源加载数据
    tushare_data = None
    akshare_data = None

    try:
        # Tushare 数据
        print("[1/4] 加载 Tushare 数据...")
        df_tushare = lab.load_bar_df(
            symbol=stock_symbol,
            exchange="SZSE" if stock_symbol.startswith("000") or stock_symbol.startswith("003") else "SSE",
            interval="daily",
            start="2020-04-13",
            end="2025-04-13",
        )

        if df_tushare is not None and len(df_tushare) > 0:
            # 筛选 Tushare 数据
            df_tushare = df_tushare.filter(pl.col("gateway_name") == "TUSHARE")
            if len(df_tushare) > 0:
                tushare_data = df_tushare
                print(f"  ✓ Tushare: {len(df_tushare)} 条")
            else:
                print(f"  ✗ Tushare: 无数据")
        else:
            print(f"  ✗ Tushare: 无数据")
    except Exception as e:
        print(f"  ✗ Tushare 加载失败：{str(e)}")

    try:
        # AKShare 数据
        print("\n[2/4] 加载 AKShare 数据...")
        df_akshare = lab.load_bar_df(
            symbol=stock_symbol,
            exchange="SZSE" if stock_symbol.startswith("000") or stock_symbol.startswith("003") else "SSE",
            interval="daily",
            start="2020-04-13",
            end="2025-04-13",
        )

        if df_akshare is not None and len(df_akshare) > 0:
            # 筛选 AKShare 数据
            df_akshare = df_akshare.filter(pl.col("gateway_name") == "AKSHARE")
            if len(df_akshare) > 0:
                akshare_data = df_akshare
                print(f"  ✓ AKShare: {len(df_akshare)} 条")
            else:
                print(f"  ✗ AKShare: 无数据")
        else:
            print(f"  ✗ AKShare: 无数据")
    except Exception as e:
        print(f"  ✗ AKShare 加载失败：{str(e)}")

    # 对比数据
    if tushare_data is not None and akshare_data is not None:
        print("\n[3/4] 字段对比...")
        compare_fields(tushare_data, akshare_data)

        print("\n[4/4] 数据一致性检查...")
        check_consistency(tushare_data, akshare_data)
    else:
        print("\n[3/4] 缺少数据源，跳过对比")
        if tushare_data is None:
            print("  ⚠ Tushare 数据不可用")
        if akshare_data is None:
            print("  ⚠ AKShare 数据不可用")

    print(f"\n{'=' * 60}\n")


def compare_fields(df1: pl.DataFrame, df2: pl.DataFrame):
    """对比字段"""
    print("\n字段对比：")
    print(f"{'Tushare 字段':<20} | {'AKShare 字段':<20} | {'对齐状态'}")
    print("-" * 60)

    # 字段映射
    field_mapping = {
        "datetime": ("datetime", "datetime"),
        "open_price": ("open_price", "open_price"),
        "high_price": ("high_price", "high_price"),
        "low_price": ("low_price", "low_price"),
        "close_price": ("close_price", "close_price"),
        "volume": ("volume", "volume"),
        "turnover": ("turnover", "turnover"),
        "open_interest": ("open_interest", "open_interest"),
    }

    for vnpy_field, (field1, field2) in field_mapping.items():
        has_1 = field1 in df1.columns
        has_2 = field2 in df2.columns

        if has_1 and has_2:
            status = "✓ 对齐"
        elif has_1 or has_2:
            status = "⚠ 部分对齐"
        else:
            status = "✗ 都不存在"

        print(f"{vnpy_field:<20} | {field1 if has_1 else '(缺失)'}:<20} | {status}")

    # 额外字段
    extra_1 = set(df1.columns) - {f[1] for f in field_mapping.values()}
    extra_2 = set(df2.columns) - {f[1] for f in field_mapping.values()}

    if extra_1:
        print(f"\nTushare 额外字段: {extra_1}")
    if extra_2:
        print(f"\nAKShare 额外字段: {extra_2}")


def check_consistency(df1: pl.DataFrame, df2: pl.DataFrame):
    """检查数据一致性"""
    # 找到共同的日期
    df1_dates = set(df1["datetime"].dt.strftime("%Y-%m-%d"))
    df2_dates = set(df2["datetime"].dt.strftime("%Y-%m-%d"))

    common_dates = df1_dates & df2_dates

    print(f"\n数据范围对比:")
    print(f"  Tushare: {len(df1_dates)} 个交易日")
    print(f"  AKShare: {len(df2_dates)} 个交易日")
    print(f"  共同: {len(common_dates)} 个交易日")

    # 筛选共同日期的数据
    df1_common = df1.filter(pl.col("datetime").dt.strftime("%Y-%m-%d").is_in(common_dates))
    df2_common = df2.filter(pl.col("datetime").dt.strftime("%Y-%m-%d").is_in(common_dates))

    if len(df1_common) > 0 and len(df2_common) > 0:
        # 随机抽取几条对比
        sample_size = min(5, len(df1_common))
        samples = df1_common.sample(sample_size)["datetime"].to_list()

        print(f"\n随机抽样对比（{sample_size}条）:")
        print(f"{'日期':<12} | {'Tushare 收盘':<12} | {'AKShare 收盘':<12} | {'差异'}")
        print("-" * 60)

        for date in samples:
            row1 = df1_common.filter(pl.col("datetime") == date).row(0)
            row2 = df2_common.filter(pl.col("datetime") == date).row(0)

            close1 = row1[5]  # close_price
            close2 = row2[5]  # close_price
            diff = abs(close1 - close2)
            pct_diff = (diff / close1 * 100) if close1 != 0 else 0

            status = "✓ 一致" if pct_diff < 0.01 else f"⚠ 差异 {pct_diff:.2f}%"

            print(f"{str(date)[:10]:<12} | {close1:<12.2f} | {close2:<12.2f} | {status}")

        # 统计差异
        df1_sorted = df1_common.sort("datetime")
        df2_sorted = df2_common.sort("datetime")

        close_diff = (df1_sorted["close_price"] - df2_sorted["close_price"]).abs()
        max_diff = close_diff.max()
        mean_diff = close_diff.mean()

        print(f"\n价格差异统计:")
        print(f"  最大差异: {max_diff:.2f} 元")
        print(f"  平均差异: {mean_diff:.2f} 元")
        print(f"  差异<0.01元: {(close_diff < 0.01).sum()} 条 ({(close_diff < 0.01).sum() / len(close_diff) * 100:.1f}%)")
        print(f"  差异<0.1元:  {(close_diff < 0.1).sum()} 条 ({(close_diff < 0.1).sum() / len(close_diff) * 100:.1f}%)")
        print(f"  差异>1元:   {(close_diff > 1.0).sum()} 条 ({(close_diff > 1.0).sum() / len(close_diff) * 100:.1f}%)")


def main():
    """主函数"""
    LAB_PATH = "/Users/w4sh8899/project/vnpy/lab_data"

    # 测试股票列表
    test_stocks = ["000001", "600000", "600519"]

    print("个股数据对比验证")
    print("=" * 60)
    print(f"测试股票: {', '.join(test_stocks)}")
    print(f"数据路径: {LAB_PATH}")
    print("=" * 60)

    for stock in test_stocks:
        try:
            compare_data_sources(stock, LAB_PATH)
        except Exception as e:
            print(f"\n✗ {stock} 对比失败: {str(e)}")
            continue


if __name__ == "__main__":
    main()
