#!/usr/bin/env python3
"""
个股数据下载脚本（同时使用 Tushare 和 AKShare）
功能：
1. 双数据源下载，确保数据完整性
2. 字段对齐，便于对比验证
3. 分段下载，避免频率限制
4. 自动去重和合并
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import time
import pandas as pd

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import tushare as ts
import akshare as ak

from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
from vnpy.alpha import AlphaLab


class StockDataDownloader:
    """个股数据下载器（双数据源）"""

    # 延迟设置（秒）
    TUSHARE_DELAY = 0.5  # Tushare 免费版：每分钟200次左右
    AKSHARE_DELAY = 0.1  # AKShare：无限制

    def __init__(self, lab_path: str):
        """初始化"""
        print("=" * 60)
        print("初始化个股数据下载器")
        print("=" * 60)

        # 初始化 Tushare
        print("\n[1/3] 初始化 Tushare...")
        ts.set_token(os.environ["TUSHARE_TOKEN"])
        self.pro = ts.pro_api()
        print("  ✓ Tushare 连接成功")

        # 初始化 AKShare
        print("\n[2/3] 初始化 AKShare...")
        print(f"  ✓ AKShare 版本: {ak.__version__}")

        # 初始化 AlphaLab
        print("\n[3/3] 初始化 AlphaLab...")
        self.lab = AlphaLab(lab_path)
        print(f"  ✓ AlphaLab 路径: {lab_path}")

        # 统计信息
        self.stats = {
            "tushare": {"success": 0, "failed": 0, "total_bars": 0},
            "akshare": {"success": 0, "failed": 0, "total_bars": 0},
        }

    def download_stock_data(
        self,
        stock_codes: list[str],
        start_date: str,
        end_date: str,
        use_tushare: bool = True,
        use_akshare: bool = True,
        chunk_by_year: bool = True,
    ):
        """
        下载个股数据
        :param stock_codes: 股票代码列表（格式：000001.SZ 或 600000.SH）
        :param start_date: 开始日期 YYYY-MM-DD
        :param end_date: 结束日期 YYYY-MM-DD
        :param use_tushare: 是否使用 Tushare
        :param use_akshare: 是否使用 AKShare
        :param chunk_by_year: 是否按年份分段下载
        """
        print(f"\n{'=' * 60}")
        print("开始下载个股数据")
        print(f"{'=' * 60}")
        print(f"股票数量：{len(stock_codes)}")
        print(f"时间范围：{start_date} ~ {end_date}")
        print(
            f"数据源：Tushare={'✓' if use_tushare else '✗'}, AKShare={'✓' if use_akshare else '✗'}"
        )
        print(f"分段下载：{'按年份' if chunk_by_year else '一次性'}")
        print(f"{'=' * 60}\n")

        # 解析日期
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        # 生成分段列表
        if chunk_by_year:
            chunks = self._generate_yearly_chunks(start_dt, end_dt)
            print(f"分段策略：按年份分段，共 {len(chunks)} 段")
            for i, (chunk_start, chunk_end) in enumerate(chunks):
                print(f"  段 {i + 1}: {chunk_start.date()} ~ {chunk_end.date()}")
        else:
            chunks = [(start_dt, end_dt)]
            print("分段策略：一次性下载")

        # 下载每个股票的数据
        for i, stock_code in enumerate(stock_codes, 1):
            print(f"\n[{i}/{len(stock_codes)}] 处理股票：{stock_code}")
            print("-" * 60)

            # Tushare 数据
            if use_tushare:
                print("\n[Tushare] 开始下载...")
                try:
                    tushare_bars = self._download_from_tushare(stock_code, chunks)
                    if tushare_bars:
                        self._save_and_validate(stock_code, tushare_bars, "TUSHARE")
                except Exception as e:
                    print(f"  ✗ Tushare 下载失败：{str(e)}")
                    self.stats["tushare"]["failed"] += 1

            # AKShare 数据
            if use_akshare:
                print("\n[AKShare] 开始下载...")
                try:
                    akshare_bars = self._download_from_akshare(stock_code, chunks)
                    if akshare_bars:
                        self._save_and_validate(stock_code, akshare_bars, "AKSHARE")
                except Exception as e:
                    print(f"  ✗ AKShare 下载失败：{str(e)}")
                    self.stats["akshare"]["failed"] += 1

        # 打印统计
        self._print_summary()

    def _generate_yearly_chunks(self, start: datetime, end: datetime) -> list[tuple]:
        """生成分段列表（按年份）"""
        chunks = []
        current = start

        while current <= end:
            # 计算当前年份结束
            year_end = datetime(current.year, 12, 31)
            chunk_end = min(year_end, end)

            chunks.append((current, chunk_end))
            current = chunk_end + timedelta(days=1)

        return chunks

    def _download_from_tushare(
        self, stock_code: str, chunks: list[tuple]
    ) -> list[BarData]:
        """使用 Tushare 下载数据"""
        all_bars = []

        for i, (chunk_start, chunk_end) in enumerate(chunks):
            start_str = chunk_start.strftime("%Y%m%d")
            end_str = chunk_end.strftime("%Y%m%d")

            print(f"  段 {i + 1}/{len(chunks)}: {start_str} ~ {end_str}", end=" ")

            try:
                # 转换股票代码格式（000001.SZ -> 000001.SZ）
                ts_code = stock_code.replace(".", "")

                # 下载日线数据（前复权）
                df = self.pro.daily(
                    ts_code=ts_code,
                    start_date=start_str,
                    end_date=end_str,
                )

                if df is not None and len(df) > 0:
                    # 转换为 BarData
                    bars = self._convert_tushare_to_bars(df, stock_code)
                    all_bars.extend(bars)
                    print(f"✓ {len(df)} 条")
                else:
                    print("- 无数据")

                # 延迟
                time.sleep(self.TUSHARE_DELAY)

            except Exception as e:
                print(f"✗ {str(e)}")
                continue

        # 去重（按日期）
        all_bars = self._deduplicate_bars(all_bars)

        return all_bars

    def _download_from_akshare(
        self, stock_code: str, chunks: list[tuple]
    ) -> list[BarData]:
        """使用 AKShare 下载数据"""
        all_bars = []

        # 获取股票代码（去掉交易所后缀）
        code = stock_code.split(".")[0]

        for i, (chunk_start, chunk_end) in enumerate(chunks):
            start_str = chunk_start.strftime("%Y%m%d")
            end_str = chunk_end.strftime("%Y%m%d")

            print(f"  段 {i + 1}/{len(chunks)}: {start_str} ~ {end_str}", end=" ")

            try:
                # AKShare 下载数据
                df = ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start_str,
                    end_date=end_str,
                    adjust="qfq",  # 前复权
                )

                if df is not None and len(df) > 0:
                    # 转换为 BarData
                    bars = self._convert_akshare_to_bars(df, stock_code)
                    all_bars.extend(bars)
                    print(f"✓ {len(df)} 条")
                else:
                    print("- 无数据")

                # 延迟
                time.sleep(self.AKSHARE_DELAY)

            except Exception as e:
                print(f"✗ {str(e)}")
                continue

        # 去重（按日期）
        all_bars = self._deduplicate_bars(all_bars)

        return all_bars

    def _convert_tushare_to_bars(
        self, df: pd.DataFrame, stock_code: str
    ) -> list[BarData]:
        """转换 Tushare 数据为 BarData"""
        # 确定交易所
        exchange = Exchange.SSE if stock_code.endswith(".SH") else Exchange.SZSE
        symbol = stock_code.split(".")[0]

        bars = []
        for _, row in df.iterrows():
            try:
                bar = BarData(
                    symbol=symbol,
                    exchange=exchange,
                    datetime=datetime.strptime(str(row["trade_date"]), "%Y%m%d"),
                    interval=Interval.DAILY,
                    open_price=float(row["open"]),
                    high_price=float(row["high"]),
                    low_price=float(row["low"]),
                    close_price=float(row["close"]),
                    volume=float(row["vol"]),
                    turnover=float(row.get("amount", 0)),  # 成交额（千元）
                    open_interest=0.0,  # 股票没有持仓量
                    gateway_name="TUSHARE",
                )
                bars.append(bar)
            except Exception:
                continue

        return bars

    def _convert_akshare_to_bars(
        self, df: pd.DataFrame, stock_code: str
    ) -> list[BarData]:
        """转换 AKShare 数据为 BarData"""
        # 确定交易所
        exchange = Exchange.SSE if stock_code.endswith(".SH") else Exchange.SZSE
        symbol = stock_code.split(".")[0]

        bars = []
        for _, row in df.iterrows():
            try:
                bar = BarData(
                    symbol=symbol,
                    exchange=exchange,
                    datetime=pd.to_datetime(row["日期"]),
                    interval=Interval.DAILY,
                    open_price=float(row["开盘"]),
                    high_price=float(row["最高"]),
                    low_price=float(row["最低"]),
                    close_price=float(row["收盘"]),
                    volume=float(row["成交量"]),
                    turnover=float(row["成交额"]),  # 成交额（元）
                    open_interest=0.0,  # 股票没有持仓量
                    gateway_name="AKSHARE",
                )
                bars.append(bar)
            except Exception:
                continue

        return bars

    def _deduplicate_bars(self, bars: list[BarData]) -> list[BarData]:
        """去重（按日期）"""
        if not bars:
            return []

        # 使用字典去重（保留最后一条）
        bar_dict = {}
        for bar in bars:
            key = (bar.symbol, bar.exchange, bar.datetime)
            bar_dict[key] = bar

        # 按日期排序
        sorted_bars = sorted(bar_dict.values(), key=lambda x: x.datetime)
        return sorted_bars

    def _save_and_validate(self, stock_code: str, bars: list[BarData], source: str):
        """保存数据并验证"""
        if not bars:
            print(f"  ✗ {source} 无数据保存")
            return

        # 保存到 AlphaLab
        self.lab.save_bar_data(bars)

        # 验证数据
        print(f"  ✓ {source} 保存成功：{len(bars)} 条")
        print(f"    时间范围：{bars[0].datetime.date()} ~ {bars[-1].datetime.date()}")

        # 数据质量检查
        self._check_data_quality(bars, source)

        # 更新统计
        self.stats[source.lower()]["success"] += 1
        self.stats[source.lower()]["total_bars"] += len(bars)

    def _check_data_quality(self, bars: list[BarData], source: str):
        """检查数据质量"""
        issues = []

        # 检查缺失值
        for bar in bars:
            if (
                bar.open_price == 0
                or bar.high_price == 0
                or bar.low_price == 0
                or bar.close_price == 0
            ):
                issues.append(f"{bar.datetime.date()} 价格为0")
            if bar.volume < 0:
                issues.append(f"{bar.datetime.date()} 成交量为负")

        if issues:
            print(f"    ⚠ 发现 {len(issues)} 个数据问题")
            if len(issues) <= 3:
                for issue in issues:
                    print(f"      - {issue}")
        else:
            print("    ✓ 数据质量检查通过")

    def _print_summary(self):
        """打印统计汇总"""
        print(f"\n{'=' * 60}")
        print("下载完成！统计汇总")
        print(f"{'=' * 60}")

        print("\n[Tushare]")
        print(f"  成功：{self.stats['tushare']['success']}")
        print(f"  失败：{self.stats['tushare']['failed']}")
        print(f"  总条数：{self.stats['tushare']['total_bars']}")

        print("\n[AKShare]")
        print(f"  成功：{self.stats['akshare']['success']}")
        print(f"  失败：{self.stats['akshare']['failed']}")
        print(f"  总条数：{self.stats['akshare']['total_bars']}")

        print(f"\n{'=' * 60}")


def main():
    """主函数"""
    LAB_PATH = "/Users/w4sh8899/project/vnpy/lab_data"

    # 配置参数
    # 示例：沪深300成分股（前10只）
    stock_codes = [
        "000001.SZ",  # 平安银行
        "000002.SZ",  # 万科A
        "000063.SZ",  # 中兴通讯
        "000333.SZ",  # 美的集团
        "000338.SZ",  # 潍柴动力
        "600000.SH",  # 浦发银行
        "600036.SH",  # 招商银行
        "600519.SH",  # 贵州茅台
        "600887.SH",  # 伊利股份
        "601318.SH",  # 中国平安
    ]

    # 时间范围（过去5年）
    end_date = datetime(2025, 4, 13)
    start_date = datetime(2020, 4, 13)

    end_str = end_date.strftime("%Y-%m-%d")
    start_str = start_date.strftime("%Y-%m-%d")

    print("\n个股数据下载配置：")
    print(f"  股票数量：{len(stock_codes)}")
    print(f"  时间范围：{start_str} ~ {end_str}")
    print("  分段策略：按年份（避免频率限制）")
    print("  数据源：Tushare + AKShare（双源验证）")

    # 创建下载器
    downloader = StockDataDownloader(LAB_PATH)

    # 下载数据
    downloader.download_stock_data(
        stock_codes=stock_codes,
        start_date=start_str,
        end_date=end_str,
        use_tushare=True,
        use_akshare=True,
        chunk_by_year=True,  # 按年份分段
    )

    print("\n✓ 所有下载任务完成！")
    print("\n可以使用以下命令验证数据：")
    print("  source venv/bin/activate")
    print(
        f"  python -c \"from vnpy.alpha import AlphaLab; lab = AlphaLab('{LAB_PATH}'); print('数据已保存')\""
    )


if __name__ == "__main__":
    main()
