#!/usr/bin/env python3
"""
布林带选股系统
基于布林带指标筛选符合条件的股票

选股策略：
1. 超卖策略：价格触及下轨（买入机会）
2. 超买策略：价格触及上轨（卖出机会）
3. 突破策略：价格突破布林带
4. 波动率筛选：布林带宽度过滤
5. 趋势确认：结合均线方向
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from vnpy.trader.constant import Interval
from vnpy.alpha import AlphaLab


class BollingerStockPicker:
    """布林带选股器"""

    def __init__(self, lab_path: str):
        """初始化"""
        self.lab = AlphaLab(lab_path)
        self.results: defaultdict = defaultdict(list)

    def scan_stocks(
        self,
        stock_list: list[str],
        ma_window: int = 20,
        std_window: int = 20,
        dev_mult: float = 2.0,
        min_price: float = 3.0,
        max_price: float = 300.0,
        min_volume: int = 1000000,
        scan_date: datetime = None,
    ) -> dict[str, list[dict]]:
        """
        扫描股票池

        参数：
        - stock_list: 股票代码列表
        - ma_window: 均线周期
        - std_window: 标准差周期
        - dev_mult: 标准差倍数
        - min_price: 最低价格（过滤低价股）
        - max_price: 最高价格（过滤高价股）
        - min_volume: 最小成交量
        - scan_date: 扫描日期（默认为最新交易日）
        """
        print("=" * 60)
        print("布林带选股系统")
        print("=" * 60)
        print("\n选股参数：")
        print(f"  股票数量：{len(stock_list)}")
        print(f"  均线周期：{ma_window}")
        print(f"  标准差周期：{std_window}")
        print(f"  标准差倍数：{dev_mult}")
        print(f"  价格范围：{min_price} - {max_price} 元")
        print(f"  最小成交量：{min_volume:,}")

        # 如果没有指定日期，使用当前日期
        if scan_date is None:
            scan_date = datetime.now()
            # 往前推5年确保有足够数据
            start_date = scan_date - timedelta(days=365 * 5)
        else:
            start_date = scan_date - timedelta(days=365 * 5)

        print(f"  扫描日期：{scan_date.date()}")
        print("\n开始扫描...")

        # 扫描计数
        total_scanned = 0
        oversold_count = 0  # 超卖
        overbought_count = 0  # 超买
        breakout_up_count = 0  # 向上突破
        breakout_down_count = 0  # 向下突破

        for i, vt_symbol in enumerate(stock_list, 1):
            try:
                # 加载历史数据
                bars = self.lab.load_bar_data(
                    vt_symbol, Interval.DAILY, start_date, scan_date
                )

                if not bars or len(bars) < std_window + 10:
                    continue

                total_scanned += 1

                # 获取最新数据
                latest_bar = bars[-1]

                # 价格过滤
                if (
                    latest_bar.close_price < min_price
                    or latest_bar.close_price > max_price
                ):
                    continue

                # 成交量过滤
                if latest_bar.volume < min_volume:
                    continue

                # 计算布林带指标
                bb_data = self.calculate_bollinger_bands(
                    bars, ma_window, std_window, dev_mult
                )

                if not bb_data:
                    continue

                # 分析信号
                signals = self.analyze_signals(bb_data, latest_bar)

                # 如果有信号，添加到结果
                if signals:
                    stock_info = {
                        "vt_symbol": vt_symbol,
                        "close_price": latest_bar.close_price,
                        "volume": latest_bar.volume,
                        "bb_position": bb_data["bb_position"],
                        "upper_band": bb_data["upper_band"],
                        "middle_band": bb_data["middle_band"],
                        "lower_band": bb_data["lower_band"],
                        "bb_width": bb_data["bb_width"],
                        "signals": signals,
                    }

                    # 分类存储
                    for signal in signals:
                        self.results[signal].append(stock_info)
                        if signal == "oversold":
                            oversold_count += 1
                        elif signal == "overbought":
                            overbought_count += 1
                        elif signal == "breakout_up":
                            breakout_up_count += 1
                        elif signal == "breakout_down":
                            breakout_down_count += 1

                # 进度显示
                if i % 500 == 0:
                    print(
                        f"  已扫描：{i}/{len(stock_list)} ({i / len(stock_list) * 100:.1f}%)"
                    )

            except Exception:
                # 跳过有问题的股票
                continue

        # 统计结果
        print("\n扫描完成！")
        print("=" * 60)
        print(f"总扫描股票：{total_scanned}")
        print(
            f"符合条件：{oversold_count + overbought_count + breakout_up_count + breakout_down_count}"
        )
        print(f"  超卖信号（买入机会）：{oversold_count}")
        print(f"  超买信号（卖出机会）：{overbought_count}")
        print(f"  向上突破：{breakout_up_count}")
        print(f"  向下突破：{breakout_down_count}")

        return self.results

    def calculate_bollinger_bands(
        self, bars: list, ma_window: int, std_window: int, dev_mult: float
    ) -> dict:
        """计算布林带指标"""
        if len(bars) < std_window:
            return None

        # 计算中轨（移动平均）
        closes = [bar.close_price for bar in bars[-ma_window:]]
        middle_band = sum(closes) / len(closes)

        # 计算标准差
        std_closes = [bar.close_price for bar in bars[-std_window:]]
        import numpy as np

        std = np.std(std_closes)

        # 计算上下轨
        upper_band = middle_band + dev_mult * std
        lower_band = middle_band - dev_mult * std

        # 计算布林带宽度（百分比）
        if middle_band > 0:
            bb_width = (upper_band - lower_band) / middle_band * 100
        else:
            bb_width = 0

        # 获取最新价格
        latest_price = bars[-1].close_price

        # 计算布林带位置（0-1之间）
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

    def analyze_signals(self, bb_data: dict, bar) -> list[str]:
        """分析布林带信号"""
        signals = []
        bb_position = bb_data["bb_position"]
        bb_width = bb_data["bb_width"]

        # 1. 超卖信号（买入机会）
        if bb_position <= 0.15:
            signals.append("oversold")

        # 2. 超买信号（卖出机会）
        elif bb_position >= 0.85:
            signals.append("overbought")

        # 3. 向上突破
        elif bb_position >= 0.7 and bb_width > 5:
            signals.append("breakout_up")

        # 4. 向下突破
        elif bb_position <= 0.3 and bb_width > 5:
            signals.append("breakout_down")

        # 5. 收缩信号（可能即将突破）
        if bb_width < 2 and 0.4 <= bb_position <= 0.6:
            signals.append("squeeze")

        return signals

    def save_results(self, output_dir: str = "/Users/w4sh8899/project/vnpy/output"):
        """保存选股结果"""

        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 保存各类信号结果
        for signal_type, stocks in self.results.items():
            if not stocks:
                continue

            # 按布林带位置排序
            sorted_stocks = sorted(stocks, key=lambda x: x["bb_position"])

            filename = output_path / f"stock_picker_{signal_type}_{timestamp}.txt"

            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"布林带选股结果 - {signal_type}\n")
                f.write(f"扫描时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"股票数量：{len(sorted_stocks)}\n")
                f.write("=" * 60 + "\n\n")

                for i, stock in enumerate(sorted_stocks, 1):
                    f.write(f"第 {i} 只：{stock['vt_symbol']}\n")
                    f.write(f"  价格：{stock['close_price']:.2f} 元\n")
                    f.write(f"  成交量：{stock['volume']:,}\n")
                    f.write(f"  布林带位置：{stock['bb_position']:.2%}\n")
                    f.write(f"  上轨：{stock['upper_band']:.2f}\n")
                    f.write(f"  中轨：{stock['middle_band']:.2f}\n")
                    f.write(f"  下轨：{stock['lower_band']:.2f}\n")
                    f.write(f"  布林带宽度：{stock['bb_width']:.2f}%\n")
                    f.write(f"  信号类型：{', '.join(stock['signals'])}\n")
                    f.write("\n")

            print(f"✓ {signal_type} 结果已保存：{filename.name}")

        # 生成汇总报告
        self._generate_summary_report(output_path, timestamp)

    def _generate_summary_report(self, output_path: Path, timestamp: str):
        """生成汇总报告"""
        filename = output_path / f"stock_picker_summary_{timestamp}.txt"

        with open(filename, "w", encoding="utf-8") as f:
            f.write("布林带选股汇总报告\n")
            f.write(f"扫描时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")

            for signal_type, stocks in self.results.items():
                if not stocks:
                    continue

                f.write(f"{signal_type.upper()}\n")
                f.write("-" * 60 + "\n")
                f.write(f"股票数量：{len(stocks)}\n")
                f.write("股票列表：\n")

                for stock in stocks[:20]:  # 只显示前20个
                    f.write(
                        f"  {stock['vt_symbol']:15s} "
                        f"价格:{stock['close_price']:8.2f} "
                        f"位置:{stock['bb_position']:6.2%}\n"
                    )

                if len(stocks) > 20:
                    f.write(f"  ... 还有 {len(stocks) - 20} 只股票\n")

                f.write("\n")

        print(f"✓ 汇总报告已保存：{filename.name}")

    def get_stock_list(self, source: str = "local") -> list[str]:
        """获取股票列表"""
        # 从 lab_data/daily 目录读取已下载的股票
        daily_dir = Path("/Users/w4sh8899/project/vnpy/lab_data/daily")

        if daily_dir.exists():
            # 获取所有 .parquet 文件
            parquet_files = list(daily_dir.glob("*.parquet"))

            # 提取股票代码
            stock_list = [f.stem for f in parquet_files]

            print(f"从本地数据加载股票列表：{len(stock_list)} 只")
            return stock_list
        else:
            print("数据目录不存在，请先运行数据下载脚本")
            return []


def main():
    """主函数"""
    picker = BollingerStockPicker("/Users/w4sh8899/project/vnpy/lab_data")

    # 获取股票列表
    stock_list = picker.get_stock_list()

    if not stock_list:
        print("无法获取股票列表")
        return

    # 执行选股扫描
    _results = picker.scan_stocks(
        stock_list=stock_list,
        ma_window=20,
        std_window=20,
        dev_mult=2.0,
        min_price=5.0,  # 最低5元
        max_price=200.0,  # 最高200元
        min_volume=5000000,  # 最小500万成交量
    )

    # 保存结果
    picker.save_results()

    print("\n选股完成！")


if __name__ == "__main__":
    main()
