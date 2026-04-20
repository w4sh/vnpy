"""策略管理API

提供策略的更新、删除、查询功能:
- PUT /api/strategies/<id> - 更新策略
- DELETE /api/strategies/<id> - 软删除策略
- GET /api/strategies/<id> - 获取策略详情
- GET /api/strategies/<id>/positions - 获取策略持仓
"""

from flask import Blueprint, request, jsonify
from web_app.models import Strategy, StrategyAuditLog, Position, get_db_session
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

strategy_bp = Blueprint("strategies", __name__)


@strategy_bp.route("/api/strategies/<int:strategy_id>", methods=["PUT"])
def update_strategy(strategy_id):
    """更新策略

    请求体:
    {
        "description": "更新后的描述",
        "risk_level": "低"
    }

    不可修改字段: name, initial_capital, total_return, max_drawdown, sharpe_ratio
    """
    session = get_db_session()
    try:
        strategy = session.query(Strategy).get(strategy_id)
        if not strategy:
            return jsonify({"error": "策略不存在"}), 404

        data = request.get_json()
        if not data:
            return jsonify({"error": "请求体不能为空"}), 400

        # 记录原始值(用于审计)
        old_values = {}
        changes = []

        # 更新描述
        if "description" in data:
            old_values["description"] = strategy.description
            strategy.description = data["description"]
            changes.append("description")

        # 更新风险等级
        if "risk_level" in data:
            old_values["risk_level"] = strategy.risk_level
            strategy.risk_level = data["risk_level"]
            changes.append("risk_level")

        # 检查是否尝试修改受保护字段
        protected_fields = [
            "name",
            "initial_capital",
            "total_return",
            "max_drawdown",
            "sharpe_ratio",
        ]
        for field in protected_fields:
            if field in data:
                return jsonify({"error": f"{field}字段不允许修改"}), 400

        if not changes:
            return jsonify({"error": "没有需要更新的字段"}), 400

        # 记录审计日志
        for field in changes:
            audit_log = StrategyAuditLog(
                strategy_id=strategy_id,
                field_name=field,
                old_value=str(old_values.get(field, "")),
                new_value=str(data[field]),
                change_reason=data.get("reason", "策略更新"),
                changed_at=datetime.now(),
            )
            session.add(audit_log)

        strategy.updated_at = datetime.now()
        session.commit()

        logger.info(f"策略{strategy_id}更新成功")

        return jsonify(
            {
                "id": strategy.id,
                "name": strategy.name,
                "description": strategy.description,
                "initial_capital": float(strategy.initial_capital),
                "current_capital": float(strategy.current_capital)
                if strategy.current_capital
                else 0,
                "total_return": float(strategy.total_return)
                if strategy.total_return
                else 0,
                "risk_level": strategy.risk_level,
                "recalc_status": strategy.recalc_status,
                "updated_at": strategy.updated_at.isoformat(),
            }
        )
    except Exception as e:
        session.rollback()
        logger.error(f"更新策略{strategy_id}失败: {e}")
        return jsonify({"error": f"更新失败: {str(e)}"}), 500
    finally:
        session.close()


@strategy_bp.route("/api/strategies/<int:strategy_id>", methods=["DELETE"])
def delete_strategy(strategy_id):
    """软删除策略

    将status设为'deleted'，记录审计日志
    如果策略有活跃持仓(status='holding'),则拒绝删除
    """
    session = get_db_session()
    try:
        strategy = session.query(Strategy).get(strategy_id)
        if not strategy:
            return jsonify({"error": "策略不存在"}), 404

        # 检查是否有关联持仓
        active_positions = (
            session.query(Position)
            .filter_by(strategy_id=strategy_id, status="holding")
            .count()
        )

        if active_positions > 0:
            return jsonify(
                {"error": f"策略有{active_positions}个活跃持仓,无法删除"}
            ), 400

        reason = request.args.get("reason", "用户删除")

        # 记录审计日志
        audit_log = StrategyAuditLog(
            strategy_id=strategy_id,
            field_name="status",
            old_value="active",
            new_value="deleted",
            change_reason=reason,
            changed_at=datetime.now(),
        )
        session.add(audit_log)

        # 软删除：将status设为deleted
        strategy.status = "deleted"
        strategy.updated_at = datetime.now()
        session.commit()

        logger.info(f"策略{strategy_id}已软删除")

        return jsonify(
            {"id": strategy_id, "status": "deleted", "message": "策略已删除"}
        )
    except Exception as e:
        session.rollback()
        logger.error(f"删除策略{strategy_id}失败: {e}")
        return jsonify({"error": f"删除失败: {str(e)}"}), 500
    finally:
        session.close()


