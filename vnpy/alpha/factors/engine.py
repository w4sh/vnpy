"""
因子引擎总调度器

通过注册模式管理多个因子维度的完整管线。
支持日终调度和财报季调度。
"""

import logging
from datetime import datetime

import polars as pl

from vnpy.alpha.factors.base import DataFetcher, FactorComputer, FactorStorage

logger = logging.getLogger(__name__)


class FactorPipeline:
    """单个维度的因子计算管线"""

    def __init__(
        self,
        name: str,
        fetcher: DataFetcher,
        computer: FactorComputer,
        storage: FactorStorage,
    ):
        self.name = name
        self.fetcher = fetcher
        self.computer = computer
        self.storage = storage


class FactorEngine:
    """因子引擎总调度器"""

    def __init__(self, data_dir: str | None = None):
        if data_dir is None:
            import os

            data_dir = os.path.join(os.path.expanduser("~"), ".vntrader", "factors")
        self.data_dir = data_dir
        self.pipelines: dict[str, FactorPipeline] = {}

    def register(
        self,
        name: str,
        fetcher: DataFetcher,
        computer: FactorComputer,
        storage: FactorStorage,
    ) -> None:
        """注册一个因子维度的完整管线"""
        self.pipelines[name] = FactorPipeline(name, fetcher, computer, storage)
        logger.info(f"FactorEngine: 注册管线 '{name}'")

    def run_daily(self, symbols: list[str], trade_date: str) -> dict:
        """执行日终因子更新

        参数:
            symbols: 股票池代码列表
            trade_date: 交易日 'YYYYMMDD'
        返回:
            {pipeline_name: stats_dict}
        """
        results = {}
        for name, pipeline in self.pipelines.items():
            logger.info(f"FactorEngine: 执行管线 '{name}' 日频更新")
            try:
                stats = self._run_daily_pipeline(pipeline, symbols, trade_date)
                results[name] = stats
            except Exception as e:
                logger.error(f"管线 '{name}' 日频更新失败: {e}")
                results[name] = {"error": str(e)}
        return results

    def run_quarterly(self, symbols: list[str], end_date: str) -> dict:
        """执行季频因子更新（仅基本面维度）

        参数:
            symbols: 股票池代码列表
            end_date: 报告期截止日 'YYYYMMDD'
        """
        results = {}
        for name, pipeline in self.pipelines.items():
            logger.info(f"FactorEngine: 执行管线 '{name}' 季频更新")
            try:
                stats = self._run_quarterly_pipeline(pipeline, symbols, end_date)
                results[name] = stats
            except Exception as e:
                logger.error(f"管线 '{name}' 季频更新失败: {e}")
                results[name] = {"error": str(e)}
        return results

    # ---- 因子矩阵输出 ----

    def get_factor_matrix(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        """输出标准化的日频因子宽表，供 AlphaDataset 注入

        宽表格式: datetime | vt_symbol | 因子1 | 因子2 | ...

        AlphaDataset 用法:
          for factor_name in factor_columns:
              factor_df = matrix.select(["datetime", "vt_symbol", factor_name])
              factor_df = factor_df.rename({factor_name: "data"})
              dataset.add_feature(factor_name, result=factor_df)
        """
        frames = []
        for pipeline in self.pipelines.values():
            try:
                df = pipeline.storage.load(symbols, start, end)
                if not df.is_empty():
                    frames.append(df)
            except FileNotFoundError:
                logger.warning(f"管线 '{pipeline.name}': 数据文件不存在，跳过")
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames)

    def get_latest_snapshot(self, symbols: list[str]) -> pl.DataFrame:
        """获取最新交易日因子快照（供 Web API）

        对于有 vt_symbol 的维度直接合并，对于市场级维度（如 flow）
        广播到所有 symbols。
        """
        frames = []
        for pipeline in self.pipelines.values():
            try:
                df = pipeline.storage.get_latest(symbols)
                if df.is_empty():
                    continue
                # 如果是市场级数据(无 vt_symbol 列)，广播到所有 symbols
                if "vt_symbol" not in df.columns:
                    score_cols = [c for c in df.columns if c != "trade_date"]
                    rows = []
                    for sym in symbols:
                        row = {"vt_symbol": sym}
                        for c in score_cols:
                            row[c] = df[0, c]
                        rows.append(row)
                    df = pl.DataFrame(rows)
                frames.append(df)
            except FileNotFoundError:
                pass
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames)

    # ---- 内部方法 ----

    def _run_daily_pipeline(
        self,
        pipeline: FactorPipeline,
        symbols: list[str],
        trade_date: str,
    ) -> dict:
        """执行单个管线的日频更新"""
        # 基本面管线: daily_basic 估值数据
        if pipeline.name == "fundamental":
            from vnpy.alpha.factors.fundamental.fetcher import FundamentalFetcher
            from vnpy.alpha.factors.fundamental.factors import FundamentalComputer

            if not isinstance(pipeline.fetcher, FundamentalFetcher):
                return {"error": "fetcher 类型不匹配"}
            if not isinstance(pipeline.computer, FundamentalComputer):
                return {"error": "computer 类型不匹配"}

            raw = pipeline.fetcher.fetch_daily_basic(trade_date)
            if raw.is_empty():
                return {"fetched": 0, "stored": 0}
            factors = pipeline.computer.compute_daily(raw)
            pipeline.storage.save_daily(factors)
            return {"fetched": len(raw), "stored": len(factors)}
        # 资金流向管线: 北向资金数据
        elif pipeline.name == "flow":
            from vnpy.alpha.factors.flow.fetcher import FlowFetcher
            from vnpy.alpha.factors.flow.factors import FlowComputer

            if not isinstance(pipeline.fetcher, FlowFetcher):
                return {"error": "fetcher 类型不匹配"}
            if not isinstance(pipeline.computer, FlowComputer):
                return {"error": "computer 类型不匹配"}

            raw = pipeline.fetcher.fetch_hsgt_flow(trade_date)
            if raw.is_empty():
                return {"fetched": 0, "stored": 0}
            factors = pipeline.computer.compute_flow(raw)
            pipeline.storage.save(factors)
            return {"fetched": len(raw), "stored": len(factors)}

        # 其他管线（二期、三期）在此扩展
        return {"skipped": True}

    def _run_quarterly_pipeline(
        self,
        pipeline: FactorPipeline,
        symbols: list[str],
        end_date: str,
    ) -> dict:
        """执行单个管线的季频更新"""
        if pipeline.name != "fundamental":
            return {"skipped": True}

        from vnpy.alpha.factors.fundamental.fetcher import (
            FundamentalFetcher,
            _to_tushare_code,
        )
        from vnpy.alpha.factors.fundamental.factors import FundamentalComputer

        if not isinstance(pipeline.fetcher, FundamentalFetcher):
            return {"error": "fetcher 类型不匹配"}
        if not isinstance(pipeline.computer, FundamentalComputer):
            return {"error": "computer 类型不匹配"}

        total_computed = 0
        for symbol in symbols:
            ts_code = _to_tushare_code(symbol)
            try:
                income_raw = pipeline.fetcher.fetch_income(ts_code)
                fina_raw = pipeline.fetcher.fetch_fina_indicator(ts_code)
                disc_raw = pipeline.fetcher.fetch_disclosure_dates(ts_code)

                quarterly = pipeline.computer.compute_quarterly(
                    income_raw, fina_raw, disc_raw
                )
                if not quarterly.is_empty():
                    pipeline.storage.save_quarterly(quarterly)
                    total_computed += 1
            except Exception as e:
                logger.warning(f"季频因子计算失败 {symbol}: {e}")
                continue

        return {"symbols_updated": total_computed}
