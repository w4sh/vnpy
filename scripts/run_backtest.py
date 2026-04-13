#!/usr/bin/env python3
"""
双均线策略回测主程序
"""

import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from vnpy.trader.constant import Interval
from vnpy.alpha.strategy.backtesting import BacktestingEngine
from vnpy.alpha import AlphaLab
from scripts.dual_ma_strategy import DualMaStrategy


def run_backtest(
    vt_symbols: list,
    start: datetime,
    end: datetime,
    fast_window: int = 5,
    slow_window: int = 20,
    capital: int = 1_000_000,
):
    """
    运行回测
    """
    print("=" * 60)
    print("双均线策略回测")
    print("=" * 60)

    # 初始化 AlphaLab
    lab_path = "/Users/w4sh8899/project/vnpy/lab_data"
    lab = AlphaLab(lab_path)

    # 创建回测引擎
    engine = BacktestingEngine(lab)

    # 设置回测参数
    engine.set_parameters(
        vt_symbols=vt_symbols,
        interval=Interval.DAILY,
        start=start,
        end=end,
        capital=capital,
        risk_free=0.0,
        annual_days=240,
    )

    # 创建空的信号 DataFrame（双均线策略不需要预计算信号）
    import polars as pl

    signal_df = pl.DataFrame({"datetime": [], "vt_symbol": [], "signal": []})

    # 添加策略
    engine.add_strategy(
        DualMaStrategy,
        {"fast_window": fast_window, "slow_window": slow_window},
        signal_df,
    )

    # 加载数据
    print("\n正在加载历史数据...")
    engine.load_data()

    # 运行回测
    print("\n开始回测...")
    engine.run_backtesting()

    # 计算结果
    print("\n计算回测结果...")
    engine.calculate_result()

    # 显示统计
    print("\n" + "=" * 60)
    print("回测统计结果")
    print("=" * 60)
    stats = engine.calculate_statistics()

    # 显示图表
    print("\n显示回测图表...")
    engine.show_chart()

    # 输出成交记录
    trades = engine.get_all_trades()
    print(f"\n总成交次数：{len(trades)}")

    # 保存结果
    output_path = Path("/Users/w4sh8899/project/vnpy/output")
    output_path.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 保存统计结果
    with open(output_path / f"backtest_stats_{timestamp}.txt", "w") as f:
        for key, value in stats.items():
            f.write(f"{key}: {value}\n")

    print(f"\n✓ 回测完成！结果已保存到 {output_path}")

    return engine, stats


def main():
    """主函数"""
    # 配置参数
    vt_symbols = ["IF.CFFEX", "IH.CFFEX", "IC.CFFEX"]

    # 回测时间范围（使用数据的时间范围）
    end = datetime(2024, 12, 31)
    start = datetime(2024, 4, 13)

    # 策略参数
    fast_window = 5
    slow_window = 20

    # 初始资金
    capital = 1_000_000

    print("回测配置：")
    print(f"  合约：{vt_symbols}")
    print(f"  时间：{start.date()} - {end.date()}")
    print(f"  快线：{fast_window} 日")
    print(f"  慢线：{slow_window} 日")
    print(f"  初始资金：{capital:,}\n")

    # 运行回测
    engine, stats = run_backtest(
        vt_symbols=vt_symbols,
        start=start,
        end=end,
        fast_window=fast_window,
        slow_window=slow_window,
        capital=capital,
    )

    # 打印关键指标
    print("\n" + "=" * 60)
    print("关键绩效指标")
    print("=" * 60)
    print(f"总收益率：{stats.get('total_return', 0):.2f}%")
    print(f"年化收益：{stats.get('annual_return', 0):.2f}%")
    print(f"最大回撤：{stats.get('max_ddpercent', 0):.2f}%")
    print(f"夏普比率：{stats.get('sharpe_ratio', 0):.2f}")
    print(f"收益回撤比：{stats.get('return_drawdown_ratio', 0):.2f}")


if __name__ == "__main__":
    main()
