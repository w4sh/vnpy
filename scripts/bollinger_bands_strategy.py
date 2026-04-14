#!/usr/bin/env python3
"""
布林带策略 (Bollinger Bands Strategy)

经典趋势跟踪策略，逻辑：
1. 计算中轨：N日移动平均线
2. 计算上下轨：中轨 ± k倍标准差
3. 价格触及下轨买入，触及上轨卖出
4. 可结合其他指标过滤信号

参数优化空间：
- ma_window: 均线周期
- std_window: 标准差周期
- dev_mult: 标准差倍数
- 超买超卖过滤
"""

from collections import defaultdict
import numpy as np

from vnpy.trader.object import BarData, TradeData, OrderData
from vnpy.trader.constant import Direction, Offset
from vnpy.trader.utility import ArrayManager
from vnpy.alpha import AlphaStrategy


class BollingerBandsStrategy(AlphaStrategy):
    """布林带策略"""

    # 策略参数
    ma_window: int = 20  # 均线周期
    std_window: int = 20  # 标准差周期
    dev_mult: float = 2.0  # 标准差倍数
    init_days: int = 30  # 初始化天数
    position_pct: float = 0.2  # 仓位比例（降低到20%避免过度杠杆）

    def on_init(self) -> None:
        """策略初始化"""
        self.write_log(
            f"布林带策略初始化（周期={self.ma_window}, 倍数={self.dev_mult}）"
        )

        # 数据缓存
        self.am: defaultdict = defaultdict(ArrayManager)
        self.bars: defaultdict = defaultdict(list)

        # 交易状态
        self.signals: defaultdict = defaultdict(str)

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """K线数据回调"""
        for vt_symbol, bar in bars.items():
            # 更新数据
            self.am[vt_symbol].update_bar(bar)
            self.bars[vt_symbol].append(bar)

            # 保持数据长度
            if len(self.bars[vt_symbol]) > self.ma_window + 10:
                self.bars[vt_symbol] = self.bars[vt_symbol][-(self.ma_window + 10) :]

            # 检查数据充足性
            if len(self.bars[vt_symbol]) < self.init_days:
                continue

            # 计算布林带指标
            ma, upper_band, lower_band = self.calculate_bollinger_bands(
                self.bars[vt_symbol]
            )

            if ma and upper_band and lower_band:
                # 计算位置百分比（用于调试）
                if upper_band != lower_band:
                    bb_position = (bar.close_price - lower_band) / (
                        upper_band - lower_band
                    )
                else:
                    bb_position = 0.5

                # 每10天输出一次调试信息
                if len(self.bars[vt_symbol]) % 10 == 0:
                    self.write_log(
                        f"{vt_symbol} 调试: 价格={bar.close_price:.2f}, "
                        f"中轨={ma:.2f}, 上轨={upper_band:.2f}, "
                        f"下轨={lower_band:.2f}, 位置={bb_position:.2f}"
                    )

                # 生成交易信号
                self.generate_signals(vt_symbol, bar, ma, upper_band, lower_band)

        # 执行交易
        self.execute_trading(bars, price_add=0.0)

    def calculate_bollinger_bands(self, bars: list):
        """计算布林带"""
        if len(bars) < self.ma_window:
            return None, None, None

        # 计算中轨（移动平均）
        closes = [bar.close_price for bar in bars[-self.ma_window :]]
        ma = sum(closes) / len(closes)

        # 计算标准差
        if len(bars) < self.std_window:
            return ma, None, None

        std_closes = [bar.close_price for bar in bars[-self.std_window :]]
        std = np.std(std_closes)

        # 计算上下轨
        upper_band = ma + self.dev_mult * std
        lower_band = ma - self.dev_mult * std

        return ma, upper_band, lower_band

    def generate_signals(
        self,
        vt_symbol: str,
        bar: BarData,
        ma: float,
        upper_band: float,
        lower_band: float,
    ) -> None:
        """生成交易信号"""
        # 计算位置百分比
        if upper_band != lower_band:
            bb_position = (bar.close_price - lower_band) / (upper_band - lower_band)
        else:
            bb_position = 0.5

        current_pos = self.get_target(vt_symbol)

        # 信号逻辑（降低阈值以提高触发频率）
        if bb_position <= 0.2 and current_pos == 0:
            # 价格触及下轨20%位置，超卖买入
            target_volume = self.calculate_position_size(vt_symbol, bar)
            self.set_target(vt_symbol, target_volume)
            self.write_log(
                f"{vt_symbol} 布林带下轨买入 "
                f"价格：{bar.close_price:.2f} 下轨：{lower_band:.2f} "
                f"位置：{bb_position:.2f}"
            )
            self.signals[vt_symbol] = "buy"

        elif bb_position >= 0.8 and current_pos == 0:
            # 价格触及上轨80%位置，超买卖出（做空）
            target_volume = self.calculate_position_size(vt_symbol, bar)
            self.set_target(vt_symbol, -target_volume)
            self.write_log(
                f"{vt_symbol} 布林带上轨卖出 "
                f"价格：{bar.close_price:.2f} 上轨：{upper_band:.2f} "
                f"位置：{bb_position:.2f}"
            )
            self.signals[vt_symbol] = "sell"

        elif bb_position >= 0.5 and current_pos > 0:
            # 价格回到中轨附近，平多仓
            self.set_target(vt_symbol, 0)
            self.write_log(
                f"{vt_symbol} 价格回归中轨平多 "
                f"价格：{bar.close_price:.2f} 中轨：{ma:.2f}"
            )

        elif bb_position <= 0.5 and current_pos < 0:
            # 价格回到中轨附近，平空仓
            self.set_target(vt_symbol, 0)
            self.write_log(
                f"{vt_symbol} 价格回归中轨平空 "
                f"价格：{bar.close_price:.2f} 中轨：{ma:.2f}"
            )

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
