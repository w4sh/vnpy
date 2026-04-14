#!/usr/bin/env python3
"""
布林带选股命令行工具
快速选股工具，支持多种策略和参数配置
"""

import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.advanced_bollinger_picker import AdvancedBollingerPicker


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="布林带选股系统")
    parser.add_argument(
        "--strategy",
        type=str,
        default="oversold",
        choices=[
            "oversold",
            "overbought",
            "breakout_up",
            "breakout_down",
            "squeeze",
        ],
        help="选股策略",
    )
    parser.add_argument("--top", type=int, default=20, help="返回前N只股票")
    parser.add_argument("--min-price", type=float, default=5.0, help="最低价格")
    parser.add_argument("--max-price", type=float, default=200.0, help="最高价格")
    parser.add_argument("--min-volume", type=int, default=5000000, help="最小成交量")
    parser.add_argument("--ma-window", type=int, default=20, help="均线周期")
    parser.add_argument("--std-window", type=int, default=20, help="标准差周期")
    parser.add_argument("--dev-mult", type=float, default=2.0, help="标准差倍数")

    args = parser.parse_args()

    # 创建选股器
    picker = AdvancedBollingerPicker("/Users/w4sh8899/project/vnpy/lab_data")

    # 执行选股
    results = picker.scan_with_strategy(
        strategy=args.strategy,
        ma_window=args.ma_window,
        std_window=args.std_window,
        dev_mult=args.dev_mult,
        min_price=args.min_price,
        max_price=args.max_price,
        min_volume=args.min_volume,
        top_n=args.top,
    )

    # 保存结果
    if results:
        output_file = f"/Users/w4sh8899/project/vnpy/output/stock_picker_{args.strategy}_latest.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"布林带选股结果 - {args.strategy}\n")
            f.write(f"扫描时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"股票数量：{len(results)}\n")
            f.write("=" * 60 + "\n\n")

            for i, stock in enumerate(results, 1):
                f.write(f"第 {i} 只：{stock['vt_symbol']}\n")
                f.write(f"  价格：{stock['close_price']:.2f} 元\n")
                f.write(f"  成交量：{stock['volume']:,}\n")
                f.write(f"  布林带位置：{stock['bb_position']:.2%}\n")
                f.write(f"  上轨：{stock['upper_band']:.2f}\n")
                f.write(f"  中轨：{stock['middle_band']:.2f}\n")
                f.write(f"  下轨：{stock['lower_band']:.2f}\n")
                f.write(f"  布林带宽度：{stock['bb_width']:.2f}%\n")
                f.write(f"  得分：{stock['score']:.2f}\n")
                f.write("\n")

        print(f"\n✓ 结果已保存到：{output_file}")


if __name__ == "__main__":
    main()
