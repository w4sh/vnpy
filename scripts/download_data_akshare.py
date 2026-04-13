#!/usr/bin/env python3
"""
AKShare 股指期货数据下载脚本
优势：免费、无频率限制、速度快（5-10分钟完成）
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import time

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import akshare as ak
from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
from vnpy.alpha import AlphaLab


class AkshareDataDownloader:
    """AKShare 数据下载器"""

    # 合约交易参数（与 Tushare 保持一致）
    CONTRACT_SETTINGS = {
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

    def __init__(self, lab_path: str):
        """初始化"""
        print("初始化 AKShare 连接...")
        print(f"AKShare 版本: {ak.__version__}")

        print("初始化 AlphaLab...")
        self.lab = AlphaLab(lab_path)

        # 配置合约信息
        self._setup_contracts()

    def _setup_contracts(self):
        """配置合约交易参数"""
        print("配置合约交易参数...")
        for vt_symbol, settings in self.CONTRACT_SETTINGS.items():
            self.lab.add_contract_setting(vt_symbol, **settings)
            print(
                f"  ✓ {vt_symbol}: 手续费={settings['long_rate']:.4f}, "
                f"乘数={settings['size']}, 最小变动={settings['pricetick']}"
            )

    def download_daily_data(
        self, start_date: str = None, end_date: str = None, symbols: list = None
    ):
        """
        下载日线数据
        :param start_date: 开始日期 YYYYMMDD（可选，默认5年前）
        :param end_date: 结束日期 YYYYMMDD（可选，默认今天）
        :param symbols: 合约列表，默认下载 IF/IH/IC
        """
        if symbols is None:
            symbols = ["IF", "IH", "IC"]

        # 计算日期范围
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        if start_date is None:
            start_dt = datetime.now() - timedelta(days=365 * 5)
            start_date = start_dt.strftime("%Y%m%d")

        print(f"\n{'=' * 60}")
        print("开始下载日线数据（AKShare）")
        print(f"时间范围：{start_date} - {end_date}")
        print(f"合约列表：{', '.join(symbols)}")
        print(f"{'=' * 60}\n")

        # 连续合约映射（AKShare 使用 99 结尾的连续合约）
        continuous_contracts = {
            "IF": "IF99",  # 沪深300连续合约
            "IH": "IH99",  # 上证50连续合约
            "IC": "IC99",  # 中证500连续合约
        }

        success_count = 0
        failed_symbols = []

        for symbol in symbols:
            vt_symbol = f"{symbol}.CFFEX"
            continuous_code = continuous_contracts.get(symbol)

            if not continuous_code:
                print(f"  ✗ {symbol} 没有对应的连续合约代码")
                failed_symbols.append(symbol)
                continue

            print(f"\n[{symbol}] 开始下载 {vt_symbol}...")
            print(f"    连续合约代码: {continuous_code}")

            try:
                # 下载连续合约数据
                df = self._fetch_from_akshare(continuous_code, start_date, end_date)

                if df is not None and len(df) > 0:
                    # 转换为 BarData
                    bars = self._convert_to_bars(df, symbol)

                    if len(bars) > 0:
                        # 保存到 AlphaLab
                        self.lab.save_bar_data(bars)

                        print(f"  ✓ {vt_symbol} 下载成功，共 {len(bars)} 条数据")
                        print(
                            f"    时间范围：{bars[0].datetime.date()} ~ {bars[-1].datetime.date()}"
                        )
                        success_count += 1
                    else:
                        print(f"  ✗ {vt_symbol} 数据转换失败")
                        failed_symbols.append(symbol)
                else:
                    print(f"  ✗ {vt_symbol} 下载数据为空")
                    failed_symbols.append(symbol)

                # 轻微延迟（避免过于频繁的请求）
                time.sleep(1)

            except Exception as e:
                print(f"  ✗ {vt_symbol} 下载失败：{str(e)}")
                import traceback

                traceback.print_exc()
                failed_symbols.append(symbol)

        # 打印汇总
        print(f"\n{'=' * 60}")
        print("下载完成！")
        print(f"  成功：{success_count}/{len(symbols)}")
        if failed_symbols:
            print(f"  失败：{', '.join(failed_symbols)}")
        print(f"{'=' * 60}\n")

    def _fetch_from_akshare(self, symbol: str, start: str, end: str):
        """
        从 AKShare 获取数据
        :param symbol: 连续合约代码（如 IF99）
        :param start: 开始日期 YYYYMMDD
        :param end: 结束日期 YYYYMMDD
        """
        try:
            print(f"    调用 AKShare API: futures_zh_daily_sina")
            print(f"    参数: symbol={symbol}, adjust='0'")

            # AKShare 获取期货日线数据（新浪财经源）
            # 注意：该函数只接受 symbol 参数，不支持 adjust 参数
            df = ak.futures_zh_daily_sina(symbol=symbol)

            if df is None or len(df) == 0:
                print(f"    ⚠ AKShare 返回空数据")
                return None

            print(f"    ✓ AKShare 返回 {len(df)} 条数据")

            # AKShare 返回的字段映射
            # date, open, high, low, close, volume, hold

            # 按日期过滤
            df["date"] = df["date"].astype(str)
            df = df[(df["date"] >= start) & (df["date"] <= end)]

            if len(df) == 0:
                print(f"    ⚠ 过滤后无数据")
                return None

            print(f"    ✓ 过滤后剩余 {len(df)} 条数据")

            return df

        except Exception as e:
            print(f"    ✗ AKShare API 调用失败：{str(e)}")
            import traceback

            traceback.print_exc()
            return None

    def _convert_to_bars(self, df, symbol: str) -> list:
        """
        转换 pandas DataFrame 为 BarData 列表
        """
        bars = []

        for _, row in df.iterrows():
            try:
                # 解析日期（AKShare 格式：YYYY-MM-DD）
                trade_date = str(row["date"])
                dt = datetime.strptime(trade_date, "%Y-%m-%d")

                bar = BarData(
                    symbol=symbol,
                    exchange=Exchange.CFFEX,
                    datetime=dt,
                    interval=Interval.DAILY,
                    open_price=float(row["open"]),
                    high_price=float(row["high"]),
                    low_price=float(row["low"]),
                    close_price=float(row["close"]),
                    volume=float(row["volume"]),
                    turnover=0.0,  # AKShare 没有成交额数据
                    open_interest=float(row["hold"]),  # 持仓量
                    gateway_name="AKSHARE",
                )
                bars.append(bar)
            except Exception as e:
                print(f"    转换数据行时出错：{str(e)}")
                continue

        return bars


def main():
    """主函数"""
    # 配置参数
    LAB_PATH = "/Users/w4sh8899/project/vnpy/lab_data"

    # 计算日期范围（过去5年）
    end_date = datetime(2025, 4, 13)
    start_date = datetime(2020, 4, 13)

    end_str = end_date.strftime("%Y%m%d")
    start_str = start_date.strftime("%Y%m%d")

    print(f"\n{'=' * 60}")
    print("VNPY 股指期货数据下载器（AKShare 版本）")
    print(f"{'=' * 60}")
    print("数据源：AKShare（新浪财经）")
    print(f"数据路径：{LAB_PATH}")
    print(f"时间范围：{start_str} - {end_str}")
    print("特点：免费、无频率限制、速度快")
    print(f"{'=' * 60}\n")

    # 创建下载器
    try:
        downloader = AkshareDataDownloader(LAB_PATH)

        # 下载数据
        downloader.download_daily_data(start_str, end_str)

        print("\n✓ 数据下载完成！")
        print("\n可以使用以下命令验证数据：")
        print("  source venv/bin/activate")
        print(
            f"  python -c \"from vnpy.alpha import AlphaLab; lab = AlphaLab('{LAB_PATH}'); print(lab.get_bar_overview())\""
        )

        print("\n📊 数据统计：")
        print("  可使用以下命令查看数据详情：")
        print(
            f"  python -c \"import polars as pl; df = pl.read_parquet('{LAB_PATH}/daily/IF.CFFEX.parquet'); print(df)\""
        )

    except Exception as e:
        print(f"\n✗ 下载失败：{str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
