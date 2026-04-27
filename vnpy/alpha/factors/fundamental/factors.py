"""
基本面因子计算器

从拉取的 Tushare 原始数据中计算 7 个基本面因子:
  - 季频 (长表格式): revenue_yoy_growth, net_profit_yoy_growth, roe, gross_margin, debt_to_assets
  - 日频 (宽表格式): pe_ttm, pb, ps_ttm

季频因子输出格式:
    report_date | pub_date  | vt_symbol  | factor_name          | factor_value
日频因子输出格式:
    trade_date  | vt_symbol | pe_ttm  | pb     | ps_ttm
"""

import logging
from datetime import datetime

import numpy as np
import polars as pl

from vnpy.alpha.factors.base import FactorComputer
from vnpy.alpha.factors.fundamental.fetcher import _to_vnpy_code

logger = logging.getLogger(__name__)

# 季频因子列表
QUARTERLY_FACTORS = [
    "revenue_yoy_growth",
    "net_profit_yoy_growth",
    "roe",
    "gross_margin",
    "debt_to_assets",
]


class FundamentalComputer(FactorComputer):
    """基本面因子计算器"""

    def compute(self, raw_df: pl.DataFrame) -> pl.DataFrame:
        """统一入口，根据输入数据类型分发"""
        raise NotImplementedError("请调用 compute_quarterly() 或 compute_daily()")

    def compute_daily(self, daily_basic_df: pl.DataFrame) -> pl.DataFrame:
        """从 daily_basic 数据计算日频因子

        输入: trade_date, ts_code, pe_ttm, pb, ps_ttm, ...
        输出: trade_date, vt_symbol, pe_ttm, pb, ps_ttm
        """
        if daily_basic_df.is_empty():
            return pl.DataFrame()

        df = daily_basic_df.with_columns(
            pl.col("ts_code")
            .map_elements(_to_vnpy_code, return_dtype=pl.Utf8)
            .alias("vt_symbol"),
        )

        # 只保留需要的因子列
        keep_cols = ["trade_date", "vt_symbol", "pe_ttm", "pb", "ps_ttm"]
        existing = [c for c in keep_cols if c in df.columns]
        df = df.select(existing)

        # 将估值倒数化（高估值 = 低得分），因子值为正指标
        for col in ["pe_ttm", "pb", "ps_ttm"]:
            if col in df.columns:
                df = df.with_columns(
                    pl.when(pl.col(col) > 0)
                    .then(1.0 / pl.col(col))
                    .otherwise(pl.lit(None))
                    .alias(col)
                )

        df = df.with_columns(
            pl.col("trade_date").cast(pl.Utf8),
            pl.col("vt_symbol").cast(pl.Utf8),
        )

        for col in ["pe_ttm", "pb", "ps_ttm"]:
            if col in df.columns:
                df = df.with_columns(pl.col(col).cast(pl.Float64))

        return df

    def compute_quarterly(
        self,
        income_df: pl.DataFrame,
        fina_df: pl.DataFrame,
        disclosure_df: pl.DataFrame,
    ) -> pl.DataFrame:
        """计算季频因子，输出长表

        输入: 利润表、财务指标、公告日期三张表（单只股票的）
        输出: report_date | pub_date | vt_symbol | factor_name | factor_value
        """
        if income_df.is_empty() or fina_df.is_empty():
            return pl.DataFrame()

        # 将 ts_code 统一为 vnpy 格式 -- NOTE: Polars DataFrames are immutable
        # so we need to reassign after with_columns
        frames = []
        for frame in [income_df, fina_df, disclosure_df]:
            if (
                not frame.is_empty()
                and "vt_symbol" not in frame.columns
                and "ts_code" in frame.columns
            ):
                frame = frame.with_columns(
                    pl.col("ts_code")
                    .map_elements(_to_vnpy_code, return_dtype=pl.Utf8)
                    .alias("vt_symbol")
                )
            frames.append(frame)
        income_df, fina_df, disclosure_df = frames[0], frames[1], frames[2]

        vt_symbol = income_df["vt_symbol"][0]

        # ---- 构建公告日期映射 ----
        if not disclosure_df.is_empty():
            pub_dates = {}
            for row in disclosure_df.iter_rows(named=True):
                end = row.get("end_date", "")
                actual = row.get("actual_date", "")
                pre = row.get("pre_date", "")
                pub = actual if actual and actual != "nan" else pre
                if end and pub and pub != "nan":
                    pub_dates[str(end)] = str(pub)
        else:
            pub_dates = {}

        # ---- 利润表因子 ----
        income_sorted = income_df.sort("end_date")
        income_dict = {
            str(r["end_date"]): r for r in income_sorted.iter_rows(named=True)
        }

        rows = []

        for end_date_str, row in income_dict.items():
            # 计算去年同期日期
            try:
                end_dt = datetime.strptime(end_date_str, "%Y%m%d")
                prev_year = str(end_dt.year - 1) + end_date_str[4:]
            except ValueError:
                continue

            pub_date_str = pub_dates.get(end_date_str, end_date_str)
            rev = self._safe_float(row.get("revenue"))
            net = self._safe_float(row.get("n_income"))

            # 营收同比增速
            if prev_year in income_dict:
                prev_rev = self._safe_float(income_dict[prev_year].get("revenue"))
                prev_net = self._safe_float(income_dict[prev_year].get("n_income"))
                if prev_rev and prev_rev != 0:
                    rows.append(
                        (
                            end_date_str,
                            pub_date_str,
                            vt_symbol,
                            "revenue_yoy_growth",
                            round(rev / abs(prev_rev) - 1, 6),
                        )
                    )
                if prev_net and prev_net != 0:
                    rows.append(
                        (
                            end_date_str,
                            pub_date_str,
                            vt_symbol,
                            "net_profit_yoy_growth",
                            round(net / abs(prev_net) - 1, 6),
                        )
                    )

        # ---- 财务指标因子 ----
        fina_sorted = fina_df.sort("end_date")
        for row in fina_sorted.iter_rows(named=True):
            end_date_str = str(row["end_date"])
            pub_date_str = pub_dates.get(end_date_str, end_date_str)

            # ROE
            roe_val = self._safe_float(row.get("roe"))
            if roe_val is not None:
                rows.append(
                    (end_date_str, pub_date_str, vt_symbol, "roe", round(roe_val, 6))
                )

            # 毛利率
            gm_val = self._safe_float(row.get("grossprofit_margin"))
            if gm_val is not None:
                rows.append(
                    (
                        end_date_str,
                        pub_date_str,
                        vt_symbol,
                        "gross_margin",
                        round(gm_val, 6),
                    )
                )

            # 资产负债率
            debt_val = self._safe_float(row.get("debt_to_assets"))
            if debt_val is not None:
                rows.append(
                    (
                        end_date_str,
                        pub_date_str,
                        vt_symbol,
                        "debt_to_assets",
                        round(debt_val, 6),
                    )
                )

        if not rows:
            return pl.DataFrame()

        return pl.DataFrame(
            rows,
            schema=[
                "report_date",
                "pub_date",
                "vt_symbol",
                "factor_name",
                "factor_value",
            ],
            orient="row",
        )

    @staticmethod
    def _safe_float(val):
        """安全转换浮点数，处理 nan/inf"""
        if val is None:
            return None
        try:
            f = float(val)
            if np.isnan(f) or np.isinf(f):
                return None
            return f
        except (ValueError, TypeError):
            return None
