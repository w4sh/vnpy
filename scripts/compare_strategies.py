#!/usr/bin/env python3
"""
多策略对比回测脚本
同时测试多个策略并对比表现
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

# 导入策略
from scripts.dual_ma_strategy import DualMaStrategy
from scripts.dual_thrust_strategy import DualThrustStrategy
from scripts.bollinger_bands_strategy import BollingerBandsStrategy
from scripts.momentum_strategy import MomentumStrategy


def run_strategy_backtest(
    strategy_class,
    strategy_name: str,
    strategy_params: dict,
    vt_symbols: list,
    start: datetime,
    end: datetime,
    capital: int = 1_000_000,
):
    """运行单个策略回测"""
    print(f"\n{'=' * 60}")
    print(f"回测策略：{strategy_name}")
    print(f"{'=' * 60}")

    # 初始化
    lab_path = "/Users/w4sh8899/project/vnpy/lab_data"
    lab = AlphaLab(lab_path)
    engine = BacktestingEngine(lab)

    # 设置参数
    engine.set_parameters(
        vt_symbols=vt_symbols,
        interval=Interval.DAILY,
        start=start,
        end=end,
        capital=capital,
        risk_free=0.0,
        annual_days=240,
    )

    # 创建空信号DataFrame
    signal_df = pl.DataFrame({"datetime": [], "vt_symbol": [], "signal": []})

    # 添加策略
    engine.add_strategy(strategy_class, strategy_params, signal_df)

    # 加载数据并回测
    try:
        engine.load_data()
        engine.run_backtesting()
        engine.calculate_result()
        stats = engine.calculate_statistics()
        return stats, True
    except Exception as e:
        print(f"策略回测失败：{str(e)}")
        return None, False


def compare_strategies():
    """对比多个策略"""
    print("=" * 60)
    print("多策略对比回测")
    print("=" * 60)

    # 配置参数
    vt_symbols = [
        "000001.SZSE",  # 平安银行
        "000002.SZSE",  # 万科A
        "600000.SSE",  # 浦发银行
        "600036.SSE",  # 招商银行
        "601318.SSE",  # 中国平安
    ]

    start = datetime(2020, 4, 13)
    end = datetime(2025, 4, 13)
    capital = 1_000_000

    print("\n回测配置：")
    print(f"  股票池：{vt_symbols}")
    print(f"  时间范围：{start.date()} ~ {end.date()}")
    print(f"  初始资金：{capital:,}")

    # 定义策略
    strategies = [
        {
            "name": "双均线策略",
            "class": DualMaStrategy,
            "params": {"fast_window": 5, "slow_window": 20},
        },
        {
            "name": "Dual Thrust策略",
            "class": DualThrustStrategy,
            "params": {"k1": 0.3, "k2": 0.3, "init_days": 10, "fixed_size": 100},
        },
        {
            "name": "布林带策略",
            "class": BollingerBandsStrategy,
            "params": {
                "ma_window": 20,
                "std_window": 20,
                "dev_mult": 2.0,
                "init_days": 30,
            },
        },
        {
            "name": "动量策略",
            "class": MomentumStrategy,
            "params": {
                "momentum_window": 20,
                "entry_threshold": 0.02,
                "exit_threshold": -0.01,
                "init_days": 30,
            },
        },
    ]

    # 运行回测
    results = []
    for strategy_config in strategies:
        stats, success = run_strategy_backtest(
            strategy_class=strategy_config["class"],
            strategy_name=strategy_config["name"],
            strategy_params=strategy_config["params"],
            vt_symbols=vt_symbols,
            start=start,
            end=end,
            capital=capital,
        )

        if success and stats:
            result = {
                "strategy": strategy_config["name"],
                "total_return": stats.get("total_return", 0),
                "annual_return": stats.get("annual_return", 0),
                "max_ddpercent": stats.get("max_ddpercent", 0),
                "sharpe_ratio": stats.get("sharpe_ratio", 0),
                "return_ddratio": stats.get("return_drawdown_ratio", 0),
                "total_trades": stats.get("total_trade_count", 0),
            }
            results.append(result)

    # 对比结果
    if results:
        print(f"\n{'=' * 60}")
        print("策略对比结果")
        print(f"{'=' * 60}\n")

        # 创建对比表格
        df = pl.DataFrame(results)
        print(df.to_pandas().to_string(index=False))

        # 找出最佳策略
        best_return = max(results, key=lambda x: x["total_return"])
        best_sharpe = max(results, key=lambda x: x["sharpe_ratio"])

        print(f"\n最佳收益策略：{best_return['strategy']}")
        print(f"  总收益率：{best_return['total_return']:.2f}%")
        print(f"  夏普比率：{best_return['sharpe_ratio']:.2f}")

        print(f"\n最佳夏普策略：{best_sharpe['strategy']}")
        print(f"  夏普比率：{best_sharpe['sharpe_ratio']:.2f}")
        print(f"  总收益率：{best_sharpe['total_return']:.2f}%")

        # 保存结果
        output_path = Path("/Users/w4sh8899/project/vnpy/output")
        output_path.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = output_path / f"strategy_comparison_{timestamp}.txt"

        with open(result_file, "w") as f:
            f.write("多策略对比回测结果\n")
            f.write(f"回测时间：{start.date()} - {end.date()}\n")
            f.write(f"股票数量：{len(vt_symbols)}\n")
            f.write(f"初始资金：{capital:,}\n")
            f.write("=" * 60 + "\n\n")

            for result in results:
                f.write(f"策略：{result['strategy']}\n")
                f.write("-" * 60 + "\n")
                for key, value in result.items():
                    if key != "strategy":
                        f.write(f"{key}: {value}\n")
                f.write("\n")

        print(f"\n✓ 对比结果已保存到：{result_file}")

    return results


if __name__ == "__main__":
    compare_strategies()
