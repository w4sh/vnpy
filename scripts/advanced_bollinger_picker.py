#!/usr/bin/env python3
"""
高级布林带选股系统
支持多种选股策略和自定义条件

选股策略类型：
1. oversold - 超卖（价格触及下轨，买入机会）
2. overbought - 超买（价格触及上轨，卖出机会）
3. breakout_up - 向上突破
4. breakout_down - 向下突破
5. squeeze - 布林带收缩（即将突破）
6. reversal_down - 顶部反转（从高位回落）
7. reversal_up - 底部反转（从低位反弹）
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from vnpy.trader.constant import Interval
from vnpy.alpha import AlphaLab


class AdvancedBollingerPicker:
    """高级布林带选股器"""

    def __init__(self, lab_path: str):
        """初始化"""
        self.lab = AlphaLab(lab_path)
        self.results: defaultdict = defaultdict(list)

    def scan_with_strategy(
        self,
        strategy: str = "oversold",
        stock_list: list[str] = None,
        ma_window: int = 20,
        std_window: int = 20,
        dev_mult: float = 2.0,
        min_price: float = 3.0,
        max_price: float = 300.0,
        min_volume: int = 1000000,
        top_n: int = 20,  # 只返回前N个结果
    ) -> list[dict]:
        """
        按策略选股

        参数：
        - strategy: 选股策略类型
        - stock_list: 股票列表（None则使用全市场）
        - top_n: 返回前N个结果
        """
        print("=" * 60)
        print(f"布林带选股系统 - 策略：{strategy}")
        print("=" * 60)

        # 获取股票列表
        if stock_list is None:
            stock_list = self._get_all_stocks()

        print(f"扫描股票：{len(stock_list)} 只")
        print(f"选股策略：{strategy}")
        print("参数设置：")
        print(f"  均线周期：{ma_window}")
        print(f"  标准差周期：{std_window}")
        print(f"  标准差倍数：{dev_mult}")
        print(f"  价格范围：{min_price} - {max_price} 元")
        print(f"  最小成交量：{min_volume:,}")
        print(f"  返回数量：前 {top_n} 个")

        # 扫描股票
        candidates = []

        for i, vt_symbol in enumerate(stock_list):
            try:
                # 加载数据
                bars = self.lab.load_bar_data(
                    vt_symbol,
                    Interval.DAILY,
                    datetime.now() - timedelta(days=365 * 2),
                    datetime.now(),
                )

                if not bars or len(bars) < std_window + 10:
                    continue

                latest_bar = bars[-1]

                # 基本过滤
                if (
                    latest_bar.close_price < min_price
                    or latest_bar.close_price > max_price
                    or latest_bar.volume < min_volume
                ):
                    continue

                # 计算布林带
                bb_data = self._calculate_bollinger_bands(
                    bars, ma_window, std_window, dev_mult
                )

                if not bb_data:
                    continue

                # 检查是否符合策略条件
                if self._check_strategy(strategy, bb_data, bars):
                    score = self._calculate_score(strategy, bb_data, bars)

                    candidates.append(
                        {
                            "vt_symbol": vt_symbol,
                            "close_price": latest_bar.close_price,
                            "volume": latest_bar.volume,
                            "bb_position": bb_data["bb_position"],
                            "upper_band": bb_data["upper_band"],
                            "middle_band": bb_data["middle_band"],
                            "lower_band": bb_data["lower_band"],
                            "bb_width": bb_data["bb_width"],
                            "score": score,
                        }
                    )

                # 进度显示
                if i % 1000 == 0:
                    print(
                        f"  已扫描：{i}/{len(stock_list)} ({i / len(stock_list) * 100:.1f}%)"
                    )

            except Exception:
                continue

        # 按得分排序并返回前N个
        candidates.sort(key=lambda x: x["score"], reverse=True)

        print(f"\n扫描完成！找到 {len(candidates)} 只符合条件的股票")

        # 显示结果
        if candidates:
            print(f"\n前 {min(top_n, len(candidates))} 只股票：")
            print("-" * 60)
            for i, stock in enumerate(candidates[:top_n], 1):
                print(
                    f"{i}. {stock['vt_symbol']:15s} "
                    f"价格:{stock['close_price']:8.2f} "
                    f"位置:{stock['bb_position']:6.2%} "
                    f"得分:{stock['score']:6.2f}"
                )

        return candidates[:top_n]

    def _get_all_stocks(self) -> list[str]:
        """获取所有股票列表"""
        daily_dir = Path("/Users/w4sh8899/project/vnpy/lab_data/daily")
        if daily_dir.exists():
            return [f.stem for f in daily_dir.glob("*.parquet")]
        return []

    def _calculate_bollinger_bands(
        self, bars: list, ma_window: int, std_window: int, dev_mult: float
    ) -> dict | None:
        """计算布林带指标"""
        if len(bars) < std_window:
            return None

        import numpy as np

        closes = [bar.close_price for bar in bars]

        # 计算中轨
        middle_band = sum(closes[-ma_window:]) / ma_window

        # 计算标准差
        std_closes = closes[-std_window:]
        std = np.std(std_closes)

        # 计算上下轨
        upper_band = middle_band + dev_mult * std
        lower_band = middle_band - dev_mult * std

        # 计算布林带宽度
        bb_width = (
            (upper_band - lower_band) / middle_band * 100 if middle_band > 0 else 0
        )

        # 计算布林带位置
        latest_price = bars[-1].close_price
        if upper_band != lower_band:
            bb_position = (latest_price - lower_band) / (upper_band - lower_band)
        else:
            bb_position = 0.5

        return {
            "upper_band": upper_band,
            "middle_band": middle_band,
            "lower_band": lower_band,
            "bb_width": bb_width,
            "bb_position": bb_position,
        }

    def _check_strategy(self, strategy: str, bb_data: dict, bars: list) -> bool:
        """检查股票是否符合策略条件"""
        bb_position = bb_data["bb_position"]

        if strategy == "oversold":
            # 超卖：价格接近或低于下轨
            return bb_position <= 0.15

        elif strategy == "overbought":
            # 超买：价格接近或高于上轨
            return bb_position >= 0.85

        elif strategy == "breakout_up":
            # 向上突破：价格在上轨附近且布林带开口
            return bb_position >= 0.75 and bb_data["bb_width"] > 5

        elif strategy == "breakout_down":
            # 向下突破：价格在下轨附近且布林带开口
            return bb_position <= 0.25 and bb_data["bb_width"] > 5

        elif strategy == "squeeze":
            # 布林带收缩：布林带宽度很窄
            return bb_data["bb_width"] < 2

        elif strategy == "reversal_down":
            # 顶部反转：从高位回落
            if len(bars) < 5:
                return False
            # 前几天位置很高，现在回落
            recent_positions = []
            for i in range(-5, 0):
                if i == -1:
                    recent_positions.append(bb_position)
                else:
                    # 简化处理，这里应该重新计算每天的bb_position
                    pass
            return bb_position >= 0.7

        elif strategy == "reversal_up":
            # 底部反转：从低位反弹
            if len(bars) < 5:
                return False
            return bb_position <= 0.3

        return False

    def _calculate_score(self, strategy: str, bb_data: dict, bars: list) -> float:
        """计算股票得分（用于排序）"""
        score = 0.0
        bb_position = bb_data["bb_position"]
        bb_width = bb_data["bb_width"]

        if strategy == "oversold":
            # 超卖策略：位置越低越好，布林带宽度适中为好
            score = (1 - bb_position) * 100
            # 如果布林带宽度适中，加分
            if 3 < bb_width < 8:
                score += 20

        elif strategy == "overbought":
            # 超买策略：位置越高越好
            score = bb_position * 100
            if 3 < bb_width < 8:
                score += 20

        elif strategy == "breakout_up":
            # 突破策略：位置高且布林带开口大
            score = bb_position * 50 + bb_width * 10

        elif strategy == "breakout_down":
            score = (1 - bb_position) * 50 + bb_width * 10

        elif strategy == "squeeze":
            # 收缩策略：布林带宽度越小越好
            score = (10 - bb_width) * 10

        return score


def main():
    """主函数 - 演示不同策略的选股结果"""
    picker = AdvancedBollingerPicker("/Users/w4sh8899/project/vnpy/lab_data")

    print("高级布林带选股系统演示")
    print("=" * 60)

    # 演示不同策略
    strategies = ["oversold", "overbought", "breakout_up", "squeeze"]

    for strategy in strategies:
        print(f"\n{'=' * 60}")
        results = picker.scan_with_strategy(
            strategy=strategy,
            ma_window=20,
            std_window=20,
            dev_mult=2.0,
            min_price=5.0,
            max_price=200.0,
            min_volume=5000000,
            top_n=10,
        )

        if results:
            print(f"\n{strategy} 策略选出了 {len(results)} 只股票")


if __name__ == "__main__":
    main()
