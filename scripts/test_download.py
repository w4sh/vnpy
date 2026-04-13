#!/usr/bin/env python3
"""
快速测试：下载1个月的 IF 数据
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.download_data import TushareDataDownloader


def main():
    LAB_PATH = "/Users/w4sh8899/project/vnpy/lab_data"

    # 只下载最近1个月
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    end_str = end_date.strftime("%Y%m%d")
    start_str = start_date.strftime("%Y%m%d")

    print("\n快速测试：下载 IF 最近1个月数据")
    print(f"时间范围：{start_str} - {end_str}\n")

    try:
        downloader = TushareDataDownloader(LAB_PATH)

        # 只下载 IF
        downloader.download_daily_data(start_str, end_str, symbols=["IF"])

        print("\n✓ 测试完成！")

    except Exception as e:
        print(f"\n✗ 测试失败：{str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
