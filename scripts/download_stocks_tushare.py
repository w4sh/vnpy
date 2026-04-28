#!/usr/bin/env python3
"""
A股数据下载脚本（Tushare优化版）
- 使用Tushare API（稳定可靠）
- 智能速率限制（充分利用每分钟50次限制）
- 批量下载优化
"""

import sys
from pathlib import Path
from datetime import datetime
import time

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import tushare as ts
import pandas as pd

from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
from vnpy.alpha import AlphaLab


class TushareStockDownloader:
    """Tushare股票下载器"""

    # Tushare配置
    TUSHARE_TOKEN = "8338d9ae4c26c3ec32cffbd1b337d97228c22ba84cea0996410513bb"
    API_RATE_LIMIT = 50  # 每分钟50次
    SAFE_DELAY = 1.2  # 安全延迟（60/50 = 1.2秒）

    # 下载参数
    BATCH_SIZE = 10  # 每批处理数量（降低以避免超时）
    MAX_RETRIES = 3

    # 数据路径
    STOCK_LIST_FILE = "stock_list_all.csv"
    PROGRESS_FILE = "download_progress_tushare.json"

    def __init__(self, lab_path: str):
        """初始化"""
        # 强制无缓冲输出
        sys.stdout.reconfigure(line_buffering=True)

        print("=" * 60, flush=True)
        print("A股数据下载器（Tushare优化版）", flush=True)
        print("=" * 60, flush=True)

        print("\n[1/4] 初始化Tushare...", flush=True)
        ts.set_token(self.TUSHARE_TOKEN)
        self.pro = ts.pro_api()
        print("  ✓ Tushare API已连接", flush=True)

        print("\n[2/4] 初始化AlphaLab...", flush=True)
        self.lab = AlphaLab(lab_path)
        print(f"  ✓ 路径: {lab_path}", flush=True)

        print("\n[3/4] 加载股票列表...", flush=True)
        self.all_stocks = self._load_stock_list()
        print(f"  ✓ 总股票数: {len(self.all_stocks)}", flush=True)

        print("\n[4/4] 加载下载进度...", flush=True)
        self.downloaded_stocks = self._load_progress()
        print(f"  ✓ 已下载: {len(self.downloaded_stocks)}", flush=True)

        print("\n" + "=" * 60, flush=True)

        # 速率控制
        self.last_request_time = None

        # 统计信息
        self.stats = {
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "total_bars": 0,
        }

    def _load_stock_list(self) -> pd.DataFrame:
        """从CSV加载股票列表"""
        try:
            # 确保code列作为字符串读取，保留前导零
            df = pd.read_csv(self.STOCK_LIST_FILE, dtype={"code": str})

            # 转换为Tushare格式（TS代码）
            def convert_to_ts_code(row):
                code = row["code"]
                exchange = row["exchange"]
                if exchange == "SSE":
                    return f"{code}.SH"
                elif exchange == "SZSE":
                    return f"{code}.SZ"
                else:
                    return None

            df["ts_code"] = df.apply(convert_to_ts_code, axis=1)
            df = df[df["ts_code"].notna()]  # 过滤无效代码

            print(f"    从 {self.STOCK_LIST_FILE} 加载成功", flush=True)
            return df
        except Exception as e:
            print(f"    ✗ 加载失败: {e}", flush=True)
            return pd.DataFrame()

    def _load_progress(self) -> set[str]:
        """加载下载进度"""
        downloaded = set()

        if Path(self.PROGRESS_FILE).exists():
            try:
                import json

                with open(self.PROGRESS_FILE) as f:
                    data = json.load(f)
                    downloaded = set(data.get("downloaded", []))
            except Exception:
                pass

        # 从已下载文件读取
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
        """保存进度"""
        import json

        with open(self.PROGRESS_FILE, "w") as f:
            json.dump(
                {
                    "downloaded": list(self.downloaded_stocks),
                    "timestamp": datetime.now().isoformat(),
                },
                f,
            )

    def _rate_limit_delay(self):
        """速率限制延迟"""
        if self.last_request_time:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.SAFE_DELAY:
                wait_time = self.SAFE_DELAY - elapsed
                time.sleep(wait_time)
        self.last_request_time = time.time()

    def download_all_stocks(
        self,
        start_date: str,
        end_date: str,
        limit: int = None,
    ):
        """下载所有股票"""
        print("\n开始下载A股数据", flush=True)
        print(f"时间范围: {start_date} ~ {end_date}", flush=True)
        print(f"总股票数: {len(self.all_stocks)}", flush=True)
        print(f"已下载: {len(self.downloaded_stocks)}", flush=True)
        print(
            f"待下载: {len(self.all_stocks) - len(self.downloaded_stocks)}", flush=True
        )
        print(f"速率限制: {self.API_RATE_LIMIT} 次/分钟", flush=True)
        print(f"请求延迟: {self.SAFE_DELAY} 秒", flush=True)

        if limit:
            print(f"下载限制: {limit} 只（测试模式）", flush=True)

        # 过滤已下载
        pending_stocks = self.all_stocks[
            ~self.all_stocks["ts_code"].isin(self.downloaded_stocks)
        ]

        if limit:
            pending_stocks = pending_stocks.head(limit)

        total = len(pending_stocks)
        batches = (total + self.BATCH_SIZE - 1) // self.BATCH_SIZE

        print(f"分批下载: {batches} 批，每批 {self.BATCH_SIZE} 只", flush=True)

        # 估算时间
        estimated_time = total * self.SAFE_DELAY / 60
        print(f"预计时间: {estimated_time:.0f} 分钟\n", flush=True)

        # 分批下载
        for batch_idx in range(batches):
            start_idx = batch_idx * self.BATCH_SIZE
            end_idx = min((batch_idx + 1) * self.BATCH_SIZE, total)

            batch = pending_stocks.iloc[start_idx:end_idx]

            print(f"\n[批次 {batch_idx + 1}/{batches}] ", flush=True, end="")
            print(f"股票 {start_idx + 1}-{end_idx}", flush=True)

            batch_success = 0
            batch_failed = 0

            for idx, row in batch.iterrows():
                ts_code = row["ts_code"]
                original_code = row["code"]

                # 跳过已下载
                if original_code in self.downloaded_stocks:
                    continue

                # 下载数据
                try:
                    bars = self._download_single_stock(
                        ts_code, original_code, start_date, end_date
                    )

                    if bars and len(bars) > 0:
                        self.lab.save_bar_data(bars)
                        self.downloaded_stocks.add(original_code)
                        self.stats["success"] += 1
                        self.stats["total_bars"] += len(bars)
                        batch_success += 1

                        print(
                            f"  [{start_idx + idx - batch.index[0] + 1:3d}/{total}] ",
                            flush=True,
                            end="",
                        )
                        print(f"{ts_code}: ✓ {len(bars)} 条", flush=True)
                    else:
                        batch_failed += 1
                        self.stats["failed"] += 1
                        print(
                            f"  [{start_idx + idx - batch.index[0] + 1:3d}/{total}] ",
                            flush=True,
                            end="",
                        )
                        print(f"{ts_code}: ✗ 无数据", flush=True)

                except Exception as e:
                    batch_failed += 1
                    self.stats["failed"] += 1
                    print(
                        f"  [{start_idx + idx - batch.index[0] + 1:3d}/{total}] ",
                        flush=True,
                        end="",
                    )
                    print(f"{ts_code}: ✗ {str(e)[:20]}", flush=True)

            # 每批保存进度
            print(
                f"\n  批次完成: 成功 {batch_success}, 失败 {batch_failed}", flush=True
            )
            self._save_progress()
            print(
                f"  总进度: {len(self.downloaded_stocks)}/{len(self.all_stocks)} "
                f"({len(self.downloaded_stocks) / len(self.all_stocks) * 100:.1f}%)",
                flush=True,
            )

        self._print_summary()

    def _download_single_stock(
        self,
        ts_code: str,
        original_code: str,
        start_date: str,
        end_date: str,
    ) -> list[BarData]:
        """下载单只股票"""
        self._rate_limit_delay()

        for attempt in range(self.MAX_RETRIES):
            try:
                # Tushare下载
                df = self.pro.daily(
                    ts_code=ts_code, start_date=start_date, end_date=end_date
                )

                if df is not None and len(df) > 0:
                    # 转换为BarData
                    bars = self._convert_to_bars(df, original_code, ts_code)
                    return bars
                else:
                    return []

            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(2)
                else:
                    raise e

        return []

    def _convert_to_bars(
        self, df: pd.DataFrame, code: str, ts_code: str
    ) -> list[BarData]:
        """转换为BarData"""
        # 确定交易所
        if ts_code.endswith(".SH"):
            exchange = Exchange.SSE
        else:
            exchange = Exchange.SZSE

        bars = []
        for _, row in df.iterrows():
            try:
                bar = BarData(
                    symbol=code,
                    exchange=exchange,
                    datetime=pd.to_datetime(row["trade_date"]),
                    interval=Interval.DAILY,
                    open_price=float(row["open"]),
                    high_price=float(row["high"]),
                    low_price=float(row["low"]),
                    close_price=float(row["close"]),
                    volume=float(row["vol"]),
                    turnover=float(row.get("amount", 0)),
                    open_interest=0.0,
                    gateway_name="TUSHARE",
                )
                bars.append(bar)
            except Exception:
                continue

        return bars

    def _print_summary(self):
        """打印统计"""
        print(f"\n{'=' * 60}", flush=True)
        print("下载完成！统计汇总", flush=True)
        print(f"{'=' * 60}", flush=True)

        print(f"\n下载成功: {self.stats['success']}", flush=True)
        print(f"下载失败: {self.stats['failed']}", flush=True)
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

    downloader = TushareStockDownloader(LAB_PATH)

    print("\n开始全量下载（使用Tushare）...", flush=True)
    print("提示：下载速度较慢但稳定可靠", flush=True)
    print("预计时间：约110-120分钟\n", flush=True)

    downloader.download_all_stocks(
        start_date=start_str,
        end_date=end_str,
    )

    print("\n✓ 下载完成！", flush=True)


if __name__ == "__main__":
    main()
