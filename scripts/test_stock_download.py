#!/usr/bin/env python3
"""快速测试股票下载功能"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import akshare as ak
import pandas as pd
from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
from vnpy.alpha import AlphaLab

print("=== 测试 AKShare 股票下载 ===\n")

# 测试参数
stock_code = "000001"  # 平安银行
start_date = "20240101"
end_date = "20240131"

print(f"股票代码: {stock_code}")
print(f"时间范围: {start_date} ~ {end_date}\n")

# 下载数据
print("[1/3] 从 AKShare 下载数据...")
df = ak.stock_zh_a_hist(
    symbol=stock_code,
    period="daily",
    start_date=start_date,
    end_date=end_date,
    adjust="qfq",
)

if df is not None and len(df) > 0:
    print(f"✓ 下载成功: {len(df)} 条")
    print("\n[2/3] 转换为 BarData...")

    # 转换为 BarData
    bars = []
    for _, row in df.iterrows():
        bar = BarData(
            symbol=stock_code,
            exchange=Exchange.SZSE,
            datetime=pd.to_datetime(row["日期"]),
            interval=Interval.DAILY,
            open_price=float(row["开盘"]),
            high_price=float(row["最高"]),
            low_price=float(row["最低"]),
            close_price=float(row["收盘"]),
            volume=float(row["成交量"]),
            turnover=float(row["成交额"]),
            open_interest=0.0,
            gateway_name="AKSHARE",
        )
        bars.append(bar)

    print(f"✓ 转换成功: {len(bars)} 条")
    print("\n[3/3] 保存到 AlphaLab...")

    # 保存
    lab = AlphaLab("lab_data")
    lab.save_bar_data(bars)

    print("✓ 保存成功")
    print("\n数据示例:")
    for bar in bars[:3]:
        print(
            f"  {bar.datetime.date()}: 收盘 {bar.close_price:.2f}, 成交量 {bar.volume:.0f}"
        )
else:
    print("✗ 下载失败")

print("\n=== 测试完成 ===")
