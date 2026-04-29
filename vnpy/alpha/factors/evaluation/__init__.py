"""
因子评估模块

提供因子有效性的完整评估工具:
- ForwardReturnCalculator: 前向收益计算
- ICAnalyzer: Rank IC 分析
- QuantileAnalyzer: 分位分组收益
- FactorEvaluator: 统一评估入口

用法:
    evaluator = FactorEvaluator(
        lab_path="/path/to/lab_data",
        factor_data_dir="/path/to/factors",
    )
    report = evaluator.evaluate(
        factor_names=["roe", "pe_ttm", "pb"],
        start="2020-04-13",
        end="2025-04-13",
        horizons=[5, 20, 60],
    )
    report.print()
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
import polars as pl
import numpy as np

from vnpy.alpha.factors.evaluation.ic_analysis import ICAnalyzer
from vnpy.alpha.factors.evaluation.quantile import QuantileAnalyzer
from vnpy.alpha.factors.evaluation.returns import (
    DEFAULT_HORIZONS,
    ForwardReturnCalculator,
)

logger = logging.getLogger(__name__)


@dataclass
class FactorReport:
    """因子评估报告"""

    factor_names: list[str]
    horizons: list[int]
    ic_results: dict = field(default_factory=dict)
    quantile_results: dict = field(default_factory=dict)
    correlation_matrix: list[list[float]] = field(default_factory=list)
    scores: list[tuple[str, float]] = field(default_factory=list)

    def __init__(self, factor_names: list[str], horizons: list[int]):
        self.factor_names = factor_names
        self.horizons = horizons
        self.ic_results = {}
        self.quantile_results = {}
        self.correlation_matrix = []
        self.scores = []

    def print(self) -> None:
        """打印报告到控制台"""
        h_str = "/".join(str(h) + "d" for h in self.horizons)

        # ---- IC 汇总表 ----
        print("\n" + "=" * 80)
        print(f"  因子 IC 汇总 (持有期: {h_str})")
        print("=" * 80)

        if self.ic_results:
            horizon = self.horizons[1] if len(self.horizons) > 1 else self.horizons[0]
            key = f"fwd_{horizon}d"
            print(
                f"{'因子':<25s} {'IC均值':>8s} {'IC标准差':>8s} {'IC_IR':>8s} {'IC>0比':>8s} {'期数':>6s}"
            )
            print("-" * 70)

            for fname in self.factor_names:
                info = self.ic_results.get(fname, {}).get(key, {})
                if info:
                    print(
                        f"{fname:<25s} {info.get('ic_mean', 0):>8.4f} "
                        f"{info.get('ic_std', 0):>8.4f} "
                        f"{info.get('ic_ir', 0):>8.4f} "
                        f"{info.get('ic_positive_ratio', 0):>8.2%} "
                        f"{info.get('n_periods', 0):>6d}"
                    )
        print()

        # ---- IC 衰减表 ----
        if self.ic_results:
            print("-" * 80)
            print("  IC 衰减分析")
            print("-" * 80)
            header = f"{'因子':<25s}"
            for h in self.horizons:
                header += f" {f'{h}d':>8s}"
            print(header)
            print("-" * (25 + 9 * len(self.horizons)))

            for fname in self.factor_names:
                row = f"{fname:<25s}"
                for h in self.horizons:
                    col_key = f"fwd_{h}d"
                    info = self.ic_results.get(fname, {}).get(col_key, {})
                    row += f" {info.get('ic_mean', 0):>8.4f}"
                print(row)
        print()

        # ---- 分位收益 ----
        if self.quantile_results:
            print("-" * 80)
            print(f"  分位分组收益 (持有期: {h_str})")
            print("-" * 80)
            key = (
                f"fwd_{self.horizons[1]}d"
                if len(self.horizons) > 1
                else f"fwd_{self.horizons[0]}d"
            )
            for fname in self.factor_names:
                qr = self.quantile_results.get(fname, {})
                groups = qr.get("group_returns", [])
                ls = qr.get("long_short", 0)
                if groups:
                    group_str = " | ".join(
                        f"{label}: {ret:+.4%}" for label, ret in groups
                    )
                    print(f"  {fname}: {group_str}")
                    print(
                        f"    {' ':>10s} 多空收益 (Q5-Q1, 高因子值-低因子值): {ls:+.4%}"
                    )
        print()

        # ---- 相关性矩阵 ----
        if self.correlation_matrix:
            print("-" * 80)
            print("  因子截面秩相关系数矩阵")
            print("-" * 80)
            n = len(self.factor_names)
            header = f"{'':>25s}" + "".join(
                f"{fname[:8]:>10s}" for fname in self.factor_names
            )
            print(header)
            for i, fname in enumerate(self.factor_names):
                row = f"{fname:<25s}"
                for j in range(n):
                    if j < len(self.correlation_matrix[i]):
                        row += f" {self.correlation_matrix[i][j]:>9.4f}"
                print(row)
        print()

        # ---- 综合评分 ----
        if self.scores:
            print("-" * 80)
            print("  综合评分 (IC_IR × 50 + 多空收益 × 30 + IC>0比 × 20)")
            print("-" * 80)
            for fname, score in self.scores:
                stars = "★" * min(5, int(score / 20))
                print(f"  {fname:<25s} {score:>6.2f}  {stars}")
        print()

    def to_dict(self) -> dict:
        """导出为字典"""
        return {
            "factor_names": self.factor_names,
            "horizons": self.horizons,
            "ic_results": self.ic_results,
            "quantile_results": self.quantile_results,
            "correlation_matrix": self.correlation_matrix,
            "scores": self.scores,
        }


class FactorEvaluator:
    """因子评估器

    统一入口：加载因子数据 → 计算前向收益 → IC分析 + 分位收益 + 相关性 → 报告
    """

    def __init__(self, lab_path: str, factor_data_dir: str | None = None):
        self.return_calc = ForwardReturnCalculator(lab_path)
        self.ic_analyzer = ICAnalyzer()
        self.quantile_analyzer = QuantileAnalyzer()
        self.factor_data_dir = factor_data_dir or lab_path

    def evaluate(
        self,
        factor_names: list[str] | None = None,
        start: str = "20200413",
        end: str = "20250413",
        horizons: list[int] | None = None,
        symbols: list[str] | None = None,
    ) -> FactorReport:
        """执行完整的因子评估

        参数:
            factor_names: 要评估的因子名列表，None 表示全部
            start: 起始日期 'YYYYMMDD'
            end: 结束日期 'YYYYMMDD'
            horizons: 持有期列表
            symbols: 限定股票池

        返回:
            FactorReport 包含所有评估结果
        """
        if horizons is None:
            horizons = DEFAULT_HORIZONS

        t0 = time.time()

        # 1. 加载因子值
        logger.info("Step 1: 加载因子数据...")
        factor_df = self._load_factors(factor_names, start, end, symbols)
        if factor_df.is_empty():
            logger.error("因子数据为空")
            return FactorReport([], horizons)

        actual_names = self._get_factor_names(factor_df)
        logger.info(
            "  加载 %d 日数据, %d 个因子", factor_df.shape[0], len(actual_names)
        )

        # 2. 计算前向收益
        logger.info("Step 2: 计算前向收益 (%s)...", horizons)
        all_dates = (
            factor_df.select("trade_date")
            .unique()
            .sort("trade_date")["trade_date"]
            .to_list()
        )
        # 对于前向收益，需要比因子数据最后的日期更远的 bar 数据
        # 所以传入所有日期，ForwardReturnCalculator 会自动处理
        if symbols is None:
            all_symbols = factor_df.select("vt_symbol").unique()["vt_symbol"].to_list()
        else:
            all_symbols = symbols

        returns_df = self.return_calc.calculate(all_symbols, all_dates, horizons)
        if returns_df.is_empty():
            logger.error("前向收益计算为空")
            return FactorReport(actual_names, horizons)

        # 3. IC 分析
        logger.info("Step 3: IC 分析...")
        ic_results = {}
        for h in horizons:
            col = f"fwd_{h}d"
            if col not in returns_df.columns:
                continue
            ic_info = self.ic_analyzer.compute_ic_series(
                factor_df, returns_df, return_col=col
            )
            for fname, info in ic_info.items():
                if fname not in ic_results:
                    ic_results[fname] = {}
                ic_results[fname][col] = info

        # 4. 分位收益
        logger.info("Step 4: 分位分组收益...")
        quantile_results = {}
        main_horizon = horizons[1] if len(horizons) > 1 else horizons[0]
        col = f"fwd_{main_horizon}d"
        if col in returns_df.columns:
            quantile_results = self.quantile_analyzer.group_returns(
                factor_df, returns_df, return_col=col
            )

        # 5. 因子相关性矩阵
        logger.info("Step 5: 因子截面秩相关性...")
        corr_matrix = self._compute_factor_correlation(factor_df, actual_names)

        # 6. 综合评分
        logger.info("Step 6: 综合评分...")
        scores = self._compute_scores(ic_results, quantile_results, main_horizon)

        elapsed = time.time() - t0
        logger.info("评估完成, 耗时 %.1f 秒", elapsed)

        report = FactorReport(actual_names, horizons)
        report.ic_results = ic_results
        report.quantile_results = quantile_results
        report.correlation_matrix = corr_matrix
        report.scores = scores
        return report

    def _load_factors(
        self,
        factor_names: list[str] | None,
        start: str,
        end: str,
        symbols: list[str] | None,
    ) -> pl.DataFrame:
        """从本地 parquet 文件加载因子数据

        支持:
        - 日频因子 (fundamental_daily.parquet): trade_date | vt_symbol | pe_ttm | pb | ps_ttm
        - 季频因子 (fundamental_quarterly.parquet): report_date | pub_date | vt_symbol | factor_name | factor_value
        """
        from pathlib import Path

        lab_dir = str(self.return_calc.lab_data_dir)
        factor_dir = Path.home() / ".vntrader" / "factors"  # 默认因子目录
        if self.factor_data_dir != lab_dir:
            factor_dir = Path(self.factor_data_dir)

        frames = []

        # 日频因子 (宽表) → 转为长表 (trade_date | vt_symbol | factor_name | factor_value)
        daily_path = factor_dir / "fundamental_daily.parquet"
        if daily_path.exists():
            df = pl.read_parquet(daily_path)
            # 识别因子列（在 factor_names 中的列）
            id_cols = ["trade_date", "vt_symbol"]
            if factor_names:
                factor_cols = [c for c in df.columns if c in factor_names]
                df = df.select(id_cols + factor_cols)
            else:
                factor_cols = [c for c in df.columns if c not in id_cols]

            if factor_cols:
                # 宽表 → 长表: unpivot 因子列
                df = df.unpivot(
                    index=id_cols,
                    on=factor_cols,
                    variable_name="factor_name",
                    value_name="factor_value",
                )
                df = df.with_columns(
                    pl.col("factor_value").cast(pl.Float64, strict=False)
                )
                frames.append(df)

        # 季频因子 (长表) — 前值填充至交易日序列
        quarterly_path = factor_dir / "fundamental_quarterly.parquet"
        if quarterly_path.exists():
            qdf = pl.read_parquet(quarterly_path)
            if factor_names:
                qdf = qdf.filter(pl.col("factor_name").is_in(factor_names))

            if not qdf.is_empty():
                # 前值填充：将季频因子按 pub_date 填充到所有交易日
                qdf = self._forward_fill_quarterly(qdf, start, end)
                if not qdf.is_empty():
                    frames.append(qdf)

        logger.debug("加载了 %d 个数据块", len(frames))
        for i, f in enumerate(frames):
            logger.debug("  块 %d: %d 行, 列=%s", i, f.shape[0], f.columns)

        if not frames:
            return pl.DataFrame()

        result = pl.concat(frames, how="vertical")
        logger.info("concat 后: %d 行, 列=%s", result.shape[0], result.columns)

        if symbols:
            result = result.filter(pl.col("vt_symbol").is_in(symbols))

        return result

    def _forward_fill_quarterly(
        self, qdf: pl.DataFrame, start: str, end: str
    ) -> pl.DataFrame:
        """将季频因子按 pub_date 前值填充至所有交易日

        参数:
            qdf: 季频因子数据 (report_date, pub_date, vt_symbol, factor_name, factor_value)
            start/end: 日期范围 'YYYYMMDD'

        返回:
            trade_date | vt_symbol | factor_name | factor_value (填充到每个交易日)
        """
        # 获取所有交易日 (从 bar 数据收集)
        all_dates: set[str] = set()
        for f in self.return_calc.daily_dir.glob("*.parquet"):
            df = pl.read_parquet(f, columns=["datetime"])
            for dt in df["datetime"].unique():
                d = dt.strftime("%Y%m%d")
                if start <= d <= end:
                    all_dates.add(d)

        if not all_dates:
            logger.warning("无法获取交易日列表")
            return pl.DataFrame()

        trade_dates = sorted(all_dates)

        # 收集所有因子名和股票
        factor_names = qdf["factor_name"].drop_nulls().unique().to_list()
        symbols = qdf["vt_symbol"].unique().to_list()

        # 对每个 stock × factor，按 pub_date 排序后前值填充
        result_frames = []
        for sym in symbols:
            sym_df = qdf.filter(pl.col("vt_symbol") == sym)
            if sym_df.is_empty():
                continue

            for fname in factor_names:
                f_df = sym_df.filter(pl.col("factor_name") == fname).sort("pub_date")

                if f_df.is_empty():
                    continue

                pub_dates = f_df["pub_date"].to_list()
                factor_vals = f_df["factor_value"].to_list()

                # 前值填充：对每个交易日，找到 ≤ trade_date 的最新 pub_date
                rows = []
                for td in trade_dates:
                    # 二分查找最近的 pub_date ≤ td
                    # 简单实现：线性扫描（因子数据量小，可以接受）
                    best_val = None
                    best_pub = None
                    for pd_date, val in zip(pub_dates, factor_vals, strict=True):
                        if pd_date <= td and val is not None:
                            if best_pub is None or pd_date > best_pub:
                                best_pub = pd_date
                                best_val = val

                    if best_val is not None:
                        rows.append(
                            {
                                "trade_date": td,
                                "vt_symbol": sym,
                                "factor_name": fname,
                                "factor_value": float(best_val),
                            }
                        )

                if rows:
                    result_frames.append(pl.DataFrame(rows))

        if not result_frames:
            return pl.DataFrame()

        result = pl.concat(result_frames)
        logger.info(
            "季频因子前值填充: %d 只股票 × %d 个因子 → %d 行",
            len(symbols),
            len(factor_names),
            result.shape[0],
        )
        return result

    @staticmethod
    def _get_factor_names(df: pl.DataFrame) -> list[str]:
        """获取因子名称列表"""
        if "factor_name" in df.columns:
            return df["factor_name"].drop_nulls().unique().sort().to_list()
        return [
            c
            for c in df.columns
            if c not in ("trade_date", "vt_symbol", "report_date", "pub_date")
        ]

    def _compute_factor_correlation(
        self, factor_df: pl.DataFrame, factor_names: list[str]
    ) -> list[list[float]]:
        """计算因子截面秩相关系数矩阵"""
        from scipy.stats import spearmanr

        n = len(factor_names)
        matrix = [[0.0] * n for _ in range(n)]

        dates = factor_df["trade_date"].unique().sort().to_list()
        if not dates:
            return matrix

        # 对每个日期计算截面相关，然后平均
        accum = [[0.0] * n for _ in range(n)]
        count = 0

        for d in dates:
            subset = factor_df.filter(pl.col("trade_date") == d)
            if subset.shape[0] < 10:
                continue

            if "factor_name" in subset.columns:
                # 长表格式 → 透视
                try:
                    wide = subset.pivot(
                        values="factor_value",
                        index="vt_symbol",
                        columns="factor_name",
                    )
                except Exception:
                    continue
            else:
                wide = subset

            vals = []
            names_found = []
            for fname in factor_names:
                if fname in wide.columns:
                    arr = wide[fname].to_numpy()
                    arr = arr[~np.isnan(arr)]
                    if len(arr) >= 10:
                        vals.append(arr)
                        names_found.append(fname)

            for i, _fi in enumerate(names_found):
                for j, _fj in enumerate(names_found):
                    if i == j:
                        accum[i][j] += 1.0
                    else:
                        try:
                            min_len = min(len(vals[i]), len(vals[j]))
                            corr, _ = spearmanr(vals[i][:min_len], vals[j][:min_len])
                            if abs(corr) <= 1.0:
                                accum[i][j] += corr
                        except Exception:
                            pass

            count += 1

        if count > 0:
            for i in range(n):
                for j in range(n):
                    matrix[i][j] = round(accum[i][j] / count, 4)

        return matrix

    def _compute_scores(
        self,
        ic_results: dict,
        quantile_results: dict,
        main_horizon: int,
    ) -> list[tuple[str, float]]:
        """综合评分"""
        col = f"fwd_{main_horizon}d"
        factor_names = sorted(
            set(list(ic_results.keys()) + list(quantile_results.keys())) - {None}
        )

        scores = []
        for fname in factor_names:
            ic_info = ic_results.get(fname, {}).get(col, {})
            qr = quantile_results.get(fname, {})

            ic_ir = abs(ic_info.get("ic_ir", 0))
            ic_pos = ic_info.get("ic_positive_ratio", 0)
            ls = abs(qr.get("long_short", 0))

            score = ic_ir * 50 + ls * 30 + ic_pos * 20
            scores.append((fname, round(score, 2)))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores
