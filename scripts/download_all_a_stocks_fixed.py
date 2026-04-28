#!/usr/bin/env python3
"""
A股全市场数据下载脚本（修复版）
- 直接使用已有的股票列表
- 实时输出（无缓冲）
- 简化逻辑，确保稳定运行
"""

import sys
from pathlib import Path
from datetime import datetime
import time

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import akshare as ak
import pandas as pd

from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
from vnpy.alpha import AlphaLab


class FixedAStockDownloader:
    """修复版A股下载器"""

    # 下载参数
    BATCH_SIZE = 50  # 每批下载股票数量
    REQUEST_DELAY = 0.5  # 请求延迟（秒）
    MAX_RETRIES = 3  # 最大重试次数

    # 数据路径
    STOCK_LIST_FILE = "stock_list_all.csv"
    PROGRESS_FILE = "download_progress.json"

    def __init__(self, lab_path: str):
        """初始化"""
        # 强制无缓冲输出
        sys.stdout.reconfigure(line_buffering=True)

        print("=" * 60, flush=True)
        print("A股全市场数据下载器（修复版）", flush=True)
        print("=" * 60, flush=True)

        print("\n[1/3] 初始化 AlphaLab...", flush=True)
        self.lab = AlphaLab(lab_path)
        print(f"  ✓ 路径: {lab_path}", flush=True)

        print("\n[2/3] 加载股票列表...", flush=True)
        self.all_stocks = self._load_stock_list()
        print(f"  ✓ 总股票数: {len(self.all_stocks)}", flush=True)

        print("\n[3/3] 加载下载进度...", flush=True)
        self.downloaded_stocks = self._load_progress()
        print(f"  ✓ 已下载: {len(self.downloaded_stocks)}", flush=True)

        print("\n" + "=" * 60, flush=True)
        print("准备完成，开始下载...", flush=True)
        print("=" * 60, flush=True)

        # 统计信息
        self.stats = {
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "total_bars": 0,
        }

    def _load_stock_list(self) -> pd.DataFrame:
        """从CSV文件加载股票列表"""
        try:
            df = pd.read_csv(self.STOCK_LIST_FILE)
            print(f"    从 {self.STOCK_LIST_FILE} 加载成功", flush=True)
            return df
        except Exception as e:
            print(f"    ✗ 加载失败: {e}", flush=True)
            return pd.DataFrame()

    def _load_progress(self) -> set:
        """加载下载进度"""
        downloaded = set()

        # 从JSON文件加载
        if Path(self.PROGRESS_FILE).exists():
            try:
                import json

                with open(self.PROGRESS_FILE) as f:
                    data = json.load(f)
                    downloaded = set(data.get("downloaded", []))
            except Exception:
                pass

        # 从已下载文件中读取
        try:
            daily_path = Path(self.lab_path) / "daily"
            if daily_path.exists():
                for file in daily_path.glob("*.parquet"):
                    code = file.stem.split(".")[0]
                    downloaded.add(code)
        except Exception:
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
        """下载所有A股数据"""
        print(f"\n时间范围: {start_date} ~ {end_date}", flush=True)
        print(f"总股票数: {len(self.all_stocks)}", flush=True)
        print(f"已下载: {len(self.downloaded_stocks)}", flush=True)
        print(
            f"待下载: {len(self.all_stocks) - len(self.downloaded_stocks)}", flush=True
        )

        # 过滤已下载的股票
        pending_stocks = self.all_stocks[
            ~self.all_stocks["code"].isin(self.downloaded_stocks)
        ]

        if limit:
            pending_stocks = pending_stocks.head(limit)
            print(f"下载限制: {limit} 只（测试模式）", flush=True)

        total = len(pending_stocks)
        batches = (total + self.BATCH_SIZE - 1) // self.BATCH_SIZE

        print(f"分批下载: {batches} 批，每批 {self.BATCH_SIZE} 只\n", flush=True)

        # 分批下载
        for batch_idx in range(batches):
            start_idx = batch_idx * self.BATCH_SIZE
            end_idx = min((batch_idx + 1) * self.BATCH_SIZE, total)

            batch = pending_stocks.iloc[start_idx:end_idx]

            print(f"\n[批次 {batch_idx + 1}/{batches}] ", flush=True, end="")
            print(f"下载股票 {start_idx + 1}-{end_idx}...", flush=True)

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
                            f"  [{start_idx + idx - batch.index[0] + 1:3d}/{total}] ",
                            flush=True,
                            end="",
                        )
                        print(f"{code}.{exchange}: ✓ {len(bars)} 条", flush=True)
                    else:
                        self.stats["failed"] += 1
                        print(
                            f"  [{start_idx + idx - batch.index[0] + 1:3d}/{total}] ",
                            flush=True,
                            end="",
                        )
                        print(f"{code}.{exchange}: ✗ 无数据", flush=True)

                except Exception as e:
                    self.stats["failed"] += 1
                    print(
                        f"  [{start_idx + idx - batch.index[0] + 1:3d}/{total}] ",
                        flush=True,
                        end="",
                    )
                    print(f"{code}.{exchange}: ✗ {str(e)[:30]}", flush=True)

                # 延迟
                time.sleep(self.REQUEST_DELAY)

            # 每批保存进度
            print("\n  批次完成，保存进度...", flush=True)
            self._save_progress()
            print(
                f"  已完成: {len(self.downloaded_stocks)}/{len(self.all_stocks)}",
                flush=True,
            )

        # 最终统计
        self._print_summary()

    def _download_single_stock(
        self,
        code: str,
        exchange: str,
        start: str,
        end: str,
    ) -> list[BarData]:
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
    ) -> list[BarData]:
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
            except Exception:
                continue

        return bars

    def _print_summary(self):
        """打印统计汇总"""
        print(f"\n{'=' * 60}", flush=True)
        print("下载完成！统计汇总", flush=True)
        print(f"{'=' * 60}", flush=True)

        print(f"\n下载成功: {self.stats['success']}", flush=True)
        print(f"下载失败: {self.stats['failed']}", flush=True)
        print(f"跳过已下载: {self.stats['skipped']}", flush=True)
        print(f"总数据条: {self.stats['total_bars']}", flush=True)
        print(
            f"完成率: {len(self.downloaded_stocks)}/{len(self.all_stocks)} "
            f"({len(self.downloaded_stocks) / len(self.all_stocks) * 100:.1f}%)",
            flush=True,
        )

        print(f"\n{'=' * 60}", flush=True)


def main():
    """主函数"""
    LAB_PATH = "/Users/w4sh8899/project/vnpy/lab_data"

    # 时间范围
    end_date = datetime(2025, 4, 13)
    start_date = datetime(2020, 4, 13)

    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")

    # 创建下载器
    downloader = FixedAStockDownloader(LAB_PATH)

    # 全量下载
    print("\n开始全量下载 A股数据...", flush=True)
    print("提示：支持断点续传，可随时中断\n", flush=True)

    downloader.download_all_stocks(
        start_date=start_str,
        end_date=end_str,
    )

    print("\n✓ 下载任务完成！", flush=True)


if __name__ == "__main__":
    main()
