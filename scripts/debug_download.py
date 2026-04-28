#!/usr/bin/env python3
"""调试下载脚本"""

import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import tushare as ts
from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
from vnpy.alpha import AlphaLab

# 测试配置
TUSHARE_TOKEN = "8338d9ae4c26c3ec32cffbd1b337d97228c22ba84cea0996410513bb"
LAB_PATH = "/Users/w4sh8899/project/vnpy/lab_data"

print("=== 步骤1: 初始化 Tushare ===")
try:
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
    print("✓ Tushare 初始化成功")
except Exception as e:
    print(f"✗ Tushare 初始化失败: {e}")
    sys.exit(1)

print("\n=== 步骤2: 初始化 AlphaLab ===")
try:
    lab = AlphaLab(LAB_PATH)
    print("✓ AlphaLab 初始化成功")
except Exception as e:
    print(f"✗ AlphaLab 初始化失败: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print("\n=== 步骤3: 测试获取合约列表 ===")
try:
    df_basic = pro.fut_basic(
        exchange="CFFEX",
        fut_type="1",
        fields="ts_code,symbol,name,list_date,delist_date",
    )
    print(f"✓ 获取合约列表成功，共 {len(df_basic)} 个合约")
    print(f"  列名: {df_basic.columns.tolist()}")

    # 筛选 IF 合约
    if_contracts = df_basic[df_basic["symbol"].str.contains("IF")]
    print(f"  IF 合约数量: {len(if_contracts)}")
    if len(if_contracts) > 0:
        print("  IF 合约示例:")
        print(if_contracts.head(3))

except Exception as e:
    print(f"✗ 获取合约列表失败: {e}")
    import traceback

    traceback.print_exc()

print("\n=== 步骤4: 测试获取日线数据 ===")
try:
    # 使用最近的一个合约
    if len(if_contracts) > 0:
        test_ts_code = if_contracts.iloc[0]["ts_code"]
        print(f"  测试合约: {test_ts_code}")

        df_daily = pro.fut_daily(
            ts_code=test_ts_code, start_date="20250301", end_date="20250413"
        )

        print(f"✓ 获取日线数据成功，共 {len(df_daily)} 条")
        if len(df_daily) > 0:
            print(f"  列名: {df_daily.columns.tolist()}")
            print("  前3行:")
            print(df_daily.head(3))
        else:
            print("  ⚠ 数据为空，可能合约代码或日期范围有问题")
    else:
        print("✗ 没有 IF 合约可测试")

except Exception as e:
    print(f"✗ 获取日线数据失败: {e}")
    import traceback

    traceback.print_exc()

print("\n=== 步骤5: 测试数据转换 ===")
try:
    if len(df_daily) > 0:
        bars = []
        for _, row in df_daily.iterrows():
            bar = BarData(
                symbol="IF",
                exchange=Exchange.CFFEX,
                datetime=datetime.strptime(str(row["trade_date"]), "%Y%m%d"),
                interval=Interval.DAILY,
                open_price=float(row["open"]),
                high_price=float(row["high"]),
                low_price=float(row["low"]),
                close_price=float(row["close"]),
                volume=float(row.get("vol", 0)),
                turnover=float(row.get("amount", 0)),
                open_interest=float(row.get("oi", 0)),
                gateway_name="TUSHARE",
            )
            bars.append(bar)

        print(f"✓ 数据转换成功，共 {len(bars)} 条 BarData")
        print(f"  第1条: {bars[0]}")

except Exception as e:
    print(f"✗ 数据转换失败: {e}")
    import traceback

    traceback.print_exc()

print("\n=== 步骤6: 测试保存数据 ===")
try:
    if len(bars) > 0:
        lab.save_bar_data(bars)
        print("✓ 保存数据成功")

        # 验证保存
        overview = lab.get_bar_overview()
        print(f"  数据概览: {overview}")

except Exception as e:
    print(f"✗ 保存数据失败: {e}")
    import traceback

    traceback.print_exc()

print("\n=== 测试完成 ===")
