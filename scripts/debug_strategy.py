#!/usr/bin/env python3
"""
策略调试脚本
添加详细日志来诊断为什么策略没有产生交易
"""

import sys
from pathlib import Path
from datetime import datetime
import polars as pl

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from vnpy.trader.constant import Interval
from vnpy.alpha.strategy.backtesting import BacktestingEngine
from vnpy.alpha import AlphaLab
from scripts.bollinger_bands_strategy import BollingerBandsStrategy


def debug_bollinger():
    """调试布林带策略"""
    print("=" * 60)
    print("布林带策略调试")
    print("=" * 60)

    # 初始化
    lab_path = "/Users/w4sh8899/project/vnpy/lab_data"
    lab = AlphaLab(lab_path)

    # 检查数据
    vt_symbol = "000001.SZSE"
    print(f"\n检查数据: {vt_symbol}")
    bars = lab.load_bar_data(
        vt_symbol, Interval.DAILY, datetime(2020, 4, 13), datetime(2020, 6, 13)
    )
    print(f"数据条数: {len(bars)}")
    if bars:
        print(f"时间范围: {bars[0].datetime} ~ {bars[-1].datetime}")
        print(f"最新价格: {bars[-1].close_price:.2f}")

    # 运行回测（单股票，短周期）
    engine = BacktestingEngine(lab)
    engine.set_parameters(
        vt_symbols=[vt_symbol],
        interval=Interval.DAILY,
        start=datetime(2020, 4, 13),
        end=datetime(2020, 6, 13),
        capital=1_000_000,
    )

    signal_df = pl.DataFrame({"datetime": [], "vt_symbol": [], "signal": []})

    # 使用更激进的参数
    params = {
        "ma_window": 5,
        "std_window": 5,
        "dev_mult": 1.0,
        "init_days": 6,
    }

    print(f"\n回测参数: {params}")
    engine.add_strategy(BollingerBandsStrategy, params, signal_df)

    try:
        engine.load_data()
        engine.run_backtesting()
        engine.calculate_result()

        # 检查交易记录
        trades = engine.get_all_trades()
        print(f"\n交易记录数: {len(trades)}")
        for trade in trades[:10]:  # 显示前10笔
            print(
                f"  {trade.datetime} {trade.vt_symbol} "
                f"{trade.direction.value} {trade.volume} @ {trade.price:.2f}"
            )

        # 计算统计
        stats = engine.calculate_statistics()
        print(f"\n统计数据:")
        print(f"  总收益率: {stats.get('total_return', 0):.2f}%")
        print(f"  交易次数: {stats.get('total_trade_count', 0)}")

    except Exception as e:
        print(f"\n回测失败: {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    debug_bollinger()
