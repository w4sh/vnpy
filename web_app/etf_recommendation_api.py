"""ETF 推荐 API"""

from __future__ import annotations

import logging
from datetime import date, datetime

from flask import Blueprint, jsonify, request

from web_app.etf.etf_screening_engine import run_etf_screening
from web_app.etf_recommendation_engine import generate_etf_recommendations
from web_app.models import EtfCandidate, EtfPortfolioRecommendation, get_db_session

logger = logging.getLogger(__name__)

etf_recommendation_bp = Blueprint("etf_recommendations", __name__)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _candidate_to_dict(c: EtfCandidate) -> dict:
    return {
        "ts_code": c.ts_code,
        "name": c.name or c.ts_code,
        "rank": c.rank,
        "combined_score": float(c.combined_score) if c.combined_score else 0,
        "liquidity_score": float(c.liquidity_score) if c.liquidity_score else 0,
        "size_score": float(c.size_score) if c.size_score else 0,
        "cost_score": float(c.cost_score) if c.cost_score else 0,
        "momentum_score": float(c.momentum_score) if c.momentum_score else 0,
        "volatility_score": float(c.volatility_score) if c.volatility_score else 0,
        "yield_score": float(c.yield_score) if c.yield_score else 0,
        "technical_score": float(c.technical_score) if c.technical_score else 0,
        "performance_score": float(c.performance_score) if c.performance_score else 0,
        "current_price": float(c.current_price) if c.current_price else 0,
        "fund_size": float(c.fund_size) if c.fund_size else 0,
        "expense_ratio": float(c.expense_ratio) if c.expense_ratio else 0,
        "total_return": float(c.total_return) if c.total_return else 0,
        "sharpe_ratio": float(c.sharpe_ratio) if c.sharpe_ratio else 0,
    }


def _rec_to_dict(r: EtfPortfolioRecommendation) -> dict:
    return {
        "ts_code": r.ts_code,
        "name": r.name or r.ts_code,
        "recommendation_type": r.recommendation_type,
        "combined_score": float(r.combined_score) if r.combined_score else 0,
        "current_price": float(r.current_price) if r.current_price else 0,
        "target_position_pct": float(r.target_position_pct)
        if r.target_position_pct
        else 0,
        "target_amount": float(r.target_amount) if r.target_amount else 0,
        "suggested_quantity": r.suggested_quantity or 0,
        "reason": r.reason or "",
    }


def _save_recommendations_to_db(results, rec_date: date) -> None:
    """持久化 ETF 推荐结果到数据库"""
    session = get_db_session()
    try:
        session.query(EtfPortfolioRecommendation).filter(
            EtfPortfolioRecommendation.recommendation_date == rec_date
        ).delete()

        for r in results:
            rec = EtfPortfolioRecommendation(
                ts_code=r.ts_code,
                name=r.name,
                recommendation_type=r.recommendation_type,
                combined_score=r.combined_score,
                current_price=r.current_price,
                target_position_pct=r.target_position_pct,
                target_amount=r.target_amount,
                suggested_quantity=r.suggested_quantity,
                recommendation_date=rec_date,
                reason=r.reason,
            )
            session.add(rec)

        session.commit()
        logger.info("已保存 %d 条 ETF 推荐到数据库 (date=%s)", len(results), rec_date)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# API 端点
# ---------------------------------------------------------------------------


@etf_recommendation_bp.route("/api/etf/recommendations/generate", methods=["POST"])
def generate():
    """手动触发 ETF 筛选 + 推荐"""
    try:
        data = request.get_json(silent=True) or {}
        date_str = data.get("date")

        if date_str:
            rec_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            rec_date = date.today()

        # 1. 执行筛选
        results, pool_size, elapsed = run_etf_screening(
            trade_date=rec_date.strftime("%Y%m%d")
        )

        # 2. 生成推荐
        session = get_db_session()
        try:
            recs = generate_etf_recommendations(session, rec_date)
            _save_recommendations_to_db(recs, rec_date)

            return jsonify(
                {
                    "success": True,
                    "recommendation_date": rec_date.isoformat(),
                    "screening": {
                        "pool_size": pool_size,
                        "candidates_count": len(results),
                        "elapsed": elapsed,
                    },
                    "recommendations": [r.to_dict() for r in recs],
                }
            )
        finally:
            session.close()

    except Exception as e:
        logger.error("ETF 推荐生成失败: %s", e)
        return jsonify({"success": False, "error": str(e)})


@etf_recommendation_bp.route("/api/etf/recommendations/latest")
def get_latest():
    """获取最新 ETF 推荐结果"""
    session = None
    try:
        session = get_db_session()

        latest_date = (
            session.query(EtfPortfolioRecommendation.recommendation_date)
            .order_by(EtfPortfolioRecommendation.recommendation_date.desc())
            .first()
        )

        if not latest_date:
            return jsonify(
                {
                    "success": True,
                    "recommendation_date": None,
                    "recommendations": [],
                    "message": "暂无 ETF 推荐数据，请先运行筛选",
                }
            )

        rec_date = latest_date[0]
        recs = (
            session.query(EtfPortfolioRecommendation)
            .filter(EtfPortfolioRecommendation.recommendation_date == rec_date)
            .all()
        )

        return jsonify(
            {
                "success": True,
                "recommendation_date": rec_date.isoformat(),
                "recommendations": [_rec_to_dict(r) for r in recs],
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        if session:
            session.close()


@etf_recommendation_bp.route("/api/etf/recommendations/history")
def get_history():
    """按日期查询历史 ETF 推荐"""
    session = None
    try:
        date_str = request.args.get("date", "")
        session = get_db_session()

        query = session.query(EtfPortfolioRecommendation)

        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            query = query.filter(
                EtfPortfolioRecommendation.recommendation_date == target_date
            )

        recs = query.order_by(
            EtfPortfolioRecommendation.recommendation_date.desc()
        ).all()

        results_by_date: dict = {}
        for r in recs:
            d = r.recommendation_date.isoformat()
            if d not in results_by_date:
                results_by_date[d] = []
            results_by_date[d].append(_rec_to_dict(r))

        return jsonify({"success": True, "results": results_by_date})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        if session:
            session.close()


@etf_recommendation_bp.route("/api/etf/candidates/latest")
def get_latest_candidates():
    """获取最新 ETF 评分排名"""
    session = None
    try:
        session = get_db_session()

        latest_date_row = (
            session.query(EtfCandidate.screening_date)
            .order_by(EtfCandidate.screening_date.desc())
            .first()
        )

        if not latest_date_row:
            return jsonify(
                {
                    "success": True,
                    "screening_date": None,
                    "candidates": [],
                    "message": "暂无 ETF 数据，请先运行筛选",
                }
            )

        screening_date = latest_date_row[0]
        candidates = (
            session.query(EtfCandidate)
            .filter(EtfCandidate.screening_date == screening_date)
            .order_by(EtfCandidate.rank)
            .all()
        )

        return jsonify(
            {
                "success": True,
                "screening_date": screening_date.isoformat(),
                "count": len(candidates),
                "candidates": [_candidate_to_dict(c) for c in candidates],
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        if session:
            session.close()
