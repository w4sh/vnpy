#!/usr/bin/env python3
"""
动量策略 (Momentum Strategy)

经典动量策略，逻辑：
1. 计算N日收益率
2. 收益率为正且超过阈值时买入
3. 收益率为负且超过阈值时卖出
4. 动量反转时平仓

参数优化空间：
- momentum_window: 动量计算周期
- entry_threshold: 入场阈值
- exit_threshold: 出场阈值
- 持仓时间限制
"""

from collections import defaultdict
import numpy as np

from vnpy.trader.object import BarData, TradeData, OrderData
from vnpy.trader.constant import Direction, Offset
from vnpy.trader.utility import ArrayManager
from vnpy.alpha import AlphaStrategy


class MomentumStrategy(AlphaStrategy):
    """动量策略"""

    # 策略参数
    momentum_window: int = 20  # 动量计算周期
    entry_threshold: float = 0.005  # 入场阈值（0.5%，降低以提高触发频率）
    exit_threshold: float = -0.003  # 出场阈值（-0.3%）
    init_days: int = 30  # 初始化天数
    position_pct: float = 0.2  # 仓位比例（降低到20%避免过度杠杆）

    def on_init(self) -> None:
        """策略初始化"""
        self.write_log(
            f"动量策略初始化（周期={self.momentum_window}, "
            f"入场阈值={self.entry_threshold}）"
        )

        # 数据缓存
        self.am: defaultdict = defaultdict(ArrayManager)
        self.bars: defaultdict = defaultdict(list)

        # 交易状态
        self.entry_bars: defaultdict = defaultdict(object)

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """K线数据回调"""
        for vt_symbol, bar in bars.items():
            # 更新数据
            self.am[vt_symbol].update_bar(bar)
            self.bars[vt_symbol].append(bar)

            # 保持数据长度
            if len(self.bars[vt_symbol]) > self.momentum_window + 10:
                self.bars[vt_symbol] = self.bars[vt_symbol][
                    -(self.momentum_window + 10) :
                ]

            # 检查数据充足性
            if len(self.bars[vt_symbol]) < self.init_days:
                continue

            # 计算动量指标
            momentum = self.calculate_momentum(self.bars[vt_symbol])

            if momentum is not None:
                # 生成交易信号
                self.generate_signals(vt_symbol, bar, momentum)

        # 执行交易
        self.execute_trading(bars, price_add=0.0)

    def calculate_momentum(self, bars: list) -> float:
        """计算动量（N日收益率）"""
        if len(bars) < self.momentum_window + 1:
            return None

        # 计算N日收益率
        current_close = bars[-1].close_price
        past_close = bars[-(self.momentum_window + 1)].close_price

        if past_close > 0:
            momentum = (current_close - past_close) / past_close
        else:
            momentum = 0.0

        return momentum

    def generate_signals(self, vt_symbol: str, bar: BarData, momentum: float) -> None:
        """生成交易信号"""
        current_pos = self.get_target(vt_symbol)

        if momentum > self.entry_threshold and current_pos == 0:
            # 正向动量超阈值，买入
            target_volume = self.calculate_position_size(vt_symbol, bar)
            self.set_target(vt_symbol, target_volume)
            self.entry_bars[vt_symbol] = bar
            self.write_log(
                f"{vt_symbol} 动量买入 价格：{bar.close_price:.2f} 动量：{momentum:.2%}"
            )

        elif momentum < -self.entry_threshold and current_pos == 0:
            # 负向动量超阈值，卖出（做空）
            target_volume = self.calculate_position_size(vt_symbol, bar)
            self.set_target(vt_symbol, -target_volume)
            self.entry_bars[vt_symbol] = bar
            self.write_log(
                f"{vt_symbol} 动量卖出 价格：{bar.close_price:.2f} 动量：{momentum:.2%}"
            )

        elif current_pos > 0:
            # 多头出场条件
            if momentum < self.exit_threshold:
                self.set_target(vt_symbol, 0)
                self.write_log(
                    f"{vt_symbol} 动量转负平多 "
                    f"价格：{bar.close_price:.2f} 动量：{momentum:.2%}"
                )

            # 检查持仓时间
            elif self.should_close_position(vt_symbol, bar):
                self.set_target(vt_symbol, 0)
                self.write_log(
                    f"{vt_symbol} 持仓时间到期平多 价格：{bar.close_price:.2f}"
                )

        elif current_pos < 0:
            # 空头出场条件
            if momentum > -self.exit_threshold:
                self.set_target(vt_symbol, 0)
                self.write_log(
                    f"{vt_symbol} 动量转正平空 "
                    f"价格：{bar.close_price:.2f} 动量：{momentum:.2%}"
                )

            # 检查持仓时间
            elif self.should_close_position(vt_symbol, bar):
                self.set_target(vt_symbol, 0)
                self.write_log(
                    f"{vt_symbol} 持仓时间到期平空 价格：{bar.close_price:.2f}"
                )

    def should_close_position(self, vt_symbol: str, bar: BarData) -> bool:
        """检查是否应该平仓（持仓时间限制）"""
        if vt_symbol in self.entry_bars:
            entry_bar = self.entry_bars[vt_symbol]
            holding_days = (bar.datetime - entry_bar.datetime).days
            # 持仓超过60天强制平仓
            return holding_days > 60
        return False

    def calculate_position_size(self, vt_symbol: str, bar: BarData) -> int:
        """计算仓位大小"""
        cash = self.get_cash_available()
        target_value = cash * self.position_pct
        target_volume = int(target_value / bar.close_price)
        return max(100, target_volume)  # 至少100股

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
