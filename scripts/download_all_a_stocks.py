#!/usr/bin/env python3
"""
A股全市场数据下载脚本
策略：
1. 使用 AKShare 获取股票列表（免费、无频率限制）
2. 分批下载（每批 100 只，避免内存溢出）
3. 自动去重和验证
4. 支持断点续传
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Set
import time
import polars as pl

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import akshare as ak
import pandas as pd

from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
from vnpy.alpha import AlphaLab


class AllAStockDownloader:
    """A股全市场数据下载器"""

    # 下载参数
    BATCH_SIZE = 50  # 每批下载股票数量
    REQUEST_DELAY = 0.5  # 请求延迟（秒）
    MAX_RETRIES = 3  # 最大重试次数

    # 数据路径
    STOCK_LIST_FILE = "stock_list_all.csv"
    PROGRESS_FILE = "download_progress.json"

    def __init__(self, lab_path: str):
        """初始化"""
        print("=" * 60)
        print("A股全市场数据下载器")
        print("=" * 60)

        print("\n[1/4] 初始化 AlphaLab...")
        self.lab = AlphaLab(lab_path)
        print(f"  ✓ 路径: {lab_path}")

        print("\n[2/4] 准备股票列表...")
        self.all_stocks = self._get_stock_list()
        print(f"  ✓ 总股票数: {len(self.all_stocks)}")

        print("\n[3/4] 加载下载进度...")
        self.downloaded_stocks = self._load_progress()
        print(f"  ✓ 已下载: {len(self.downloaded_stocks)}")

        print("\n[4/4] 准备数据目录...")
        self.lab_path = lab_path
        print("  ✓ 准备完成")

        # 统计信息
        self.stats = {
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "total_bars": 0,
        }

    def _get_stock_list(self) -> pd.DataFrame:
        """获取所有A股列表"""
        print("\n    获取股票列表（使用 AKShare）...")

        try:
            # 获取A股股票列表
            stock_info = ak.stock_info_a_code_name()

            if stock_info is not None and len(stock_info) > 0:
                # 重命名列
                stock_info.columns = ["code", "name"]

                # 添加交易所信息
                def get_exchange(code):
                    if code.startswith("6"):
                        return "SSE"
                    elif code.startswith("0") or code.startswith("3"):
                        return "SZSE"
                    else:
                        return "UNKNOWN"

                stock_info["exchange"] = stock_info["code"].apply(get_exchange)

                # 保存完整列表
                stock_info.to_csv(
                    self.STOCK_LIST_FILE, index=False, encoding="utf-8-sig"
                )
                print(f"    ✓ 获取到 {len(stock_info)} 只股票")

                return stock_info
            else:
                print("    ✗ AKShare 返回空数据")
                return pd.DataFrame()

        except Exception as e:
            print(f"    ✗ 获取失败: {str(e)}")
            print("    使用预定义代码范围...")

            # 备用方案：使用预定义范围
            return self._get_prestock_list()

    def _get_prestock_list(self) -> pd.DataFrame:
        """备用方案：预定义股票代码范围"""
        stocks = []

        # 上交所：600000-605000, 688000-688999
        for i in range(600000, 605001):
            stocks.append({"code": f"{i}", "name": "", "exchange": "SSE"})
        for i in range(688000, 689000):
            stocks.append({"code": f"{i}", "name": "", "exchange": "SSE"})

        # 深交所：000001-003000, 300001-301000
        for i in range(1, 30001):
            code = f"{i:06d}"
            if code.startswith("00") or code.startswith("30"):
                exchange = "SZSE"
                stocks.append({"code": code, "name": "", "exchange": exchange})

        return pd.DataFrame(stocks)

    def _load_progress(self) -> Set[str]:
        """加载下载进度"""
        downloaded = set()

        if Path(self.PROGRESS_FILE).exists():
            try:
                import json

                with open(self.PROGRESS_FILE, "r") as f:
                    data = json.load(f)
                    downloaded = set(data.get("downloaded", []))
            except:
                pass

        # 从已下载的文件中读取
        try:
            import os

            daily_path = Path(self.lab_path) / "daily"
            if daily_path.exists():
                for file in daily_path.glob("*.parquet"):
                    # 提取股票代码
                    code = file.stem.split(".")[0]
                    downloaded.add(code)
        except:
            pass

        return downloaded

    def _save_progress(self):
        """保存下载进度"""
        import json

        with open(self.PROGRESS_FILE, "w") as f:
            json.dump(
                {
                    "downloaded": list(self.downloaded_stocks),
                    "timestamp": datetime.now().isoformat(),
                },
                f,
            )

    def download_all_stocks(
        self,
        start_date: str,
        end_date: str,
        limit: int = None,
    ):
        """
        下载所有A股数据
        :param start_date: 开始日期 YYYYMMDD
        :param end_date: 结束日期 YYYYMMDD
        :param limit: 限制下载数量（用于测试）
        """
        print(f"\n{'=' * 60}")
        print("开始下载A股全市场数据")
        print(f"{'=' * 60}")
        print(f"时间范围: {start_date} ~ {end_date}")
        print(f"总股票数: {len(self.all_stocks)}")
        if limit:
            print(f"下载限制: {limit} 只（测试模式）")
        print(f"已下载: {len(self.downloaded_stocks)}")
        print(f"待下载: {len(self.all_stocks) - len(self.downloaded_stocks)}")
        print(f"{'=' * 60}\n")

        # 过滤已下载的股票
        pending_stocks = self.all_stocks[
            ~self.all_stocks["code"].isin(self.downloaded_stocks)
        ]

        if limit:
            pending_stocks = pending_stocks.head(limit)

        total = len(pending_stocks)
        batches = (total + self.BATCH_SIZE - 1) // self.BATCH_SIZE

        print(f"分批下载: {batches} 批，每批 {self.BATCH_SIZE} 只\n")

        # 分批下载
        for batch_idx in range(batches):
            start_idx = batch_idx * self.BATCH_SIZE
            end_idx = min((batch_idx + 1) * self.BATCH_SIZE, total)

            batch = pending_stocks.iloc[start_idx:end_idx]

            print(
                f"\n[批次 {batch_idx + 1}/{batches}] 下载股票 {start_idx + 1}-{end_idx}..."
            )

            for idx, row in batch.iterrows():
                code = row["code"]
                exchange = row["exchange"]

                # 跳过已下载
                if code in self.downloaded_stocks:
                    continue

                # 下载数据
                try:
                    bars = self._download_single_stock(
                        code, exchange, start_date, end_date
                    )

                    if bars and len(bars) > 0:
                        # 保存
                        self.lab.save_bar_data(bars)
                        self.downloaded_stocks.add(code)
                        self.stats["success"] += 1
                        self.stats["total_bars"] += len(bars)
                        print(
                            f"  [{idx + 1:3d}/{total}] {code}.{exchange}: ✓ {len(bars)} 条"
                        )
                    else:
                        self.stats["failed"] += 1
                        print(f"  [{idx + 1:3d}/{total}] {code}.{exchange}: ✗ 无数据")

                except Exception as e:
                    self.stats["failed"] += 1
                    print(
                        f"  [{idx + 1:3d}/{total}] {code}.{exchange}: ✗ {str(e)[:30]}"
                    )

                # 延迟
                time.sleep(self.REQUEST_DELAY)

            # 每批保存进度
            print(f"\n  批次完成，保存进度...")
            self._save_progress()
            print(f"  已完成: {len(self.downloaded_stocks)}/{len(self.all_stocks)}")

        # 最终统计
        self._print_summary()

    def _download_single_stock(
        self,
        code: str,
        exchange: str,
        start: str,
        end: str,
    ) -> List[BarData]:
        """下载单只股票数据"""
        for attempt in range(self.MAX_RETRIES):
            try:
                # AKShare 下载
                df = ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start,
                    end_date=end,
                    adjust="qfq",  # 前复权
                )

                if df is not None and len(df) > 0:
                    # 转换为 BarData
                    bars = self._convert_to_bars(df, code, exchange)
                    return bars
                else:
                    return []

            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(1)
                else:
                    raise e

        return []

    def _convert_to_bars(
        self, df: pd.DataFrame, code: str, exchange: str
    ) -> List[BarData]:
        """转换数据为 BarData"""
        exchange_obj = Exchange.SSE if exchange == "SSE" else Exchange.SZSE

        bars = []
        for _, row in df.iterrows():
            try:
                bar = BarData(
                    symbol=code,
                    exchange=exchange_obj,
                    datetime=pd.to_datetime(row["日期"]),
                    interval=Interval.DAILY,
                    open_price=float(row["开盘"]),
                    high_price=float(row["最高"]),
                    low_price=float(row["最低"]),
                    close_price=float(row["收盘"]),
                    volume=float(row["成交量"]),
                    turnover=float(row["成交额"]),
                    open_interest=0.0,
                    gateway_name="AKSHARE",
                )
                bars.append(bar)
            except:
                continue

        return bars

    def _print_summary(self):
        """打印统计汇总"""
        print(f"\n{'=' * 60}")
        print("下载完成！统计汇总")
        print(f"{'=' * 60}")

        print(f"\n下载成功: {self.stats['success']}")
        print(f"下载失败: {self.stats['failed']}")
        print(f"跳过已下载: {self.stats['skipped']}")
        print(f"总数据条: {self.stats['total_bars']}")
        print(
            f"完成率: {len(self.downloaded_stocks)}/{len(self.all_stocks)} ({len(self.downloaded_stocks) / len(self.all_stocks) * 100:.1f}%)"
        )

        print(f"\n{'=' * 60}")


def main():
    """主函数"""
    LAB_PATH = "/Users/w4sh8899/project/vnpy/lab_data"

    # 时间范围
    end_date = datetime(2025, 4, 13)
    start_date = datetime(2020, 4, 13)

    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")

    print("A股全市场数据下载")
    print("=" * 60)
    print(f"时间范围: {start_str} ~ {end_str} (5年)")
    print(f"数据源: AKShare (免费、无限制)")
    print(f"分批下载: 每批 50 只")
    print(f"断点续传: 支持")
    print("=" * 60)

    # 创建下载器
    downloader = AllAStockDownloader(LAB_PATH)

    # 全量下载（自动化模式）
    print("\n开始全量下载 A股数据...")
    print("提示：支持断点续传，可随时中断")
    downloader.download_all_stocks(
        start_date=start_str,
        end_date=end_str,
    )

    print("\n✓ 下载任务完成！")
    print("\n提示: 可以随时中断，下次运行会自动断点续传")


if __name__ == "__main__":
    main()