@strategy_bp.route("/api/strategies/<int:strategy_id>", methods=["GET"])
def get_strategy(strategy_id):
    """获取策略详情"""
    session = get_db_session()
    try:
        strategy = session.query(Strategy).get(strategy_id)
        if not strategy:
            return jsonify({"error": "策略不存在"}), 404

        # 过滤已删除的策略
        if strategy.status == "deleted":
            return jsonify({"error": "策略不存在"}), 404

        return jsonify(
            {
                "id": strategy.id,
                "name": strategy.name,
                "description": strategy.description,
                "initial_capital": float(strategy.initial_capital),
                "current_capital": float(strategy.current_capital)
                if strategy.current_capital
                else 0,
                "total_return": float(strategy.total_return)
                if strategy.total_return
                else 0,
                "max_drawdown": float(strategy.max_drawdown)
                if strategy.max_drawdown
                else 0,
                "sharpe_ratio": float(strategy.sharpe_ratio)
                if strategy.sharpe_ratio
                else 0,
                "risk_level": strategy.risk_level,
                "recalc_status": strategy.recalc_status,
                "recalc_retry_count": strategy.recalc_retry_count,
                "last_error": strategy.last_error,
                "status": strategy.status,
                "created_at": strategy.created_at.isoformat()
                if strategy.created_at
                else None,
                "updated_at": strategy.updated_at.isoformat()
                if strategy.updated_at
                else None,
            }
        )
    except Exception as e:
        logger.error(f"获取策略{strategy_id}失败: {e}")
        return jsonify({"error": f"获取失败: {str(e)}"}), 500
    finally:
        session.close()


@strategy_bp.route("/api/strategies/<int:strategy_id>/positions", methods=["GET"])
def get_strategy_positions(strategy_id):
    """获取策略的所有持仓"""
    session = get_db_session()
    try:
        strategy = session.query(Strategy).get(strategy_id)
        if not strategy:
            return jsonify({"error": "策略不存在"}), 404

        # 过滤已删除的策略
        if strategy.status == "deleted":
            return jsonify({"error": "策略不存在"}), 404

        positions = (
            session.query(Position)
            .filter_by(strategy_id=strategy_id, status="holding")
            .all()
        )

        return jsonify(
            [
                {
                    "id": p.id,
                    "symbol": p.symbol,
                    "name": p.name,
                    "quantity": p.quantity,
                    "cost_price": float(p.cost_price),
                    "current_price": float(p.current_price) if p.current_price else 0,
                    "market_value": float(p.market_value) if p.market_value else 0,
                    "profit_loss": float(p.profit_loss) if p.profit_loss else 0,
                    "profit_loss_pct": float(p.profit_loss_pct)
                    if p.profit_loss_pct
                    else 0,
                }
                for p in positions
            ]
        )
    except Exception as e:
        logger.error(f"获取策略{strategy_id}持仓失败: {e}")
        return jsonify({"error": f"获取失败: {str(e)}"}), 500
    finally:
        session.close()


@strategy_bp.route("/api/strategies/<int:strategy_id>/restore", methods=["POST"])
def restore_strategy(strategy_id):
    """恢复已删除的策略
    
    将status从'deleted'改回'active'
    """
    session = get_db_session()
    try:
        strategy = session.query(Strategy).get(strategy_id)
        if not strategy:
            return jsonify({"error": "策略不存在"}), 404
        
        # 只能恢复已删除的策略
        if strategy.status != "deleted":
            return jsonify({"error": "只能恢复已删除的策略"}), 400
        
        reason = request.args.get("reason", "用户恢复")
        
        # 记录审计日志
        audit_log = StrategyAuditLog(
            strategy_id=strategy_id,
            field_name="status",
            old_value="deleted",
            new_value="active",
            change_reason=reason,
            changed_at=datetime.now(),
        )
        session.add(audit_log)
        
        # 恢复策略
        strategy.status = "active"
        strategy.updated_at = datetime.now()
        session.commit()
        
        logger.info(f"策略{strategy_id}已恢复")
        
        return jsonify({
            "id": strategy_id,
            "status": "active",
            "message": "策略已恢复"
        })
    except Exception as e:
        session.rollback()
        logger.error(f"恢复策略{strategy_id}失败: {e}")
        return jsonify({"error": f"恢复失败: {str(e)}"}), 500
    finally:
        session.close()
