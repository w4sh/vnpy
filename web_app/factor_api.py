"""
前瞻因子 Web API

提供 4 个端点:
  GET /api/factors/snapshot       — 最新因子快照（多维基本面评分）
  GET /api/factors/history        — 单只股票因子历史
  GET /api/factors/detail         — 单只股票维度贡献分解
  GET /api/factors/dates          — 可用交易日列表
"""

import logging
from datetime import datetime, timedelta

import polars as pl
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

factor_bp = Blueprint("factors", __name__, url_prefix="/api/factors")


def get_engine():
    """延迟初始化 FactorEngine (导入 Tushare 较慢)

    只注册基本面维度管线。
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
            "both",
            FundamentalFetcher(),
            FundamentalComputer(),
            FundamentalStorage(),
        )
        return engine
    except RuntimeError as e:
        logger.warning(f"FactorEngine 初始化失败: {e}")
        return None


def get_stock_pool():
    """从 StockPoolManager 获取全量A股股票池"""
    try:
        from vnpy.alpha.factors.stock_pool import StockPoolManager

        return StockPoolManager().get_full_pool()
    except ImportError:
        try:
            from web_app.candidate.engine import STOCK_POOL

            return STOCK_POOL
        except ImportError:
            return []


def _compute_momentum_60d(
    symbols: list[str],
    snapshot_df: pl.DataFrame,
    storage,
) -> pl.DataFrame:
    """计算 60 日涨跌幅动量因子

    从 daily parquet 中加载每个股票过去 60 个交易日的 close 价格，
    计算 (最新价 / 60日前价格 - 1)。
    若数据不足 60 个交易日，用可用天数计算。
    """
    if "close" not in snapshot_df.columns:
        logger.warning("快照无 close 列，跳过动量计算")
        return snapshot_df.with_columns(pl.lit(None).alias("momentum_60d"))

    today_str = (
        snapshot_df["trade_date"].max() if "trade_date" in snapshot_df.columns else None
    )
    if not today_str:
        return snapshot_df.with_columns(pl.lit(None).alias("momentum_60d"))

    end = datetime.strptime(today_str, "%Y%m%d")
    start = end - timedelta(days=120)  # 拉 120 天确保够 60 个交易日

    try:
        hist = storage.load(symbols, start, end)
    except FileNotFoundError:
        return snapshot_df.with_columns(pl.lit(None).alias("momentum_60d"))

    if hist.is_empty() or "close" not in hist.columns:
        return snapshot_df.with_columns(pl.lit(None).alias("momentum_60d"))

    # 对每个股票取最新价和 60 个交易日前的价格
    hist_sorted = hist.sort(["vt_symbol", "trade_date"])

    # 对每个股票，取最新 close 和倒数第 60 个交易日的 close
    def _compute_return(group: pl.DataFrame) -> pl.Series:
        prices = group["close"].drop_nulls()
        if len(prices) < 2:
            return pl.Series([None] * len(group))
        current = prices[-1]
        past_idx = min(60, len(prices)) - 1
        past = prices[-(past_idx + 1)]
        if past and past > 0 and current:
            return pl.Series([current / past - 1.0] * len(group))
        return pl.Series([None] * len(group))

    # 对每个股票取最新的 close 和最早的可用的 close
    # 用 drop_nulls() 确保取到非空值
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

    return snapshot_df.join(momentum, on="vt_symbol", how="left")


def _assemble_full_snapshot(
    symbols: list[str],
    snapshot_date: datetime | None = None,
) -> pl.DataFrame | None:
    """组装完整因子快照（日频 + 季频 + 动量）

    返回: 包含所有因子列的 DataFrame，或 None（出错时）
    """
    # 加载日频因子
    from vnpy.alpha.factors.fundamental import FundamentalStorage

    storage = FundamentalStorage()

    if snapshot_date:
        try:
            daily = storage.load(symbols, snapshot_date, snapshot_date)
        except FileNotFoundError:
            return None
    else:
        engine = get_engine()
        if engine is None:
            return None
        daily = engine.get_latest_snapshot(symbols)

    if daily.is_empty():
        return None

    # 加载季频因子（PIT 约束: 只取截至快照日期已公告的数据）
    daily_date = daily["trade_date"].max() if "trade_date" in daily.columns else None
    quarterly = storage.get_latest_quarterly_snapshot(symbols, as_of_date=daily_date)
    if not quarterly.is_empty():
        daily = daily.join(quarterly, on="vt_symbol", how="left")

    # 计算动量
    daily = _compute_momentum_60d(symbols, daily, storage)

    return daily


@factor_bp.route("/snapshot")
def snapshot():
    """获取因子快照（多维基本面评分）

    Query params:
        date: 可选，指定日期 YYYY-MM-DD，默认最新
        sort: 排序字段，默认 final_score
    """
    from web_app.stock_names import get_stock_name

    try:
        target_date = request.args.get("date", "").strip()
        symbols = get_stock_pool()
        if not symbols:
            return jsonify({"error": "无可用股票池"}), 500

        # 1. 组装因子数据
        if target_date:
            try:
                target_dt = datetime.strptime(target_date, "%Y-%m-%d")
            except ValueError:
                return jsonify({"error": "日期格式错误，请使用 YYYY-MM-DD"}), 400
            snapshot_df = _assemble_full_snapshot(symbols, target_dt)
        else:
            snapshot_df = _assemble_full_snapshot(symbols)

        if snapshot_df is None or snapshot_df.is_empty():
            date_info = target_date or "最新"
            return jsonify(
                {
                    "count": 0,
                    "data": [],
                    "message": f"日期 {date_info} 无因子数据",
                }
            )

        # 2. 多维评分
        from vnpy.alpha.factors.scoring import compute_multi_dimension_scores

        scored = compute_multi_dimension_scores(snapshot_df)
        if scored.is_empty():
            return jsonify({"count": 0, "data": [], "message": "评分计算失败"})

        sort_col = request.args.get("sort", "final_score")
        if sort_col in scored.columns:
            scored = scored.sort(sort_col, descending=True)

        result = scored.head(50).to_dicts()
        # 补充股票中文名称
        for row in result:
            vt = row.get("vt_symbol", "")
            if vt:
                row["name"] = get_stock_name(vt)

        fields = [
            "vt_symbol",
            "name",
            "industry",
            "valuation_score",
            "quality_score",
            "growth_score",
            "momentum_score",
            "final_score",
            "pe_ttm",
            "pb",
            "ps_ttm",
            "roe",
            "gross_margin",
            "debt_to_assets",
            "revenue_yoy_growth",
            "net_profit_yoy_growth",
            "momentum_60d",
        ]
        cleaned = []
        for row in result:
            cleaned.append({k: row.get(k) for k in fields if k in row})

        return jsonify({"count": len(cleaned), "data": cleaned})
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
        date: YYYY-MM-DD（可选，默认最新）
    """
    symbol = request.args.get("symbol", "")
    date_str = request.args.get("date", "").strip()

    if not symbol:
        return jsonify({"error": "缺少 symbol 参数"}), 400

    try:
        if date_str:
            try:
                target_dt = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                return jsonify({"error": "日期格式错误，请使用 YYYY-MM-DD"}), 400
            full = _assemble_full_snapshot([symbol], target_dt)
        else:
            full = _assemble_full_snapshot([symbol])

        if full is None or full.is_empty():
            return jsonify({"message": "无数据"})

        # 多维评分
        from vnpy.alpha.factors.scoring import compute_multi_dimension_scores

        scored = compute_multi_dimension_scores(full)
        if scored.is_empty():
            return jsonify({"message": "评分计算失败"})

        row = scored.row(0, named=True)
        detail = {
            "symbol": symbol,
            "date": str(row.get("trade_date", "")),
            "industry": row.get("industry", ""),
            "valuation_score": row.get("valuation_score"),
            "quality_score": row.get("quality_score"),
            "growth_score": row.get("growth_score"),
            "momentum_score": row.get("momentum_score"),
            "final_score": row.get("final_score"),
            "pe_ttm": row.get("pe_ttm"),
            "pb": row.get("pb"),
            "ps_ttm": row.get("ps_ttm"),
            "roe": row.get("roe"),
            "gross_margin": row.get("gross_margin"),
            "debt_to_assets": row.get("debt_to_assets"),
            "revenue_yoy_growth": row.get("revenue_yoy_growth"),
            "net_profit_yoy_growth": row.get("net_profit_yoy_growth"),
        }

        return jsonify({"data": detail})
    except Exception as e:
        logger.error(f"因子详情 API 异常: {e}")
        return jsonify({"error": str(e)}), 500


@factor_bp.route("/dates")
def get_factor_dates():
    """获取日频因子数据中可用的交易日列表

    Returns:
        {success: bool, dates: [str], count: int}
    """
    try:
        from vnpy.alpha.factors.fundamental import FundamentalStorage

        storage = FundamentalStorage()
        dates = storage.get_available_dates()
        # YYYYMMDD → YYYY-MM-DD
        formatted = [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in dates if len(d) == 8]
        return jsonify({"success": True, "dates": formatted, "count": len(formatted)})
    except Exception as e:
        logger.error(f"获取因子日期列表失败: {e}")
        return jsonify({"success": False, "dates": [], "count": 0})
