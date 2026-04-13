#!/usr/bin/env python3
"""
Tushare 股指期货数据下载脚本 V2
不依赖 fut_basic 接口，直接生成合约代码
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List
import time

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import tushare as ts
from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
from vnpy.alpha import AlphaLab


class TushareDataDownloaderV2:
    """Tushare 数据下载器 V2 - 不依赖 fut_basic"""

    # Tushare Token
    TUSHARE_TOKEN = "8338d9ae4c26c3ec32cffbd1b337d97228c22ba84cea0996410513bb"

    # 合约交易参数（使用 vn.py 格式）
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

    # 请求延迟（秒）
    # Tushare 免费账号限制：每分钟最多调用 fut_daily 接口 20次
    # 60秒 / 20次 = 3秒/次，我们使用3.5秒确保安全
    REQUEST_DELAY = 3.5
    MAX_RETRIES = 3

    def __init__(self, lab_path: str):
        """初始化"""
        print("初始化 Tushare 连接...")
        ts.set_token(self.TUSHARE_TOKEN)
        self.pro = ts.pro_api()

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

    def _generate_contracts(
        self, symbol: str, start_year: int, end_year: int
    ) -> List[str]:
        """
        生成合约代码列表
        :param symbol: 品种代码 (IF/IH/IC)
        :param start_year: 开始年份
        :param end_year: 结束年份
        :return: 合约代码列表，如 ["IF2404.CFX", "IF2405.CFX", ...]
        """
        contracts = []

        # 股指期货的交割月份：3, 6, 9, 12月
        delivery_months = [3, 6, 9, 12]

        for year in range(start_year, end_year + 1):
            year_suffix = year % 100  # 两位年份后缀

            for month in delivery_months:
                # 生成合约代码
                ts_code = f"{symbol}{year_suffix:02d}{month:02d}.CFX"
                contracts.append(ts_code)

        return contracts

    def download_daily_data(
        self, start_date: str, end_date: str, symbols: List[str] = None
    ):
        """
        下载日线数据
        :param start_date: 开始日期 YYYYMMDD
        :param end_date: 结束日期 YYYYMMDD
        :param symbols: 合约列表，默认下载所有
        """
        if symbols is None:
            symbols = ["IF", "IH", "IC"]

        print(f"\n{'=' * 60}")
        print("开始下载日线数据")
        print(f"时间范围：{start_date} - {end_date}")
        print(f"合约列表：{', '.join(symbols)}")
        print(f"{'=' * 60}\n")

        success_count = 0
        failed_symbols = []

        for symbol in symbols:
            vt_symbol = f"{symbol}.CFFEX"
            print(f"\n[{symbol}] 开始下载 {vt_symbol}...")

            try:
                # 带重试的下载
                bars = self._download_with_retry(symbol, start_date, end_date)

                if bars and len(bars) > 0:
                    # 保存到 AlphaLab
                    self.lab.save_bar_data(bars)

                    print(f"  ✓ {vt_symbol} 下载成功，共 {len(bars)} 条数据")
                    print(
                        f"    时间范围：{bars[0].datetime.date()} ~ {bars[-1].datetime.date()}"
                    )
                    success_count += 1
                else:
                    print(f"  ✗ {vt_symbol} 下载数据为空")
                    failed_symbols.append(symbol)

            except Exception as e:
                print(f"  ✗ {vt_symbol} 下载失败：{str(e)}")
                import traceback

                traceback.print_exc()
                failed_symbols.append(symbol)

        # 打印汇总
        print(f"\n{'=' * 60}")
        print(f"下载完成！")
        print(f"  成功：{success_count}/{len(symbols)}")
        if failed_symbols:
            print(f"  失败：{', '.join(failed_symbols)}")
        print(f"{'=' * 60}\n")

    def _download_with_retry(self, symbol: str, start: str, end: str) -> List[BarData]:
        """带重试机制的下载"""
        for attempt in range(self.MAX_RETRIES):
            try:
                # 调用 Tushare API
                df = self._fetch_from_tushare(symbol, start, end)

                if df is not None and len(df) > 0:
                    # 转换为 BarData
                    bars = self._convert_to_bars(df, symbol)
                    return bars
                else:
                    return []

            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    wait_time = (attempt + 1) * 2  # 指数退避
                    print(f"  第 {attempt + 1} 次尝试失败，{wait_time}秒后重试...")
                    time.sleep(wait_time)
                else:
                    raise e

        return []

    def _fetch_from_tushare(self, symbol: str, start: str, end: str):
        """从 Tushare 获取数据"""
        try:
            # 解析日期范围
            start_dt = datetime.strptime(start, "%Y%m%d")
            end_dt = datetime.strptime(end, "%Y%m%d")

            # 生成合约列表（覆盖过去5年）
            contracts = self._generate_contracts(
                symbol, start_dt.year - 1, end_dt.year + 1
            )

            print(f"    生成 {len(contracts)} 个合约代码")
            print(f"    示例: {contracts[:3]} ... {contracts[-3:]}")

            # 步骤1：下载每个合约的数据
            all_bars = []
            success_count = 0

            for i, ts_code in enumerate(contracts):
                print(f"    [{i + 1}/{len(contracts)}] 下载 {ts_code}...")

                try:
                    df = self.pro.fut_daily(
                        ts_code=ts_code, start_date=start, end_date=end
                    )

                    if df is not None and len(df) > 0:
                        all_bars.append(df)
                        success_count += 1
                        print(f"        ✓ {len(df)} 条数据")
                    else:
                        print(f"        - 无数据（可能合约未上市或已退市）")

                    # 防爬：延迟
                    time.sleep(self.REQUEST_DELAY)

                except Exception as e:
                    print(f"        ✗ 失败：{str(e)}")
                    # 即使失败也延迟
                    time.sleep(self.REQUEST_DELAY)
                    continue

            print(f"    成功下载 {success_count}/{len(contracts)} 个合约")

            # 步骤2：合并所有合约数据
            if all_bars:
                import pandas as pd

                print(f"    合并 {len(all_bars)} 个合约的数据...")

                df_merged = pd.concat(all_bars, ignore_index=True)

                # 按日期去重（保留最新的数据）
                before_dedup = len(df_merged)
                df_merged = df_merged.drop_duplicates(
                    subset=["trade_date"], keep="last"
                )
                print(f"    去重：{before_dedup} -> {len(df_merged)} 条")

                # 按日期排序
                df_merged = df_merged.sort_values("trade_date")

                return df_merged
            else:
                print(f"    没有成功下载任何数据")
                return None

        except Exception as e:
            print(f"    ✗ 异常：{str(e)}")
            import traceback

            traceback.print_exc()

        return None

    def _convert_to_bars(self, df, symbol: str) -> List[BarData]:
        """转换 pandas DataFrame 为 BarData 列表"""
        bars = []
        # 使用 pandas 的 iterrows() 方法
        for _, row in df.iterrows():
            try:
                bar = BarData(
                    symbol=symbol,
                    exchange=Exchange.CFFEX,
                    datetime=datetime.strptime(str(row["trade_date"]), "%Y%m%d"),
                    interval=Interval.DAILY,
                    open_price=float(row["open"]),
                    high_price=float(row["high"]),
                    low_price=float(row["low"]),
                    close_price=float(row["close"]),
                    volume=float(row.get("vol", 0)),
                    turnover=float(row.get("amount", 0)),
                    open_interest=float(row.get("oi", 0)),
                    gateway_name="TUSHARE",
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

    print("=== 脚本开始执行 ===")

    # 计算日期范围（过去5年）
    end_date = datetime(2025, 4, 13)
    start_date = datetime(2020, 4, 13)
    print(f"日期范围: {start_date} - {end_date}")

    end_str = end_date.strftime("%Y%m%d")
    start_str = start_date.strftime("%Y%m%d")

    print(f"\n{'=' * 60}")
    print(f"VNPY 股指期货数据下载器 V2")
    print(f"{'=' * 60}")
    print(f"数据源：Tushare")
    print(f"数据路径：{LAB_PATH}")
    print(f"时间范围：{start_str} - {end_str}")
    print(f"{'=' * 60}\n")

    # 创建下载器
    try:
        downloader = TushareDataDownloaderV2(LAB_PATH)

        # 下载数据
        downloader.download_daily_data(start_str, end_str)

        print(f"\n✓ 数据下载完成！")
        print(f"\n可以使用以下命令验证数据：")
        print(f"  source venv/bin/activate")
        print(
            f"  python -c \"from vnpy.alpha import AlphaLab; lab = AlphaLab('{LAB_PATH}'); print(lab.get_bar_overview())\""
        )

    except Exception as e:
        print(f"\n✗ 下载失败：{str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
