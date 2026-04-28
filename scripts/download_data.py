#!/usr/bin/env python3
"""
Tushare 股指期货数据下载脚本
功能：下载 IF/IH/IC 主力连续合约的日线数据
防爬：添加延迟和重试机制，避免被封禁
"""

import sys
from pathlib import Path
from datetime import datetime
import time

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import tushare as ts

from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
from vnpy.alpha import AlphaLab


class TushareDataDownloader:
    """Tushare 数据下载器"""

    # Tushare Token
    TUSHARE_TOKEN = "8338d9ae4c26c3ec32cffbd1b337d97228c22ba84cea0996410513bb"

    # 股指期货合约映射（注意：Tushare 使用 .CFX 后缀，vn.py 使用 CFFEX 交易所）
    FUTURES_MAP = {
        "IF": "IF.CFFEX",  # 沪深300股指期货（vn.py格式，用于保存）
        "IH": "IH.CFFEX",  # 上证50股指期货
        "IC": "IC.CFFEX",  # 中证500股指期货
    }

    # Tushare 合约后缀（用于 API 调用）
    TUSHARE_SUFFIX = ".CFX"

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

    # 防爬策略：请求间隔（秒）
    # Tushare 免费账号限制：每天最多调用 fut_basic 10次
    REQUEST_DELAY = 35  # 35秒延迟，避免触发频率限制
    MAX_RETRIES = 3

    def __init__(self, lab_path: str):
        """
        初始化
        :param lab_path: AlphaLab 数据路径
        """
        print("初始化 Tushare 连接...")
        ts.set_token(self.TUSHARE_TOKEN)
        self.pro = ts.pro_api()

        print("初始化 AlphaLab...")
        self.lab = AlphaLab(lab_path)

        # 配置合约信息
        self._setup_contracts()

        # 预加载所有合约列表（调用1次 fut_basic）
        print("预加载合约列表...")
        self.all_contracts = self._load_all_contracts()
        print(f"  ✓ 共加载 {len(self.all_contracts)} 个合约")

    def _load_all_contracts(self):
        """加载所有合约列表（只调用一次 fut_basic）"""
        try:
            df = self.pro.fut_basic(
                exchange="CFFEX",  # Tushare 使用 CFFEX 作为交易所代码
                fut_type="1",  # 股指期货
                fields="ts_code,symbol,name,list_date,delist_date",
            )
            return df
        except Exception as e:
            print(f"  ✗ 加载合约列表失败：{str(e)}")
            print("  提示：Tushare 免费账号每天最多调用 fut_basic 接口 10 次")
            import pandas as pd

            return pd.DataFrame()

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
        self, start_date: str, end_date: str, symbols: list[str] = None
    ):
        """
        下载日线数据
        :param start_date: 开始日期 YYYYMMDD
        :param end_date: 结束日期 YYYYMMDD
        :param symbols: 合约列表，默认下载所有
        """
        if symbols is None:
            symbols = list(self.FUTURES_MAP.keys())

        print(f"\n{'=' * 60}")
        print("开始下载日线数据")
        print(f"时间范围：{start_date} - {end_date}")
        print(f"合约列表：{', '.join(symbols)}")
        print(f"{'=' * 60}\n")

        success_count = 0
        failed_symbols = []

        for symbol in symbols:
            vt_symbol = self.FUTURES_MAP[symbol]
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

                # 防爬：延迟
                time.sleep(self.REQUEST_DELAY)

            except Exception as e:
                print(f"  ✗ {vt_symbol} 下载失败：{str(e)}")
                failed_symbols.append(symbol)

        # 打印汇总
        print(f"\n{'=' * 60}")
        print("下载完成！")
        print(f"  成功：{success_count}/{len(symbols)}")
        if failed_symbols:
            print(f"  失败：{', '.join(failed_symbols)}")
        print(f"{'=' * 60}\n")

    def _download_with_retry(self, symbol: str, start: str, end: str) -> list[BarData]:
        """
        带重试机制的下载
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                # 调用 Tushare API
                df = self._fetch_from_tushare(symbol, start, end)

                if df is not None and len(df) > 0:
                    # 转换为 BarData
                    bars = self._convert_to_bars(df, self.FUTURES_MAP[symbol])
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
        """
        从 Tushare 获取数据
        注意：使用预加载的合约列表，避免重复调用 fut_basic
        """
        try:
            # 检查预加载的合约列表是否为空
            if self.all_contracts is None or len(self.all_contracts) == 0:
                print("    ⚠ 合约列表为空，尝试重新加载...")
                self.all_contracts = self._load_all_contracts()
                if self.all_contracts is None or len(self.all_contracts) == 0:
                    print(f"    ✗ 无法加载合约列表，跳过 {symbol}")
                    return None

            # 从预加载的合约列表中筛选当前品种
            symbol_contracts = self.all_contracts[
                self.all_contracts["symbol"].str.contains(symbol)
            ]

            if len(symbol_contracts) == 0:
                print(f"    未找到 {symbol} 相关合约")
                return None

            print(f"    找到 {len(symbol_contracts)} 个合约")

            # 步骤1：选择在时间范围内的合约
            all_bars = []
            contract_count = 0

            for _, contract in symbol_contracts.iterrows():
                contract_count += 1
                ts_code = contract["ts_code"]
                print(
                    f"    [{contract_count}/{len(symbol_contracts)}] 下载 {ts_code}..."
                )

                # 下载该合约的历史数据
                try:
                    df = self.pro.fut_daily(
                        ts_code=ts_code, start_date=start, end_date=end
                    )

                    if df is not None and len(df) > 0:
                        all_bars.append(df)
                        print(f"        ✓ {len(df)} 条数据")
                    else:
                        print("        - 无数据")

                    # 防爬：每个合约之间延迟
                    if contract_count < len(symbol_contracts):
                        print(f"        等待 {self.REQUEST_DELAY} 秒...")
                        time.sleep(self.REQUEST_DELAY)

                except Exception as e:
                    print(f"        ✗ 失败：{str(e)}")
                    # 即使失败也延迟，避免触发频率限制
                    if contract_count < len(symbol_contracts):
                        time.sleep(self.REQUEST_DELAY)
                    continue

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
                print("    没有成功下载任何数据")
                return None

        except Exception as e:
            print(f"    ✗ 异常：{str(e)}")
            import traceback

            traceback.print_exc()

        return None

    def _convert_to_bars(self, df, vt_symbol: str) -> list[BarData]:
        """
        转换 pandas DataFrame 为 BarData 列表
        """
        symbol, exchange = vt_symbol.split(".")

        bars = []
        # 使用 pandas 的 iterrows() 方法
        for _, row in df.iterrows():
            # Tushare 字段映射：trade_date, open, high, low, close, vol, amount, oi
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
                    volume=float(row.get("vol", row.get("volume", 0))),
                    turnover=float(row.get("amount", 0)),
                    open_interest=float(row.get("oi", row.get("open_int", 0))),
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

    # 计算日期范围（过去5年）
    end_date = datetime(2025, 4, 13)
    start_date = datetime(2020, 4, 13)  # 5年数据

    end_str = end_date.strftime("%Y%m%d")
    start_str = start_date.strftime("%Y%m%d")

    print(f"\n{'=' * 60}")
    print("VNPY 股指期货数据下载器")
    print(f"{'=' * 60}")
    print("数据源：Tushare")
    print(f"数据路径：{LAB_PATH}")
    print(f"时间范围：{start_str} - {end_str}")
    print(f"{'=' * 60}\n")

    # 创建下载器
    try:
        downloader = TushareDataDownloader(LAB_PATH)

        # 下载数据（下载所有合约）
        downloader.download_daily_data(start_str, end_str)

        print("\n✓ 数据下载完成！")
        print("\n可以使用以下命令验证数据：")
        print("  source venv/bin/activate")
        print(
            f"  python -c \"from vnpy.alpha import AlphaLab; lab = AlphaLab('{LAB_PATH}'); print(lab.get_bar_overview())\""
        )

    except Exception as e:
        print(f"\n✗ 下载失败：{str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
