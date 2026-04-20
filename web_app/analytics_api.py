#!/usr/bin/env python3
"""
数据分析API蓝图
提供投资组合统计、策略分析、风险计算等高级分析功能
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from web_app.models import Position, Strategy, Transaction, get_db_session
from sqlalchemy.orm import joinedload
from sqlalchemy import func
import numpy as np

# 创建蓝图
analytics_bp = Blueprint("analytics", __name__, url_prefix="/api/analytics")


# ==================== 投资组合分析接口 ====================


@analytics_bp.route("/portfolio", methods=["GET"])
def get_portfolio_analytics():
    """获取投资组合详细分析"""
    try:
        session = get_db_session()
        try:
            # 获取所有持仓
            positions = (
                session.query(Position).filter(Position.status == "holding").all()
            )

            if not positions:
                return jsonify({"success": True, "analytics": {}})

            # 基础统计
            total_assets = sum(float(p.market_value or 0) for p in positions)
            total_cost = sum(float(p.cost_price or 0) * p.quantity for p in positions)
            total_profit = sum(float(p.profit_loss or 0) for p in positions)
            total_profit_pct = (
                (total_profit / total_cost * 100) if total_cost > 0 else 0
            )

            # 持仓分布
            position_distribution = []
            for p in positions:
                position_distribution.append(
                    {
                        "symbol": p.symbol,
                        "name": p.name,
                        "market_value": float(p.market_value or 0),
                        "weight": (
                            (float(p.market_value or 0) / total_assets * 100)
                            if total_assets > 0
                            else 0
                        ),
                        "profit_loss": float(p.profit_loss or 0),
                        "profit_loss_pct": float(p.profit_loss_pct or 0),
                    }
                )

            # 盈亏分布
            profit_positions = [p for p in positions if (p.profit_loss or 0) > 0]
            loss_positions = [p for p in positions if (p.profit_loss or 0) < 0]

            profit_count = len(profit_positions)
            loss_count = len(loss_positions)
            profit_amount = sum(p.profit_loss or 0 for p in profit_positions)
            loss_amount = sum(p.profit_loss or 0 for p in loss_positions)

            # 风险指标
            returns = [float(p.profit_loss_pct or 0) for p in positions]
            volatility = calculate_volatility(returns) if returns else 0

            analytics = {
                "summary": {
                    "total_assets": float(total_assets),
                    "total_cost": float(total_cost),
                    "total_profit": float(total_profit),
                    "total_profit_pct": float(total_profit_pct),
                    "position_count": len(positions),
                },
                "distribution": position_distribution,
                "profit_loss": {
                    "profit_count": profit_count,
                    "loss_count": loss_count,
                    "profit_amount": float(profit_amount),
                    "loss_amount": float(abs(loss_amount)),
                    "win_rate": (profit_count / len(positions) * 100)
                    if positions
                    else 0,
                },
                "risk_metrics": {"volatility": float(volatility)},
            }

            return jsonify({"success": True, "analytics": analytics})

        finally:
            session.close()

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@analytics_bp.route("/strategy/<int:strategy_id>", methods=["GET"])
def get_strategy_analytics(strategy_id):
    """获取策略详细分析"""
    try:
        session = get_db_session()
        try:
            strategy = (
                session.query(Strategy)
                .options(joinedload(Strategy.positions))
                .get(strategy_id)
            )

            if not strategy:
                return jsonify({"success": False, "error": "策略不存在"}), 404

            # 过滤已删除的策略
            if strategy.status == "deleted":
                return jsonify({"success": False, "error": "策略不存在"}), 404

            positions = [p for p in strategy.positions if p.status == "holding"]

            if not positions:
                return jsonify(
                    {
                        "success": True,
                        "analytics": {
                            "strategy_id": strategy_id,
                            "strategy_name": strategy.name,
                            "position_count": 0,
                        },
                    }
                )

            # 策略统计
            total_value = sum(float(p.market_value or 0) for p in positions)
            total_cost = sum(float(p.cost_price or 0) * p.quantity for p in positions)
            total_return = total_value - float(strategy.initial_capital)
            total_return_pct = (
                (total_return / float(strategy.initial_capital) * 100)
                if strategy.initial_capital > 0
                else 0
            )

            # 持仓表现
            position_performance = []
            for p in positions:
                position_performance.append(
                    {
                        "symbol": p.symbol,
                        "name": p.name,
                        "quantity": p.quantity,
                        "cost_price": float(p.cost_price),
                        "current_price": float(p.current_price or 0),
                        "profit_loss": float(p.profit_loss or 0),
                        "profit_loss_pct": float(p.profit_loss_pct or 0),
                        "weight": (
                            (float(p.market_value or 0) / total_value * 100)
                            if total_value > 0
                            else 0
                        ),
                    }
                )

            analytics = {
                "strategy_id": strategy_id,
                "strategy_name": strategy.name,
                "initial_capital": float(strategy.initial_capital),
                "current_capital": float(strategy.current_capital or 0),
                "total_value": float(total_value),
                "total_return": float(total_return),
                "total_return_pct": float(total_return_pct),
                "position_count": len(positions),
                "position_performance": position_performance,
            }

            return jsonify({"success": True, "analytics": analytics})

        finally:
            session.close()

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@analytics_bp.route("/comparison", methods=["GET"])
def compare_strategies():
    """策略对比分析"""
    try:
        session = get_db_session()
        try:
            # 使用joinedload预加载positions，避免N+1查询
            strategies = (
                session.query(Strategy)
                .options(joinedload(Strategy.positions))
                .filter_by(status="active")
                .order_by(Strategy.created_at.desc())
                .all()
            )

            comparison = []
            for strategy in strategies:
                positions = [p for p in strategy.positions if p.status == "holding"]

                total_value = sum(float(p.market_value or 0) for p in positions)
                total_cost = sum(
                    float(p.cost_price or 0) * p.quantity for p in positions
                )
                total_return = total_value - float(strategy.initial_capital)
                total_return_pct = (
                    (total_return / float(strategy.initial_capital) * 100)
                    if strategy.initial_capital > 0
                    else 0
                )

                # 计算风险指标
                returns = [float(p.profit_loss_pct or 0) for p in positions]
                volatility = calculate_volatility(returns) if len(returns) > 1 else 0

                comparison.append(
                    {
                        "strategy_id": strategy.id,
                        "strategy_name": strategy.name,
                        "initial_capital": float(strategy.initial_capital),
                        "current_value": float(total_value),
                        "total_return": float(total_return),
                        "total_return_pct": float(total_return_pct),
                        "position_count": len(positions),
                        "volatility": float(volatility),
                        "risk_level": strategy.risk_level,
                    }
                )

            return jsonify({"success": True, "comparison": comparison})

        finally:
            session.close()

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@analytics_bp.route("/risk/metrics", methods=["GET"])
def calculate_risk_metrics():
    """计算投资组合风险指标"""
    try:
        session = get_db_session()
        try:
            positions = (
                session.query(Position).filter(Position.status == "holding").all()
            )

            if not positions or len(positions) < 2:
                return jsonify(
                    {
                        "success": True,
                        "metrics": {"message": "需要至少2个持仓来计算风险指标"},
                    }
                )

            # 收益率数据
            returns = [float(p.profit_loss_pct or 0) for p in positions]

            # 计算各种风险指标
            metrics = {
                "volatility": float(calculate_volatility(returns)),
                "var_95": float(calculate_var(returns, 0.95)),
                "var_99": float(calculate_var(returns, 0.99)),
                "max_drawdown": float(calculate_max_drawdown(positions)),
                "sharpe_ratio": float(calculate_sharpe_ratio(positions)),
                "concentration": float(calculate_concentration(positions)),
            }

            return jsonify({"success": True, "metrics": metrics})

        finally:
            session.close()

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@analytics_bp.route("/export", methods=["GET"])
def export_data():
    """导出数据（JSON格式）"""
    try:
        session = get_db_session()
        try:
            # 获取所有数据
            positions = session.query(Position).all()
            strategies = session.query(Strategy).all()
            transactions = session.query(Transaction).all()

            export_data = {
                "export_date": datetime.now().isoformat(),
                "positions": [
                    {
                        "id": p.id,
                        "symbol": p.symbol,
                        "name": p.name,
                        "quantity": p.quantity,
                        "cost_price": float(p.cost_price),
                        "current_price": float(p.current_price)
                        if p.current_price
                        else None,
                        "market_value": float(p.market_value)
                        if p.market_value
                        else None,
                        "profit_loss": float(p.profit_loss) if p.profit_loss else None,
                        "profit_loss_pct": float(p.profit_loss_pct)
                        if p.profit_loss_pct
                        else None,
                        "buy_date": p.buy_date.isoformat() if p.buy_date else None,
                        "status": p.status,
                    }
                    for p in positions
                ],
                "strategies": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "description": s.description,
                        "initial_capital": float(s.initial_capital),
                        "current_capital": float(s.current_capital)
                        if s.current_capital
                        else None,
                        "risk_level": s.risk_level,
                    }
                    for s in strategies
                ],
                "transactions": [
                    {
                        "id": t.id,
                        "symbol": t.symbol,
                        "transaction_type": t.transaction_type,
                        "quantity": t.quantity,
                        "price": float(t.price),
                        "amount": float(t.amount),
                        "transaction_date": t.transaction_date.isoformat()
                        if t.transaction_date
                        else None,
                    }
                    for t in transactions
                ],
            }

            return jsonify({"success": True, "data": export_data})

        finally:
            session.close()

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 辅助计算函数 ====================


def calculate_volatility(returns):
    """计算波动率（标准差）"""
    if len(returns) < 2:
        return 0
    return float(np.std(returns))


def calculate_var(returns, confidence=0.95):
    """计算风险价值（VaR）"""
    if not returns:
        return 0
    return float(np.percentile(returns, (1 - confidence) * 100))


def calculate_max_drawdown(positions):
    """计算最大回撤"""
    if not positions:
        return 0

    # 计算累计收益曲线
    cumulative_returns = []
    cumulative = 0
    for p in positions:
        cumulative += p.profit_loss or 0
        cumulative_returns.append(cumulative)

    if len(cumulative_returns) < 2:
        return 0

    # 计算最大回撤
    peak = cumulative_returns[0]
    max_dd = 0
    for value in cumulative_returns:
        if value > peak:
            peak = value
        dd = (peak - value) / peak if peak != 0 else 0
        if dd > max_dd:
            max_dd = dd

    return float(max_dd * 100)  # 转换为百分比


def calculate_sharpe_ratio(positions, risk_free_rate=0.03):
    """计算夏普比率"""
    if not positions or len(positions) < 2:
        return 0

    returns = [float(p.profit_loss_pct or 0) for p in positions]
    avg_return = np.mean(returns)
    volatility = np.std(returns)

    if volatility == 0:
        return 0

    # 年化夏普比率
    sharpe = (avg_return - risk_free_rate) / volatility
    return float(sharpe)


def calculate_concentration(positions):
    """计算集中度（赫芬达尔指数）"""
    if not positions:
        return 0

    # 计算持仓市值占比
    total_value = sum(p.market_value or 0 for p in positions)
    if total_value == 0:
        return 0

    weights = [(p.market_value or 0) / total_value for p in positions]

    # 赫芬达尔指数
    hhi = sum(w**2 for w in weights)
    return float(hhi * 100)  # 转换为百分比
