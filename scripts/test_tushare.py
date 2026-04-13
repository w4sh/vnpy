#!/usr/bin/env python3
"""测试 Tushare 数据格式"""

import tushare as ts

# 设置 Token
ts.set_token("8338d9ae4c26c3ec32cffbd1b337d97228c22ba84cea0996410513bb")
pro = ts.pro_api()

# 测试获取合约列表
print("=== 测试 fut_basic 接口 ===")
try:
    df_basic = pro.fut_basic(
        exchange="CFFEX",
        fut_type="1",
        fields="ts_code,symbol,name,list_date,delist_date",
    )
    print(f"返回类型: {type(df_basic)}")
    print(f"合约数量: {len(df_basic)}")
    print("\n前5个合约:")
    print(df_basic.head(5))
    print(f"\n列名: {df_basic.columns.tolist()}")

    # �篩选 IF 合约
    if_contracts = df_basic[df_basic["symbol"].str.contains("IF")]
    print(f"\nIF 合约数量: {len(if_contracts)}")
    print("IF 合约示例:")
    print(if_contracts.head(3))

except Exception as e:
    print(f"错误: {e}")
    import traceback

    traceback.print_exc()

# 测试获取日线数据
print("\n\n=== 测试 fut_daily 接口 ===")
try:
    df_daily = pro.fut_daily(
        ts_code="IF2504.CFFEX",  # 使用一个具体的合约代码
        start_date="20250301",
        end_date="20250413",
    )
    print(f"返回类型: {type(df_daily)}")
    print(f"数据行数: {len(df_daily)}")
    print("\n前5行数据:")
    print(df_daily.head(5))
    print(f"\n列名: {df_daily.columns.tolist()}")
    print("\n数据类型:")
    print(df_daily.dtypes)

except Exception as e:
    print(f"错误: {e}")
    import traceback

    traceback.print_exc()
