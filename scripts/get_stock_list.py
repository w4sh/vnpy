#!/usr/bin/env python3
"""快速获取A股股票列表"""

import akshare as ak

print("=" * 60)
print("获取A股股票列表")
print("=" * 60)

try:
    # 获取A股股票列表
    print("\n[1/2] 从 AKShare 获取股票列表...")
    stock_info = ak.stock_info_a_code_name()

    if stock_info is not None and len(stock_info) > 0:
        # 重命名列
        stock_info.columns = ["code", "name"]

        print(f"✓ 获取到 {len(stock_info)} 只股票")

        # 添加交易所
        def get_exchange(code):
            if code.startswith("6"):
                return "SSE"
            elif code.startswith("0") or code.startswith("3"):
                return "SZSE"
            else:
                return "UNKNOWN"

        stock_info["exchange"] = stock_info["code"].apply(get_exchange)

        # 保存
        stock_info.to_csv("stock_list_all.csv", index=False, encoding="utf-8-sig")
        print("✓ 已保存到: stock_list_all.csv")

        # 统计
        print("\n[2/2] 市场分布:")
        print(stock_info["exchange"].value_counts())

        print("\n前10只股票:")
        print(stock_info.head(10))

    else:
        print("✗ 获取失败")

except Exception as e:
    print(f"✗ 错误: {str(e)}")

print("\n" + "=" * 60)
