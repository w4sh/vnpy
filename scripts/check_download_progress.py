#!/usr/bin/env python3
"""
A股数据下载进度监控
"""

import os
import polars as pl
from pathlib import Path

LAB_PATH = "/Users/w4sh8899/project/vnpy/lab_data"

print("=" * 60)
print("A股数据下载进度监控")
print("=" * 60)

# 统计已下载的股票数量
daily_path = Path(LAB_PATH) / "daily"

if daily_path.exists():
    # 统计股票文件
    stock_files = list(daily_path.glob("*.parquet"))

    # 过滤出股票文件（排除期货）
    stock_files = [
        f for f in stock_files if not any(x in f.stem for x in ["IF.", "IH.", "IC."])
    ]

    print(f"\n已下载股票数量: {len(stock_files)}")

    if len(stock_files) > 0:
        # 计算总数据条数
        total_bars = 0
        for file in stock_files[:10]:  # 采样前10个文件估算
            try:
                df = pl.read_parquet(file)
                total_bars += len(df)
            except:
                pass

        estimated_total = total_bars * (len(stock_files) / min(10, len(stock_files)))

        print(f"估算数据条数: {estimated_total:,}")
        print(f"平均每只: {estimated_total / len(stock_files):.0f} 条")

        # 最新下载的5只股票
        print(f"\n最新下载的5只股票:")
        sorted_files = sorted(
            stock_files, key=lambda f: f.stat().st_mtime, reverse=True
        )[:5]

        for file in sorted_files:
            try:
                df = pl.read_parquet(file)
                if len(df) > 0:
                    latest_date = df["datetime"].max()
                    print(f"  {file.stem}: {len(df)} 条 (最新: {latest_date.date()})")
            except:
                print(f"  {file.stem}: 读取失败")
    else:
        print("\n尚未下载任何股票数据")

else:
    print("\n数据目录不存在")

print("\n" + "=" * 60)

# 进程状态
import subprocess

try:
    result = subprocess.run(["ps", "-aux"], capture_output=True, text=True)
    download_processes = [
        line for line in result.stdout.split("\n") if "download_all_a_stocks" in line
    ]

    if download_processes:
        print("下载进程状态: 运行中")
        for proc in download_processes[:1]:
            parts = proc.split()
            pid = parts[1]
            cpu = parts[2]
            mem = parts[3]
            print(f"  PID: {pid}, CPU: {cpu}%, 内存: {mem}")
    else:
        print("下载进程状态: 未运行")
except:
    pass

print("=" * 60)
