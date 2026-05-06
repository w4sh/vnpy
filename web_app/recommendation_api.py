"""投资组合推荐 API"""

from __future__ import annotations

import logging
from datetime import date, datetime

from flask import Blueprint, jsonify, request

from web_app.models import (
    PortfolioRecommendation,
    get_db_session,
)
from web_app.recommendation_engine import generate_recommendations

logger = logging.getLogger(__name__)

recommendation_bp = Blueprint("recommendations", __name__)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _rec_to_dict(r: PortfolioRecommendation) -> dict:
    """将模型对象转为 JSON 兼容的字典"""
    return {
        "symbol": r.symbol,
        "name": r.name or r.symbol,
        "recommendation_type": r.recommendation_type,
        "combined_score": float(r.combined_score) if r.combined_score else 0,
        "current_price": float(r.current_price) if r.current_price else 0,
        "target_position_pct": float(r.target_position_pct)
        if r.target_position_pct
        else 0,
        "target_amount": float(r.target_amount) if r.target_amount else 0,
        "current_quantity": r.current_quantity or 0,
        "suggested_quantity": r.suggested_quantity or 0,
        "is_held": bool(r.is_held),
        "position_id": r.position_id,
        "reason": r.reason or "",
    }


def _save_recommendations_to_db(
    results,
    rec_date: date,
    total_capital: float,
    total_market_value: float,
) -> None:
    """持久化推荐结果到数据库"""
    session = get_db_session()
    try:
        # 幂等：先删当日已有推荐
        session.query(PortfolioRecommendation).filter(
            PortfolioRecommendation.recommendation_date == rec_date
        ).delete()

        for r in results:
            rec = PortfolioRecommendation(
                symbol=r.symbol,
                name=r.name,
                recommendation_type=r.recommendation_type,
                combined_score=r.combined_score,
                current_price=r.current_price,
                target_position_pct=r.target_position_pct,
                target_amount=r.target_amount,
                current_quantity=r.current_quantity,
                suggested_quantity=r.suggested_quantity,
                is_held=r.is_held,
                position_id=r.position_id,
                recommendation_date=rec_date,
                reason=r.reason,
            )
            session.add(rec)

        session.commit()
        logger.info("已保存 %d 条推荐到数据库 (date=%s)", len(results), rec_date)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# API 端点
# ---------------------------------------------------------------------------


@recommendation_bp.route("/api/recommendations/generate", methods=["POST"])
def generate():
    """手动触发生成推荐"""
    session = None
    try:
        data = request.get_json(silent=True) or {}
        date_str = data.get("date")

        if date_str:
            rec_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            rec_date = date.today()

        session = get_db_session()
        results = generate_recommendations(session, rec_date)

        # 保存到 DB
        from web_app.models import Strategy

        strategies = session.query(Strategy).filter(Strategy.status == "active").all()
        total_capital = (
            sum(float(s.current_capital or s.initial_capital) for s in strategies)
            if strategies
            else 1_000_000
        )

        from web_app.models import Position

        held_positions = (
            session.query(Position).filter(Position.status == "holding").all()
        )
        total_market_value = sum(float(p.market_value or 0) for p in held_positions)

        _save_recommendations_to_db(
            results, rec_date, total_capital, total_market_value
        )

        # 构建响应
        investable = max(total_capital * (1 - 0.10) - total_market_value, 0.0)

        return jsonify(
            {
                "success": True,
                "recommendation_date": rec_date.isoformat(),
                "summary": {
                    "total_capital": total_capital,
                    "total_market_value": total_market_value,
                    "available_investable": investable,
                    "cash_reserve": total_capital * 0.10,
                },
                "recommendations": [_rec_to_dict(r) for r in results],
            }
        )
    except Exception as e:
        logger.error("生成推荐失败: %s", e)
        return jsonify({"success": False, "error": str(e)})
    finally:
        if session:
            session.close()


@recommendation_bp.route("/api/recommendations/latest")
def get_latest():
    """获取最新的推荐结果"""
    session = None
    try:
        session = get_db_session()

        latest_date = (
            session.query(PortfolioRecommendation.recommendation_date)
            .order_by(PortfolioRecommendation.recommendation_date.desc())
            .first()
        )

        if not latest_date:
            return jsonify(
                {
                    "success": True,
                    "recommendation_date": None,
                    "recommendations": [],
                    "message": "暂无推荐数据，请先运行候选股筛选和推荐生成",
                }
            )

        rec_date = latest_date[0]
        recs = (
            session.query(PortfolioRecommendation)
            .filter(PortfolioRecommendation.recommendation_date == rec_date)
            .all()
        )

        # 计算资金汇总
        from web_app.models import Position, Strategy

        strategies = session.query(Strategy).filter(Strategy.status == "active").all()
        total_capital = (
            sum(float(s.current_capital or s.initial_capital) for s in strategies)
            if strategies
            else 1_000_000
        )
        held_positions = (
            session.query(Position).filter(Position.status == "holding").all()
        )
        total_market_value = sum(float(p.market_value or 0) for p in held_positions)
        investable = max(total_capital * (1 - 0.10) - total_market_value, 0.0)

        return jsonify(
            {
                "success": True,
                "recommendation_date": rec_date.isoformat(),
                "summary": {
                    "total_capital": total_capital,
                    "total_market_value": total_market_value,
                    "available_investable": investable,
                    "cash_reserve": total_capital * 0.10,
                },
                "recommendations": [_rec_to_dict(r) for r in recs],
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        if session:
            session.close()


@recommendation_bp.route("/api/recommendations/history")
def get_history():
    """按日期查询历史推荐"""
    session = None
    try:
        date_str = request.args.get("date", "")
        session = get_db_session()

        query = session.query(PortfolioRecommendation)

        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            query = query.filter(
                PortfolioRecommendation.recommendation_date == target_date
            )

        recs = query.order_by(PortfolioRecommendation.recommendation_date.desc()).all()

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
