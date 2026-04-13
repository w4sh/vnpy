#!/usr/bin/env python3
"""检查下载进度"""

import os
import polars as pl
from datetime import datetime

LAB_PATH = "/Users/w4sh8899/project/vnpy/lab_data"
DAILY_DIR = os.path.join(LAB_PATH, "daily")

print("=" * 60)
print("股指期货数据下载进度报告")
print("=" * 60)
print(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# 检查进程
if os.path.exists("download.pid"):
    with open("download.pid") as f:
        pid = int(f.read().strip())
    try:
        os.kill(pid, 0)
        print(f"✓ 下载进程运行中 (PID: {pid})")
    except OSError:
        print(f"✗ 下载进程已结束 (PID: {pid})")
else:
    print("✗ 未找到下载进程文件")

print()

# 检查数据文件
print("=" * 60)
print("数据文件统计")
print("=" * 60)

symbols = ["IF", "IH", "IC"]
for symbol in symbols:
    filename = f"{symbol}.CFFEX.parquet"
    filepath = os.path.join(DAILY_DIR, filename)

    if os.path.exists(filepath):
        df = pl.read_parquet(filepath)
        file_size = os.path.getsize(filepath) / 1024  # KB

        print(f"\n{filename}:")
        print(f"  文件大小: {file_size:.1f} KB")
        print(f"  数据行数: {len(df)}")
        print(f"  时间范围: {df['datetime'].min()} ~ {df['datetime'].max()}")

        # 计算数据覆盖率
        start_date = df["datetime"].min()
        end_date = df["datetime"].max()
        days = (end_date - start_date).days + 1
        expected_days = 365 * 5  # 5年
        coverage = len(df) / expected_days * 100
        print(f"  覆盖率: {coverage:.1f}% ({len(df)}/{expected_days} 个交易日)")
    else:
        print(f"\n{filename}: 尚未生成")

print()
print("=" * 60)
print("注意事项:")
print("=" * 60)
print("1. 数据可能不连续（周末、节假日无交易）")
print("2. 部分合约可能尚未上市或已退市")
print("3. 下载仍在进行中，数据会持续更新")
print("4. 预计总耗时: 2-3小时（96次API调用 × 3.5秒/次）")
print()
