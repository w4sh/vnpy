#!/usr/bin/env python3
"""测试 fut_basic API 调用"""

import tushare as ts

TUSHARE_TOKEN = "8338d9ae4c26c3ec32cffbd1b337d97228c22ba84cea0996410513bb"

ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

print("测试 fut_basic API 调用...")
try:
    df = pro.fut_basic(
        exchange="CFFEX",
        fut_type="1",
        fields="ts_code,symbol,name,list_date,delist_date",
    )

    print(f"✓ 调用成功")
    print(f"  返回类型: {type(df)}")
    print(f"  数据行数: {len(df)}")

    if len(df) > 0:
        print(f"  列名: {df.columns.tolist()}")
        print(f"  前3行:")
        print(df.head(3))
    else:
        print(f"  ✗ DataFrame 为空")

except Exception as e:
    print(f"✗ 调用失败: {e}")
    import traceback

    traceback.print_exc()
