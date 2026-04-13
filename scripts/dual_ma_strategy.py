#!/usr/bin/env python3
"""
双均线策略（Dual Moving Average Strategy）
逻辑：
- 快线上穿慢线：买入（做多）
- 快线下穿慢线：卖出（平仓或做空）
"""

from collections import defaultdict


from vnpy.trader.object import BarData, TradeData
from vnpy.alpha import AlphaStrategy


class DualMaStrategy(AlphaStrategy):
    """双均线策略"""

    # 策略参数
    fast_window: int = 5  # 快线周期
    slow_window: int = 20  # 慢线周期
    position_pct: float = 0.95  # 仓位比例

    def on_init(self) -> None:
        """策略初始化"""
        self.write_log(
            f"双均线策略初始化（快线：{self.fast_window}，慢线：{self.slow_window}）"
        )

        # 历史数据缓存（每个品种独立）
        self.history_data: defaultdict = defaultdict(list)
        self.fast_mas: defaultdict = defaultdict(float)
        self.slow_mas: defaultdict = defaultdict(float)

        # 记录上一时刻的均线值（用于判断交叉）
        self.last_fast_mas: defaultdict = defaultdict(float)
        self.last_slow_mas: defaultdict = defaultdict(float)

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """K线数据回调"""
        for vt_symbol, bar in bars.items():
            # 更新历史数据
            self.history_data[vt_symbol].append(bar)

            # 保持足够的数据长度（比慢线周期多10条，避免边缘效应）
            max_length = self.slow_window + 10
            if len(self.history_data[vt_symbol]) > max_length:
                self.history_data[vt_symbol] = self.history_data[vt_symbol][
                    -max_length:
                ]

            # 计算均线
            if len(self.history_data[vt_symbol]) >= self.slow_window:
                current_fast_ma = self._calculate_ma(
                    self.history_data[vt_symbol], self.fast_window
                )
                current_slow_ma = self._calculate_ma(
                    self.history_data[vt_symbol], self.slow_window
                )

                self.fast_mas[vt_symbol] = current_fast_ma
                self.slow_mas[vt_symbol] = current_slow_ma

                # 生成交易信号（只在有足够数据时）
                last_fast = self.last_fast_mas.get(vt_symbol, None)
                last_slow = self.last_slow_mas.get(vt_symbol, None)

                if last_fast is not None and last_slow is not None:
                    # 判断交叉
                    # 金叉：快线上穿慢线
                    if last_fast <= last_slow and current_fast_ma > current_slow_ma:
                        self.write_log(
                            f"{vt_symbol} 金叉 "
                            f"快线：{last_fast:.2f}->{current_fast_ma:.2f} "
                            f"慢线：{last_slow:.2f}->{current_slow_ma:.2f}"
                        )

                        # 计算目标仓位
                        target_volume = self._calculate_position_size(vt_symbol, bar)
                        self.set_target(vt_symbol, target_volume)

                    # 死叉：快线下穿慢线
                    elif last_fast >= last_slow and current_fast_ma < current_slow_ma:
                        self.write_log(
                            f"{vt_symbol} 死叉 "
                            f"快线：{last_fast:.2f}->{current_fast_ma:.2f} "
                            f"慢线：{last_slow:.2f}->{current_slow_ma:.2f}"
                        )

                        # 平仓
                        self.set_target(vt_symbol, 0)

                # 更新上一时刻的均线值
                self.last_fast_mas[vt_symbol] = current_fast_ma
                self.last_slow_mas[vt_symbol] = current_slow_ma

        # 执行交易
        self.execute_trading(bars, price_add=0.0)

    def _calculate_ma(self, data: list[BarData], window: int) -> float:
        """计算简单移动平均"""
        if len(data) < window:
            return 0.0

        close_prices = [bar.close_price for bar in data[-window:]]
        return sum(close_prices) / window

    def _calculate_position_size(self, vt_symbol: str, bar: BarData) -> float:
        """
        计算目标仓位大小
        简化版：每次使用固定比例的资金，使用默认合约乘数
        """
        # 获取可用资金
        cash = self.get_cash_available()

        # 计算目标价值
        target_value = cash * self.position_pct

        # 使用默认合约乘数（股指期货通常是300或200）
        # IF/IH: 300, IC: 200
        if "IC" in vt_symbol:
            size = 200
        else:
            size = 300

        target_volume = int(target_value / (bar.close_price * size))

        return max(0, target_volume)

    def on_trade(self, trade: TradeData) -> None:
        """成交回调"""
        msg = f"成交：{trade.vt_symbol} {trade.direction.value} {trade.offset.value} "
        msg += f"价格：{trade.price} 数量：{trade.volume}"
        self.write_log(msg)
