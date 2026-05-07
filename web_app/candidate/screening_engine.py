#!/usr/bin/env python3
"""候选股筛选引擎 — 调度入口

每日收盘后：
1. 获取候选池股票日线数据（Tushare Pro）          → engine.py
2. 计算四类技术因子得分（动量/趋势/量价/波动）      → factors.py
3. 归一化 + 排名                                    → scoring.py
4. 结果存入 CandidateStock 数据库表                 → scoring.py
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta

import polars as pl

from web_app.candidate.candidate_types import CandidateResult
from web_app.candidate.engine import (
    STOCK_POOL,
    fetch_all_stocks_data,
    fetch_daily_data,
)
from web_app.candidate.factors import score_stock
from web_app.candidate.scoring import score_and_rank, save_results_to_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 筛选主流程
# ---------------------------------------------------------------------------


def run_screening(
    stock_pool: list[str] | None = None,
    top_n: int = 30,
    mode: str = "pool",
) -> tuple[list[dict], int, float]:
    """执行一次完整筛选

    Args:
        stock_pool: 股票池列表，仅 mode="pool" 时使用
        top_n: 返回 Top N 只
        mode: "pool" 使用手动股票池逐只获取，"full" 全市场批量获取

    返回: (results, pool_size, elapsed_seconds)
    """
    start = time.time()
    results: list[CandidateResult] = []

    # --- 1. 获取日线数据 ---
    if mode == "full":
        all_data = fetch_all_stocks_data()
        pool_size = len(all_data)
        logger.info(f"开始全市场筛选，股票池 {pool_size} 只")
    else:
        if stock_pool is None:
            stock_pool = STOCK_POOL
        pool_size = len(stock_pool)
        all_data = {}
        logger.info(f"开始筛选，股票池 {pool_size} 只")
        for symbol in stock_pool:
            data = fetch_daily_data(symbol)
            if data is None:
                continue
            time.sleep(0.2)
            all_data[data["symbol"]] = data

    # --- 2. 因子打分 ---
    for _symbol, data in all_data.items():
        result = score_stock(data)
        if result:
            results.append(result)

    # --- 2.5 加载基本面评分 ---
    if results:
        try:
            fundamental_scores = _load_fundamental_scores([r.symbol for r in results])
            for r in results:
                r.fundamental_score = fundamental_scores.get(r.symbol, 0.0)
            scored_count = sum(1 for r in results if r.fundamental_score > 0)
            logger.info(
                "基本面评分加载: %d / %d 只有效评分", scored_count, len(results)
            )
        except Exception as e:
            logger.warning("基本面评分加载失败（降级运行）: %s", e)

    # --- 3. 评分 + 排名 ---
    top = score_and_rank(results, top_n=top_n)

    elapsed = round(time.time() - start, 1)
    logger.info(
        f"筛选完成：{len(results)} 只有效股票 → Top {len(top)}，耗时 {elapsed}s"
    )

    return _results_to_dicts(top), pool_size, elapsed


def _results_to_dicts(candidates: list[CandidateResult]) -> list[dict]:
    """将 CandidateResult 列表转为 API 兼容的 dict 列表"""
    return [
        {
            "symbol": r.symbol,
            "name": r.name,
            "score": r.combined_score,
            "fundamental_score": r.fundamental_score,
            "technical_score": r.technical_score,
            "performance_score": r.performance_score,
            "combined_score": r.combined_score,
            "rank": r.rank,
            "momentum_score": r.momentum_score,
            "trend_score": r.trend_score,
            "volume_score": r.volume_score,
            "volatility_score": r.volatility_score,
            "current_price": r.current_price,
            "total_return": r.total_return,
            "max_drawdown": r.max_drawdown,
            "sharpe_ratio": r.sharpe_ratio,
        }
        for r in candidates
    ]


def _load_fundamental_scores(symbols: list[str]) -> dict[str, float]:
    """从基本面评分系统获取每只股票的 final_score

    加载日频+季频因子快照，计算多维评分，返回 {symbol: final_score} 映射。
    symbol 格式为 000001.SZ / 600036.SH（候选池内的简写格式）。
    """
    try:
        from vnpy.alpha.factors.fundamental.storage import FundamentalStorage
        from vnpy.alpha.factors.scoring import compute_final_score_only

        storage = FundamentalStorage()

        # 构建完整 vt_symbol 列表（基本面系统用 xx.SSE/xx.SZSE 格式）
        vt_symbols = []
        for s in symbols:
            # 候选池格式: 600036.SH → 600036.SSE
            parts = s.split(".")
            if len(parts) == 2:
                suffix = "SSE" if parts[1] in ("SH", "SSE") else "SZSE"
                vt_symbols.append(f"{parts[0]}.{suffix}")
            else:
                vt_symbols.append(s)

        # 1. 加载因子快照（日频 + 季频 + 动量）
        end = datetime.now()
        start = end - timedelta(days=120)

        daily = storage.load(vt_symbols, start, end)
        if daily.is_empty() or "close" not in daily.columns:
            logger.debug("日频因子数据不足，跳过基本面评分")
            return {}

        # 2. 取最新交易日快照
        latest_date = daily["trade_date"].max()
        snapshot = daily.filter(pl.col("trade_date") == latest_date)

        # 3. 合并季频因子（PIT 约束: 只取截至最新交易日已公告的数据）
        quarterly = storage.get_latest_quarterly_snapshot(
            vt_symbols, as_of_date=latest_date
        )
        if not quarterly.is_empty():
            snapshot = snapshot.join(quarterly, on="vt_symbol", how="left")

        # 4. 计算 60 日动量
        hist_sorted = daily.sort(["vt_symbol", "trade_date"])
        latest_close = hist_sorted.group_by("vt_symbol").agg(
            [
                pl.col("close").drop_nulls().last().alias("_latest_close"),
                pl.col("close").drop_nulls().first().alias("_past_close"),
            ]
        )
        momentum = latest_close.with_columns(
            pl.when(pl.col("_past_close") > 0)
            .then(pl.col("_latest_close") / pl.col("_past_close") - 1.0)
            .otherwise(pl.lit(None))
            .alias("momentum_60d")
        ).select(["vt_symbol", "momentum_60d"])
        snapshot = snapshot.join(momentum, on="vt_symbol", how="left")

        # 5. 计算多维评分
        scored = compute_final_score_only(snapshot)
        if scored.is_empty():
            return {}

        # 6. 格式转换: vt_symbol → 候选池简写格式
        result: dict[str, float] = {}
        for row in scored.to_dicts():
            vt = row.get("vt_symbol", "")
            score = row.get("final_score", 0)
            if not vt or score is None:
                continue
            # xx.SSE → xx.SH
            simple = vt.replace(".SSE", ".SH").replace(".SZSE", ".SZ")
            result[simple] = round(float(score), 2)

        return result
    except ImportError as e:
        logger.warning("因子评分模块未安装，跳过基本面评分: %s", e)
        return {}
    except FileNotFoundError as e:
        logger.info("基本面 Parquet 文件尚未生成，跳过基本面评分: %s", e)
        return {}
    except Exception as e:
        logger.warning("基本面评分计算异常: %s", e)
        return {}


# ---------------------------------------------------------------------------
# 每日调度入口
# ---------------------------------------------------------------------------


def run_daily_screening():
    """每日筛选主入口 — 由调度器调用"""
    logger.info("=== 开始每日候选股筛选 ===")
    try:
        results, pool_size, elapsed = run_screening()
        _save_daily_results(results)
        logger.info(
            f"=== 每日候选股筛选完成，股票池 {pool_size}，"
            f"Top {len(results)}，耗时 {elapsed}s ==="
        )
        return results, pool_size, elapsed
    except Exception as e:
        logger.error(f"每日候选股筛选失败: {e}")
        raise


def _save_daily_results(results: list[dict]) -> None:
    """将 dict 列表转为 CandidateResult 并存入 DB"""
    candidates = [
        CandidateResult(
            symbol=r["symbol"],
            name=r["name"],
            fundamental_score=r.get("fundamental_score", 0.0),
            momentum_score=r["momentum_score"],
            trend_score=r["trend_score"],
            volume_score=r["volume_score"],
            volatility_score=r["volatility_score"],
            technical_score=r["technical_score"],
            performance_score=r.get("performance_score", 0.0),
            combined_score=r["combined_score"],
            rank=r["rank"],
            current_price=r["current_price"],
            total_return=r["total_return"],
            max_drawdown=r["max_drawdown"],
            sharpe_ratio=r["sharpe_ratio"],
        )
        for r in results
    ]
    save_results_to_db(candidates, date.today())
