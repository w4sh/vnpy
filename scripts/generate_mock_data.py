#!/usr/bin/env python3
"""
生成模拟股指期货数据（用于快速验证回测流程）
生成带有明显趋势的数据，便于观察双均线策略效果
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import random

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
from vnpy.alpha import AlphaLab


def generate_mock_data(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    initial_price: float = 3000.0,
    trend: float = 0.0001,  # 每日趋势
    volatility: float = 0.02,  # 波动率
) -> list[BarData]:
    """
    生成模拟K线数据
    :param symbol: 合约代码
    :param start_date: 开始日期
    :param end_date: 结束日期
    :param initial_price: 初始价格
    :param trend: 每日趋势（正数上涨，负数下跌）
    :param volatility: 波动率
    """
    bars = []
    current_date = start_date
    current_price = initial_price

    while current_date <= end_date:
        # 生成日内数据
        # 简单的随机游走模型
        daily_return = trend + random.gauss(0, volatility)

        open_price = current_price * (1 + random.gauss(0, volatility * 0.5))
        close_price = current_price * (1 + daily_return)
        high_price = max(open_price, close_price) * (
            1 + abs(random.gauss(0, volatility * 0.3))
        )
        low_price = min(open_price, close_price) * (
            1 - abs(random.gauss(0, volatility * 0.3))
        )

        volume = random.randint(10000, 50000)
        turnover = volume * close_price * random.uniform(0.8, 1.2)

        bar = BarData(
            symbol=symbol.split(".")[0],
            exchange=Exchange.CFFEX,
            datetime=current_date,
            interval=Interval.DAILY,
            open_price=round(open_price, 2),
            high_price=round(high_price, 2),
            low_price=round(low_price, 2),
            close_price=round(close_price, 2),
            volume=volume,
            turnover=round(turnover, 2),
            open_interest=random.randint(5000, 20000),
            gateway_name="MOCK",
        )

        bars.append(bar)
        current_price = close_price

        # 下一个交易日（跳过周末）
        current_date += timedelta(days=1)
        while current_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
            current_date += timedelta(days=1)

    return bars


def main():
    """主函数"""
    LAB_PATH = "/Users/w4sh8899/project/vnpy/lab_data"

    # 生成2年的模拟数据（便于观察策略效果）
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * 2)

    print(f"\n{'=' * 60}")
    print("生成模拟股指期货数据")
    print(f"{'=' * 60}")
    print(f"时间范围：{start_date.date()} ~ {end_date.date()}")
    print("数据品种：IF.CFFEX, IH.CFFEX, IC.CFFEX")
    print(f"{'=' * 60}\n")

    # 初始化 AlphaLab
    lab = AlphaLab(LAB_PATH)

    # 配置合约参数
    contracts = {
        "IF.CFFEX": {
            "long_rate": 0.0001,
            "short_rate": 0.0001,
            "size": 300,
            "pricetick": 0.2,
        },
        "IH.CFFEX": {
            "long_rate": 0.0001,
            "short_rate": 0.0001,
            "size": 300,
            "pricetick": 0.2,
        },
        "IC.CFFEX": {
            "long_rate": 0.0001,
            "short_rate": 0.0001,
            "size": 200,
            "pricetick": 0.2,
        },
    }

    for vt_symbol, settings in contracts.items():
        lab.add_contract_setting(vt_symbol, **settings)
        print(f"✓ 配置 {vt_symbol}")

    # 生成三个品种的数据（不同的趋势）
    configs = [
        ("IF.CFFEX", 3000.0, 0.0005, 0.025),  # 强势上涨
        ("IH.CFFEX", 2500.0, 0.0002, 0.020),  # 温和上涨
        ("IC.CFFEX", 5000.0, -0.0001, 0.030),  # 震荡略偏空
    ]

    for symbol, init_price, trend, vol in configs:
        print(f"\n生成 {symbol} 数据...")
        bars = generate_mock_data(symbol, start_date, end_date, init_price, trend, vol)

        # 保存到 AlphaLab
        lab.save_bar_data(bars)

        print(f"  ✓ {symbol}: {len(bars)} 条数据")
        print(f"    价格范围：{bars[0].close_price:.2f} ~ {bars[-1].close_price:.2f}")

    print(f"\n{'=' * 60}")
    print("✓ 模拟数据生成完成！")
    print(f"{'=' * 60}\n")

    # 验证数据
    print("\n验证数据...")
    try:
        from vnpy.trader.constant import Interval

        bars = lab.load_bar_data("IF.CFFEX", Interval.DAILY, "2024-01-01", "2024-12-31")
        print(f"✓ IF.CFFEX: {len(bars)} 条数据")
        if bars:
            print(f"  时间范围：{bars[0].datetime.date()} ~ {bars[-1].datetime.date()}")
    except Exception as e:
        print(f"验证失败：{e}")


if __name__ == "__main__":
    main()
