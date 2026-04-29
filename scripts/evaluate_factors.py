#!/usr/bin/env python3
"""
前瞻因子效果测试 — 执行脚本

使用方法:
    # 1. 先回填日频因子历史数据（约 6 分钟）
    python scripts/backfill_daily_factors.py

    # 2. 运行因子评估
    python scripts/evaluate_factors.py

评估因子:
    日频: pe_ttm, pb, ps_ttm
    季频: roe, gross_margin, debt_to_assets, revenue_yoy_growth, net_profit_yoy_growth

评估项:
    - Rank IC 分析 (持有期: 5d, 20d, 60d)
    - IC 衰减曲线
    - 分位分组收益 (5组)
    - 因子截面秩相关系数矩阵
    - 综合评分排序
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# 所有待评估因子
DAILY_FACTORS = ["pe_ttm", "pb", "ps_ttm"]
QUARTERLY_FACTORS = [
    "roe",
    "gross_margin",
    "debt_to_assets",
    "revenue_yoy_growth",
    "net_profit_yoy_growth",
]
ALL_FACTORS = DAILY_FACTORS + QUARTERLY_FACTORS

# 评估参数
EVAL_START = "20200413"
EVAL_END = "20250411"
HORIZONS = [5, 20, 60]


def main() -> None:
    from vnpy.alpha.factors.evaluation import FactorEvaluator

    # 路径
    project_root = Path(__file__).parent.parent
    lab_path = str(project_root / "lab_data")

    if not Path(lab_path).exists():
        logger.error("lab_data 目录不存在: %s", lab_path)
        sys.exit(1)

    # 检查日频因子数据
    daily_path = os.path.expanduser("~/.vntrader/factors/fundamental_daily.parquet")
    if Path(daily_path).exists():
        import polars as pl

        df = pl.read_parquet(daily_path)
        dates = df["trade_date"].unique().sort()
        n_dates = len(dates)
        logger.info("日频因子覆盖 %d 个交易日", n_dates)
        logger.info("日期范围: %s ~ %s", dates[0], dates[-1])
        if n_dates < 100:
            logger.warning(
                "日频因子仅 %d 天，日频因子(pe_ttm/pb/ps_ttm)将不参与评估。（Tushare daily_basic API 需更高积分权限）"
            )
    else:
        logger.warning("日频因子文件不存在，仅评估季频因子")

    # 检查季频因子数据
    q_path = os.path.expanduser("~/.vntrader/factors/fundamental_quarterly.parquet")
    if not Path(q_path).exists():
        logger.error("季频因子文件不存在: %s", q_path)
        sys.exit(1)

    import polars as pl

    qdf = pl.read_parquet(q_path)
    stocks = qdf["vt_symbol"].n_unique()
    factors = qdf["factor_name"].unique().to_list()
    logger.info("季频因子: %d 只股票, %s", stocks, factors)

    logger.info("开始因子评估")
    logger.info("评估区间: %s ~ %s", EVAL_START, EVAL_END)
    logger.info("因子列表: %s", ALL_FACTORS)
    logger.info("持有期: %s", HORIZONS)

    evaluator = FactorEvaluator(
        lab_path=lab_path,
    )

    report = evaluator.evaluate(
        factor_names=ALL_FACTORS,
        start=EVAL_START,
        end=EVAL_END,
        horizons=HORIZONS,
    )

    report.print()

    # 保存 JSON 报告
    import json

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"factor_evaluation_{timestamp}.json"

    with open(report_path, "w", encoding="utf-8") as f:
        data = report.to_dict()
        # 将 tuple 键转为字符串
        for key in list(data["ic_results"].keys()):
            for subkey in list(data["ic_results"][key].keys()):
                if "ic_series" in data["ic_results"][key][subkey]:
                    data["ic_results"][key][subkey]["ic_series"] = [
                        list(item)
                        for item in data["ic_results"][key][subkey]["ic_series"]
                    ]
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("报告已保存: %s", report_path)


if __name__ == "__main__":
    main()
