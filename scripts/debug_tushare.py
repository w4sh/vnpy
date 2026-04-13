#!/usr/bin/env python3
"""
调试 Tushare API，查看实际返回的数据
"""

import tushare as ts

# 设置 Token
token = "8338d9ae4c26c3ec32cffbd1b337d97228c22ba84cea0996410513bb"
ts.set_token(token)
pro = ts.pro_api()

print("=" * 60)
print("Tushare API 调试")
print("=" * 60)

# 测试 fut_daily 接口
print("\n【测试1】fut_daily 接口")
print("-" * 60)
try:
    # 尝试不同的代码格式
    test_codes = [
        "IF0.CFFEX",
        "IFL.CFFEX",
        "IF2405.CFFEX",  # 具体合约
    ]

    for code in test_codes:
        print(f"\n测试代码：{code}")
        try:
            df = pro.fut_daily(ts_code=code, start_date="20240101", end_date="20240413")
            print(f"  返回行数：{len(df)}")
            if len(df) > 0:
                print(f"  列名：{list(df.columns)}")
                print("  前3行：")
                print(df.head(3))
        except Exception as e:
            print(f"  错误：{str(e)}")

except Exception as e:
    print(f"fut_daily 接口错误：{str(e)}")

# 测试 pro_bar 接口
print("\n" + "=" * 60)
print("【测试2】pro_bar 接口")
print("-" * 60)
try:
    test_codes = [
        "IF0.CFFEX",
        "IFL0.CFFEX",
        "000300.SZ",  # 沪深300指数
    ]

    for code in test_codes:
        print(f"\n测试代码：{code}")
        try:
            df = ts.pro_bar(
                ts_code=code, start_date="20240101", end_date="20240413", adj="qfq"
            )
            if df is not None:
                print(f"  返回行数：{len(df)}")
                if len(df) > 0:
                    print(f"  列名：{list(df.columns)}")
                    print("  前3行：")
                    print(df.head(3))
            else:
                print("  返回 None")
        except Exception as e:
            print(f"  错误：{str(e)}")

except Exception as e:
    print(f"pro_bar 接口错误：{str(e)}")

# 查询可用的期货列表
print("\n" + "=" * 60)
print("【测试3】查询期货列表")
print("-" * 60)
try:
    # 查询期货基本信息
    df = pro.fut_basic(
        exchange="CFFEX",
        fut_type="1",  # 股指期货
        fields="ts_code,symbol,name,list_date,delist_date",
    )
    print(f"期货列表行数：{len(df)}")
    if len(df) > 0:
        print(f"\n列名：{list(df.columns)}")
        print("\n前10行：")
        print(df.head(10))

        # 筛选 IF 相关
        print("\n筛选 IF 相关：")
        if_df = df[df["symbol"].str.contains("IF")]
        print(if_df.head(10))

except Exception as e:
    print(f"查询期货列表错误：{str(e)}")

print("\n" + "=" * 60)
print("调试完成")
print("=" * 60)
