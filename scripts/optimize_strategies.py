#!/usr/bin/env python3
"""
策略参数优化框架
使用网格搜索优化策略参数
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
import polars as pl
from itertools import product

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from vnpy.trader.constant import Interval
from vnpy.alpha.strategy.backtesting import BacktestingEngine
from vnpy.alpha import AlphaLab

# 导入策略
from scripts.bollinger_bands_strategy import BollingerBandsStrategy
from scripts.momentum_strategy import MomentumStrategy


class StrategyOptimizer:
    """策略优化器"""

    def __init__(self, lab_path: str):
        """初始化"""
        self.lab_path = lab_path
        self.lab = AlphaLab(lab_path)

    def optimize_bollinger_bands(
        self,
        vt_symbols: List[str],
        start: datetime,
        end: datetime,
        capital: int = 1_000_000,
    ) -> Tuple[Dict, float]:
        """优化布林带策略参数"""
        print("=" * 60)
        print("布林带策略参数优化")
        print("=" * 60)

        # 定义参数网格
        param_grid = {
            "ma_window": [10, 20, 30],
            "std_window": [10, 20, 30],
            "dev_mult": [1.5, 2.0, 2.5],
            "init_days": [20, 30],
        }

        # 生成所有参数组合
        param_combinations = list(self._generate_param_combinations(param_grid))
        print(f"\n总参数组合数：{len(param_combinations)}")

        # 网格搜索
        best_params = None
        best_score = -float("inf")
        results = []

        for i, params in enumerate(param_combinations, 1):
            print(f"\n测试组合 {i}/{len(param_combinations)}: {params}")

            stats, success = self._backtest(
                BollingerBandsStrategy, params, vt_symbols, start, end, capital
            )

            if success:
                # 使用夏普比率作为优化目标
                score = stats.get("sharpe_ratio", -999)
                total_return = stats.get("total_return", 0)

                result = {
                    "params": params,
                    "sharpe_ratio": score,
                    "total_return": total_return,
                    "max_ddpercent": stats.get("max_ddpercent", 0),
                    "total_trades": stats.get("total_trade_count", 0),
                }
                results.append(result)

                print(f"  夏普比率：{score:.2f}, 收益率：{total_return:.2f}%")

                if score > best_score:
                    best_score = score
                    best_params = params
                    print(f"  ✓ 找到更优参数！")

        # 保存优化结果
        self._save_optimization_results("布林带策略", results, best_params)

        return best_params, best_score

    def optimize_momentum(
        self,
        vt_symbols: List[str],
        start: datetime,
        end: datetime,
        capital: int = 1_000_000,
    ) -> Tuple[Dict, float]:
        """优化动量策略参数"""
        print("=" * 60)
        print("动量策略参数优化")
        print("=" * 60)

        # 定义参数网格
        param_grid = {
            "momentum_window": [10, 20, 30],
            "entry_threshold": [0.01, 0.02, 0.03],
            "exit_threshold": [-0.005, -0.01, -0.02],
            "init_days": [20, 30],
        }

        # 生成所有参数组合
        param_combinations = list(self._generate_param_combinations(param_grid))
        print(f"\n总参数组合数：{len(param_combinations)}")

        # 网格搜索
        best_params = None
        best_score = -float("inf")
        results = []

        for i, params in enumerate(param_combinations, 1):
            print(f"\n测试组合 {i}/{len(param_combinations)}: {params}")

            stats, success = self._backtest(
                MomentumStrategy, params, vt_symbols, start, end, capital
            )

            if success:
                # 使用夏普比率作为优化目标
                score = stats.get("sharpe_ratio", -999)
                total_return = stats.get("total_return", 0)

                result = {
                    "params": params,
                    "sharpe_ratio": score,
                    "total_return": total_return,
                    "max_ddpercent": stats.get("max_ddpercent", 0),
                    "total_trades": stats.get("total_trade_count", 0),
                }
                results.append(result)

                print(f"  夏普比率：{score:.2f}, 收益率：{total_return:.2f}%")

                if score > best_score:
                    best_score = score
                    best_params = params
                    print(f"  ✓ 找到更优参数！")

        # 保存优化结果
        self._save_optimization_results("动量策略", results, best_params)

        return best_params, best_score

    def _backtest(
        self,
        strategy_class,
        params: Dict,
        vt_symbols: List[str],
        start: datetime,
        end: datetime,
        capital: int,
    ) -> Tuple[Dict, bool]:
        """运行单次回测"""
        try:
            engine = BacktestingEngine(self.lab)
            engine.set_parameters(
                vt_symbols=vt_symbols,
                interval=Interval.DAILY,
                start=start,
                end=end,
                capital=capital,
            )

            signal_df = pl.DataFrame({"datetime": [], "vt_symbol": [], "signal": []})
            engine.add_strategy(strategy_class, params, signal_df)
            engine.load_data()
            engine.run_backtesting()
            engine.calculate_result()
            stats = engine.calculate_statistics()

            return stats, True
        except Exception as e:
            return None, False

    def _generate_param_combinations(self, param_grid: Dict) -> List[Dict]:
        """生成参数组合"""
        keys = param_grid.keys()
        values = param_grid.values()
        combinations = product(*values)

        return [dict(zip(keys, combo)) for combo in combinations]

    def _save_optimization_results(
        self, strategy_name: str, results: List[Dict], best_params: Dict
    ):
        """保存优化结果"""
        output_path = Path("/Users/w4sh8899/project/vnpy/output")
        output_path.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = output_path / f"optimization_{strategy_name}_{timestamp}.txt"

        with open(result_file, "w") as f:
            f.write(f"{strategy_name}参数优化结果\n")
            f.write("=" * 60 + "\n\n")

            f.write(f"总测试次数：{len(results)}\n")
            f.write(f"最优参数：{best_params}\n\n")

            # 按夏普比率排序
            sorted_results = sorted(
                results, key=lambda x: x["sharpe_ratio"], reverse=True
            )

            f.write("Top 10 参数组合：\n")
            f.write("-" * 60 + "\n")
            for i, result in enumerate(sorted_results[:10], 1):
                f.write(f"\n第 {i} 名：\n")
                f.write(f"  参数：{result['params']}\n")
                f.write(f"  夏普比率：{result['sharpe_ratio']:.2f}\n")
                f.write(f"  总收益率：{result['total_return']:.2f}%\n")
                f.write(f"  最大回撤：{result['max_ddpercent']:.2f}%\n")
                f.write(f"  交易次数：{result['total_trades']}\n")

        print(f"\n✓ 优化结果已保存到：{result_file}")


def main():
    """主函数"""
    optimizer = StrategyOptimizer("/Users/w4sh8899/project/vnpy/lab_data")

    # 配置参数
    vt_symbols = [
        "000001.SZSE",
        "000002.SZSE",
        "600000.SSE",
        "600036.SSE",
        "601318.SSE",
    ]

    start = datetime(2020, 4, 13)
    end = datetime(2025, 4, 13)
    capital = 1_000_000

    print("策略参数优化")
    print("=" * 60)
    print(f"股票池：{vt_symbols}")
    print(f"时间范围：{start.date()} ~ {end.date()}")
    print(f"初始资金：{capital:,}")

    # 优化布林带策略
    print("\n" + "=" * 60)
    print("正在优化布林带策略...")
    print("=" * 60)
    bb_params, bb_score = optimizer.optimize_bollinger_bands(
        vt_symbols, start, end, capital
    )

    print(f"\n布林带最优参数：{bb_params}")
    print(f"最优夏普比率：{bb_score:.2f}")

    # 优化动量策略
    print("\n" + "=" * 60)
    print("正在优化动量策略...")
    print("=" * 60)
    mom_params, mom_score = optimizer.optimize_momentum(vt_symbols, start, end, capital)

    print(f"\n动量策略最优参数：{mom_params}")
    print(f"最优夏普比率：{mom_score:.2f}")

    print("\n" + "=" * 60)
    print("参数优化完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
