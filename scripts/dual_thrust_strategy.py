#!/usr/bin/env python3
"""
Dual Thrust 策略（双驱动策略）

经典突破策略，逻辑：
1. 计算上轨 = 昨日最高 + k1 * (昨日最高 - 昨日最低)
2. 计算下轨 = 昨日最低 - k2 * (昨日最高 - 昨日最低)
3. 突破上轨买入，突破下轨卖出
4. 反向突破时止损

参数优化空间：
- k1, k2: 波动率系数
- 止损系数
- 持仓时间
"""

from collections import defaultdict
from datetime import datetime, time

from vnpy.trader.object import BarData, TradeData, OrderData
from vnpy.trader.constant import Direction, Offset, Status
from vnpy.trader.utility import ArrayManager
from vnpy.alpha import AlphaStrategy


class DualThrustStrategy(AlphaStrategy):
    """Dual Thrust 策略"""

    # 策略参数
    k1: float = 0.3  # 上轨系数
    k2: float = 0.3  # 下轨系数
    init_days: int = 10  # 初始化天数
    fixed_size: int = 100  # 固定交易手数

    def on_init(self) -> None:
        """策略初始化"""
        self.write_log(f"Dual Thrust 策略初始化（k1={self.k1}, k2={self.k2}）")

        # 数据缓存
        self.am: defaultdict = defaultdict(ArrayManager)
        self.bars: defaultdict = defaultdict(list)

        # 交易状态
        self.targets: defaultdict = defaultdict(int)

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """K线数据回调"""
        for vt_symbol, bar in bars.items():
            # 更新数据
            self.am[vt_symbol].update_bar(bar)
            self.bars[vt_symbol].append(bar)

            # 检查数据充足性
            if not self.am[vt_symbol].inited:
                self.am[vt_symbol].update_bar(bar)
                if len(self.am[vt_symbol]) < self.init_days:
                    continue
                else:
                    self.am[vt_symbol].inited = True
                    self.write_log(f"{vt_symbol} 数据初始化完成")

            # 计算Dual Thrust指标
            if len(self.bars[vt_symbol]) >= 2:
                yesterday = self.bars[vt_symbol][-2]
                today = bar

                # 计算上下轨
                upper_band, lower_band = self.calculate_bands(yesterday)

                # 生成的交易信号
                if upper_band and lower_band:
                    self.generate_signals(vt_symbol, bar, upper_band, lower_band)

        # 执行交易
        self.execute_trading(bars, price_add=0.0)

    def calculate_bands(self, bar: BarData):
        """计算上下轨"""
        if not hasattr(bar, "high_price") or not hasattr(bar, "low_price"):
            return None, None

        high_range = bar.high_price - bar.low_price
        if high_range <= 0:
            return None, None

        upper_band = bar.high_price + self.k1 * high_range
        lower_band = bar.low_price - self.k2 * high_range

        return upper_band, lower_band

    def generate_signals(
        self, vt_symbol: str, bar: BarData, upper_band: float, lower_band: float
    ) -> None:
        """生成交易信号"""
        long_entry = bar.close_price > upper_band
        short_entry = bar.close_price < lower_band

        current_pos = self.targets[vt_symbol]

        if long_entry and current_pos == 0:
            # 突破上轨，做多
            self.targets[vt_symbol] = self.fixed_size
            self.write_log(
                f"{vt_symbol} 突破上轨买入 "
                f"价格：{bar.close_price:.2f} 上轨：{upper_band:.2f}"
            )

        elif short_entry and current_pos == 0:
            # 突破下轨，做空
            self.targets[vt_symbol] = -self.fixed_size
            self.write_log(
                f"{vt_symbol} 突破下轨卖出 "
                f"价格：{bar.close_price:.2f} 下轨：{lower_band:.2f}"
            )

        elif current_pos > 0 and bar.close_price < lower_band:
            # 多头止损
            self.targets[vt_symbol] = 0
            self.write_log(
                f"{vt_symbol} 多头止损 "
                f"价格：{bar.close_price:.2f} 下轨：{lower_band:.2f}"
            )

        elif current_pos < 0 and bar.close_price > upper_band:
            # 空头止损
            self.targets[vt_symbol] = 0
            self.write_log(
                f"{vt_symbol} 空头止损 "
                f"价格：{bar.close_price:.2f} 上轨：{upper_band:.2f}"
            )

    def on_trade(self, trade: TradeData) -> None:
        """成交回调"""
        msg = f"成交：{trade.vt_symbol} {trade.direction.value} {trade.offset.value} "
        msg += f"价格：{trade.price} 数量：{trade.volume}"
        self.write_log(msg)

    def on_order(self, order: OrderData) -> None:
        """委托回调"""
        pass

    def on_stop(self) -> None:
        """策略停止"""
        pass
