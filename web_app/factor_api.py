"""
前瞻因子 Web API

提供 3 个端点:
  GET /api/factors/snapshot       — 最新因子快照
  GET /api/factors/history        — 单只股票因子历史
  GET /api/factors/detail         — 单只股票维度贡献分解
"""

import logging
from datetime import datetime

import polars as pl
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

factor_bp = Blueprint("factors", __name__, url_prefix="/api/factors")


def get_engine():
    """延迟初始化 FactorEngine (导入 Tushare 较慢)

    若 Tushare Token 未配置，返回 None。
    """
    try:
        from vnpy.alpha.factors import FactorEngine
        from vnpy.alpha.factors.fundamental import (
            FundamentalFetcher,
            FundamentalComputer,
            FundamentalStorage,
        )

        engine = FactorEngine()
        engine.register(
            "fundamental",
            FundamentalFetcher(),
            FundamentalComputer(),
            FundamentalStorage(),
        )
        return engine
    except RuntimeError as e:
        logger.warning(f"FactorEngine 初始化失败: {e}")
        return None


def get_stock_pool():
    """从候选股模块获取股票池"""
    try:
        from web_app.candidate.screening_engine import STOCK_POOL

        return STOCK_POOL
    except ImportError:
        return []


@factor_bp.route("/snapshot")
def snapshot():
    """获取最新因子快照

    Query params:
        date: 可选，指定日期 YYYY-MM-DD，默认最新
        sort: 排序字段，默认 final_score
    """
    try:
        symbols = get_stock_pool()
        if not symbols:
            return jsonify({"error": "无可用股票池"}), 500

        engine = get_engine()
        if engine is None:
            return jsonify(
                {
                    "count": 0,
                    "data": [],
                    "message": "Tushare Token 未配置，请设置 TUSHARE_TOKEN 环境变量后重启服务",
                }
            )

        latest = engine.get_latest_snapshot(symbols)

        # 如果没有融合层，先做基本面维度评分
        from vnpy.alpha.factors.fusion import DimensionScorer

        if not latest.is_empty():
            daily_factors = ["pe_ttm", "pb", "ps_ttm"]
            existing = [c for c in daily_factors if c in latest.columns]
            if existing:
                scorer = DimensionScorer()
                fund_score = scorer.score(latest, existing)
                # 合并
                latest = latest.join(fund_score, on="vt_symbol", how="left")
                latest = latest.with_columns(
                    pl.col("dimension_score").alias("fundamental_score")
                )
                latest = latest.with_columns(
                    pl.col("fundamental_score").alias("final_score")
                )

            # 排序
            sort_col = request.args.get("sort", "final_score")
            if sort_col in latest.columns:
                latest = latest.sort(sort_col, descending=True)

        result = latest.head(50).to_dicts()
        return jsonify({"count": len(result), "data": result})
    except Exception as e:
        logger.error(f"因子快照 API 异常: {e}")
        return jsonify({"error": str(e)}), 500


@factor_bp.route("/history")
def history():
    """获取单只股票因子历史序列

    Query params:
        symbol: 000001.SZSE
        days: 最大天数，默认 60
    """
    symbol = request.args.get("symbol", "")
    days = int(request.args.get("days", 60))

    if not symbol:
        return jsonify({"error": "缺少 symbol 参数"}), 400

    try:
        engine = get_engine()
        if engine is None:
            return jsonify({"count": 0, "data": [], "message": "Tushare Token 未配置"})

        end = datetime.now()
        from datetime import timedelta

        start = end - timedelta(days=days)

        matrix = engine.get_factor_matrix([symbol], start, end)
        if matrix.is_empty():
            return jsonify({"count": 0, "data": [], "message": "无数据"})

        matrix = matrix.sort("trade_date")
        result = matrix.to_dicts()
        return jsonify({"count": len(result), "data": result})
    except Exception as e:
        logger.error(f"因子历史 API 异常: {e}")
        return jsonify({"error": str(e)}), 500


@factor_bp.route("/detail")
def detail():
    """获取单只股票维度贡献分解

    Query params:
        symbol: 600036.SSE
        date: YYYY-MM-DD
    """
    symbol = request.args.get("symbol", "")
    query_date = request.args.get("date", "")

    if not symbol:
        return jsonify({"error": "缺少 symbol 参数"}), 400

    try:
        engine = get_engine()
        if engine is None:
            return jsonify({"message": "Tushare Token 未配置"})

        latest = engine.get_latest_snapshot([symbol])
        if latest.is_empty() or len(latest) == 0:
            return jsonify({"message": "无数据"})

        row = latest.row(0, named=True)

        # 构建维度贡献分解
        detail = {
            "symbol": symbol,
            "date": str(row.get("trade_date", "")),
            "pe_ttm": row.get("pe_ttm"),
            "pb": row.get("pb"),
            "ps_ttm": row.get("ps_ttm"),
        }

        return jsonify({"data": detail})
    except Exception as e:
        logger.error(f"因子详情 API 异常: {e}")
        return jsonify({"error": str(e)}), 500
