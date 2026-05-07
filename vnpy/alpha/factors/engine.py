"""
因子引擎总调度器

通过注册模式管理多个因子维度的完整管线。
支持日终调度和财报季调度。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import polars as pl

from vnpy.alpha.factors.base import DataFetcher, FactorComputer, FactorStorage

if TYPE_CHECKING:
    from vnpy.alpha.factors.checkpoint import CheckpointManager
    from vnpy.alpha.factors.rate_limiter import RateLimiter
    from vnpy.alpha.factors.stock_pool import StockPoolManager

logger = logging.getLogger(__name__)


class FactorPipeline:
    """单个维度的因子计算管线"""

    def __init__(
        self,
        name: str,
        frequency: str,
        fetcher: DataFetcher,
        computer: FactorComputer,
        storage: FactorStorage,
    ):
        self.name = name
        self.frequency = frequency  # "daily" | "quarterly" | "both"
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

        # 全量A股扩展组件（可选注入）
        self.stock_pool: StockPoolManager | None = None
        self.rate_limiter: RateLimiter | None = None
        self.checkpoint: CheckpointManager | None = None

    def register(
        self,
        name: str,
        frequency: str,
        fetcher: DataFetcher,
        computer: FactorComputer,
        storage: FactorStorage,
    ) -> None:
        """注册一个因子维度的完整管线

        参数:
            name: 管线名称
            frequency: 更新频率，"daily" | "quarterly" | "both"
            fetcher: 数据拉取器
            computer: 因子计算器
            storage: 因子存储器
        """
        self.pipelines[name] = FactorPipeline(
            name, frequency, fetcher, computer, storage
        )
        logger.info(f"FactorEngine: 注册管线 '{name}' (frequency={frequency})")

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

        多个维度的数据通过 vt_symbol join 合并。
        """
        base = pl.DataFrame({"vt_symbol": symbols})
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
                base = base.join(df, on="vt_symbol", how="left")
            except FileNotFoundError:
                pass
        return base

    # ---- 全量A股扩展方法 ----

    def init_stock_pool(self, data_dir: str | None = None) -> None:
        """初始化全量股票池管理器

        创建 StockPoolManager 实例并赋值给 self.stock_pool，
        同时配套创建 RateLimiter 和 CheckpointManager。

        参数:
            data_dir: 缓存目录，默认使用 self.data_dir
        """
        from vnpy.alpha.factors.checkpoint import CheckpointManager
        from vnpy.alpha.factors.rate_limiter import RateLimiter
        from vnpy.alpha.factors.stock_pool import StockPoolManager

        root = data_dir or self.data_dir
        self.stock_pool = StockPoolManager(root)
        self.rate_limiter = RateLimiter(rate_per_minute=200)
        self.checkpoint = CheckpointManager(root, task_name="quarterly_sync")
        logger.info("FactorEngine: 已初始化全量股票池、限流器和断点管理器")

    def run_quarterly_batch(
        self, symbols: list[str], end_date: str, batch_size: int = 50
    ) -> dict:
        """分批执行季频因子更新（支持断点恢复）

        与 run_quarterly() 的区别：
        - 使用 RateLimiter 控制 API 调用频率
        - 使用 CheckpointManager 支持断点恢复
        - 每批处理后更新 checkpoint，确保中断后可继续

        参数:
            symbols: 待处理的股票池代码列表
            end_date: 报告期截止日 'YYYYMMDD'
            batch_size: 每批处理的股票数量，默认 50

        返回:
            {pipeline_name: stats_dict}
        """
        if self.rate_limiter is None or self.checkpoint is None:
            logger.warning(
                "RateLimiter 或 CheckpointManager 未初始化，回退到 run_quarterly()"
            )
            return self.run_quarterly(symbols, end_date)

        import time

        from vnpy.alpha.factors.fundamental.fetcher import _to_tushare_code

        results: dict = {}
        for name, pipeline in self.pipelines.items():
            if pipeline.frequency not in ("quarterly", "both"):
                continue

            # duck typing: 检查是否具备季频拉取/计算能力
            if not (
                hasattr(pipeline.fetcher, "fetch_income")
                and hasattr(pipeline.fetcher, "fetch_fina_indicator")
                and hasattr(pipeline.fetcher, "fetch_disclosure_dates")
            ):
                continue
            if not hasattr(pipeline.computer, "compute_quarterly"):
                continue

            # 注入 RateLimiter 到 fetcher（如果尚未注入）
            if getattr(pipeline.fetcher, "rate_limiter", None) is None:
                pipeline.fetcher.rate_limiter = self.rate_limiter

            logger.info("FactorEngine: 执行管线 '%s' 分批季频更新", name)

            # 从 checkpoint 恢复已处理列表
            processed = self.checkpoint.get_processed(end_date)
            pending = [s for s in symbols if s not in processed]
            logger.info(
                "季频分批: 总计 %d, 已处理 %d, 待处理 %d",
                len(symbols),
                len(processed),
                len(pending),
            )

            if not pending:
                logger.info("所有股票均已处理，跳过")
                self.checkpoint.mark_complete(end_date)
                results[name] = {
                    "symbols_updated": 0,
                    "batches": 0,
                    "status": "already_complete",
                }
                continue

            total_updated = 0
            total_batches = 0
            total_failed: list[dict] = []
            total_empty = 0  # 有拉取数据但计算后无因子产出的股票

            # 分批处理（individual fetcher calls use
            # rate_limiter.acquire() to throttle）
            for batch_idx in range(0, len(pending), batch_size):
                batch = pending[batch_idx : batch_idx + batch_size]

                batch_updated = 0
                batch_failed: list[dict] = []
                batch_empty = 0

                for symbol in batch:
                    ts_code = _to_tushare_code(symbol)
                    try:
                        income_raw = pipeline.fetcher.fetch_income(ts_code)
                        fina_raw = pipeline.fetcher.fetch_fina_indicator(ts_code)

                        if income_raw.is_empty() or fina_raw.is_empty():
                            logger.warning(
                                "季频因子数据为空 %s: income=%d, fina=%d",
                                symbol,
                                len(income_raw),
                                len(fina_raw),
                            )
                            batch_empty += 1
                            continue

                        disc_raw = pipeline.fetcher.fetch_disclosure_dates(ts_code)

                        quarterly = pipeline.computer.compute_quarterly(
                            income_raw, fina_raw, disc_raw
                        )
                        if not quarterly.is_empty():
                            if hasattr(pipeline.storage, "save_quarterly"):
                                pipeline.storage.save_quarterly(quarterly)
                            else:
                                pipeline.storage.save(quarterly)
                            batch_updated += 1
                        else:
                            logger.warning(
                                "季频因子计算无产出 %s: income=%d, fina=%d",
                                symbol,
                                len(income_raw),
                                len(fina_raw),
                            )
                            batch_empty += 1
                    except Exception as e:
                        logger.warning("季频因子计算失败 %s: %s", symbol, e)
                        batch_failed.append({"symbol": symbol, "error": str(e)})

                total_updated += batch_updated
                total_failed.extend(batch_failed)
                total_empty += batch_empty
                total_batches += 1

                # 更新 checkpoint
                current_processed = list(processed | set(batch))
                self.checkpoint.save(
                    end_date,
                    total_batches,
                    current_processed,
                    total_failed,
                    "in_progress",
                )

                logger.info(
                    "批次 %d/%d: 成功 %d/%d, 空=%d, 失败=%d, 累计 %d/%d",
                    total_batches,
                    (len(pending) + batch_size - 1) // batch_size,
                    batch_updated,
                    len(batch),
                    batch_empty,
                    len(batch_failed),
                    total_updated,
                    len(pending),
                )

                # 批次间额外间隔（对 Tushare 服务器友好）
                if batch_idx + batch_size < len(pending):
                    time.sleep(3)

            # 完成
            self.checkpoint.mark_complete(end_date)
            results[name] = {
                "symbols_updated": total_updated,
                "batches": total_batches,
                "failed_count": len(total_failed),
                "empty_count": total_empty,
                "status": "completed",
            }
            logger.info(
                "管线 '%s' 分批季频完成: 更新 %d, 空数据 %d, 失败 %d, 共 %d 批",
                name,
                total_updated,
                total_empty,
                len(total_failed),
                total_batches,
            )

        return results if results else {"skipped": "no quarterly pipeline found"}

    # ---- 内部方法 ----

    def _run_daily_pipeline(
        self,
        pipeline: FactorPipeline,
        symbols: list[str],
        trade_date: str,
    ) -> dict:
        """执行单个管线的日频更新"""
        # 根据 frequency 判断是否执行日频更新
        if pipeline.frequency not in ("daily", "both"):
            return {"skipped": True}

        # 根据具体类型执行对应的 fetch 和 compute
        from vnpy.alpha.factors.fundamental.fetcher import FundamentalFetcher
        from vnpy.alpha.factors.fundamental.factors import FundamentalComputer

        if isinstance(pipeline.fetcher, FundamentalFetcher):
            if not isinstance(pipeline.computer, FundamentalComputer):
                return {"error": "computer 类型不匹配"}
            raw = pipeline.fetcher.fetch_daily_basic(trade_date)
            if raw.is_empty():
                return {"fetched": 0, "stored": 0}
            factors = pipeline.computer.compute_daily(raw)
            if hasattr(pipeline.storage, "save_daily"):
                pipeline.storage.save_daily(factors)
            else:
                pipeline.storage.save(factors)
            return {"fetched": len(raw), "stored": len(factors)}

        return {"skipped": True}

    def _run_quarterly_pipeline(
        self,
        pipeline: FactorPipeline,
        symbols: list[str],
        end_date: str,
    ) -> dict:
        """执行单个管线的季频更新"""
        # 根据 frequency 判断是否执行季频更新
        if pipeline.frequency not in ("quarterly", "both"):
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
        total_empty = 0
        for symbol in symbols:
            ts_code = _to_tushare_code(symbol)
            try:
                income_raw = pipeline.fetcher.fetch_income(ts_code)
                fina_raw = pipeline.fetcher.fetch_fina_indicator(ts_code)

                if income_raw.is_empty() or fina_raw.is_empty():
                    logger.warning(
                        "季频因子数据为空 %s: income=%d, fina=%d",
                        symbol,
                        len(income_raw),
                        len(fina_raw),
                    )
                    total_empty += 1
                    continue

                disc_raw = pipeline.fetcher.fetch_disclosure_dates(ts_code)

                quarterly = pipeline.computer.compute_quarterly(
                    income_raw, fina_raw, disc_raw
                )
                if not quarterly.is_empty():
                    # 使用 hasattr 检查 storage 方法，避免抽象基类属性缺失
                    if hasattr(pipeline.storage, "save_quarterly"):
                        pipeline.storage.save_quarterly(quarterly)
                    else:
                        pipeline.storage.save(quarterly)
                    total_computed += 1
                else:
                    logger.warning(
                        "季频因子计算无产出 %s: income=%d, fina=%d",
                        symbol,
                        len(income_raw),
                        len(fina_raw),
                    )
                    total_empty += 1
            except Exception as e:
                logger.warning(f"季频因子计算失败 {symbol}: {e}")
                continue

        return {"symbols_updated": total_computed, "empty_count": total_empty}
