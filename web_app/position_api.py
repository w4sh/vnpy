#!/usr/bin/env python3
"""
持仓管理API蓝图
提供持仓、策略、交易记录的CRUD接口
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
from web_app.models import (
    Position,
    Strategy,
    Transaction,
    RiskMetric,
    TransactionAuditLog,
    get_db_session,
)
from sqlalchemy.orm import joinedload
from web_app.recalc_service import RecalculationService
import logging

logger = logging.getLogger(__name__)

# 创建蓝图
position_bp = Blueprint("positions", __name__, url_prefix="/api")


# ==================== 持仓管理接口 ====================


@position_bp.route("/positions", methods=["GET"])
def get_positions():
    """获取所有持仓列表"""
    try:
        session = get_db_session()
        try:
            # 支持筛选参数
            status_filter = request.args.get("status", "holding")
            strategy_id = request.args.get("strategy_id", type=int)

            query = session.query(Position).options(joinedload(Position.strategy))

            if status_filter:
                query = query.filter(Position.status == status_filter)
            if strategy_id:
                query = query.filter(Position.strategy_id == strategy_id)

            positions = query.order_by(Position.created_at.desc()).all()

            # 转换为字典格式
            result = []
            for pos in positions:
                pos_dict = {
                    "id": pos.id,
                    "symbol": pos.symbol,
                    "name": pos.name,
                    "quantity": pos.quantity,
                    "cost_price": float(pos.cost_price) if pos.cost_price else 0,
                    "current_price": float(pos.current_price)
                    if pos.current_price
                    else 0,
                    "market_value": float(pos.market_value) if pos.market_value else 0,
                    "profit_loss": float(pos.profit_loss) if pos.profit_loss else 0,
                    "profit_loss_pct": float(pos.profit_loss_pct)
                    if pos.profit_loss_pct
                    else 0,
                    "strategy_id": pos.strategy_id,
                    "strategy_name": pos.strategy.name if pos.strategy else None,
                    "buy_date": pos.buy_date.isoformat() if pos.buy_date else None,
                    "status": pos.status,
                    "stop_loss": float(pos.stop_loss) if pos.stop_loss else None,
                    "take_profit": float(pos.take_profit) if pos.take_profit else None,
                    "notes": pos.notes,
                    "created_at": pos.created_at.isoformat()
                    if pos.created_at
                    else None,
                    "updated_at": pos.updated_at.isoformat()
                    if pos.updated_at
                    else None,
                }
                result.append(pos_dict)

            return jsonify({"success": True, "positions": result})

        finally:
            session.close()

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@position_bp.route("/positions", methods=["POST"])
def create_position():
    """新增持仓"""
    try:
        data = request.json
        session = get_db_session()
        try:
            position = Position(
                symbol=data.get("symbol"),
                name=data.get("name"),
                quantity=int(data.get("quantity", 0)),
                cost_price=float(data.get("cost_price", 0)),
                current_price=float(
                    data.get("current_price", data.get("cost_price", 0))
                ),
                strategy_id=data.get("strategy_id"),
                buy_date=datetime.strptime(data.get("buy_date"), "%Y-%m-%d").date()
                if data.get("buy_date")
                else datetime.now().date(),
                stop_loss=float(data.get("stop_loss"))
                if data.get("stop_loss")
                else None,
                take_profit=float(data.get("take_profit"))
                if data.get("take_profit")
                else None,
                notes=data.get("notes", ""),
            )

            # 计算初始值
            position.market_value = position.quantity * position.current_price
            position.profit_loss = (
                position.current_price - position.cost_price
            ) * position.quantity
            position.profit_loss_pct = (
                ((position.current_price - position.cost_price) / position.cost_price)
                * 100
                if position.cost_price > 0
                else 0
            )

            session.add(position)
            session.commit()

            return jsonify(
                {
                    "success": True,
                    "message": "持仓创建成功",
                    "position": {"id": position.id, "symbol": position.symbol},
                }
            )

        except Exception as e:
            session.rollback()
            return jsonify({"success": False, "error": str(e)}), 400
        finally:
            session.close()

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@position_bp.route("/positions/<int:position_id>", methods=["PUT"])
def update_position(position_id):
    """修改持仓"""
    try:
        data = request.json
        session = get_db_session()
        try:
            position = session.query(Position).get(position_id)
            if not position:
                return jsonify({"success": False, "error": "持仓不存在"}), 404

            # 更新字段
            if "quantity" in data:
                position.quantity = int(data["quantity"])
            if "cost_price" in data:
                position.cost_price = float(data["cost_price"])
            if "current_price" in data:
                position.current_price = float(data["current_price"])
            if "stop_loss" in data:
                position.stop_loss = (
                    float(data["stop_loss"]) if data.get("stop_loss") else None
                )
            if "take_profit" in data:
                position.take_profit = (
                    float(data["take_profit"]) if data.get("take_profit") else None
                )
            if "notes" in data:
                position.notes = data["notes"]
            if "strategy_id" in data:
                position.strategy_id = data["strategy_id"]

            # 重新计算相关字段
            position.market_value = position.quantity * position.current_price
            position.profit_loss = (
                position.current_price - position.cost_price
            ) * position.quantity
            position.profit_loss_pct = (
                ((position.current_price - position.cost_price) / position.cost_price)
                * 100
                if position.cost_price > 0
                else 0
            )

            session.commit()

            return jsonify({"success": True, "message": "持仓更新成功"})

        except Exception as e:
            session.rollback()
            return jsonify({"success": False, "error": str(e)}), 400
        finally:
            session.close()

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@position_bp.route("/positions/<int:position_id>", methods=["DELETE"])
def delete_position(position_id):
    """删除持仓"""
    try:
        session = get_db_session()
        try:
            position = session.query(Position).get(position_id)
            if not position:
                return jsonify({"success": False, "error": "持仓不存在"}), 404

            session.delete(position)
            session.commit()

            return jsonify({"success": True, "message": "持仓删除成功"})

        except Exception as e:
            session.rollback()
            return jsonify({"success": False, "error": str(e)}), 400
        finally:
            session.close()

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 策略管理接口 ====================


@position_bp.route("/strategies", methods=["GET"])
def get_strategies():
    """获取所有策略列表"""
    try:
        session = get_db_session()
        try:
            strategies = (
                session.query(Strategy)
                .filter_by(status="active")
                .order_by(Strategy.created_at.desc())
                .all()
            )

            result = []
            for strategy in strategies:
                strategy_dict = {
                    "id": strategy.id,
                    "name": strategy.name,
                    "description": strategy.description,
                    "initial_capital": float(strategy.initial_capital)
                    if strategy.initial_capital
                    else 0,
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
                    "position_count": len(strategy.positions),
                    "created_at": strategy.created_at.isoformat()
                    if strategy.created_at
                    else None,
                    "updated_at": strategy.updated_at.isoformat()
                    if strategy.updated_at
                    else None,
                }
                result.append(strategy_dict)

            return jsonify({"success": True, "strategies": result})

        finally:
            session.close()

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@position_bp.route("/strategies", methods=["POST"])
def create_strategy():
    """创建新策略"""
    try:
        data = request.json
        session = get_db_session()
        try:
            strategy = Strategy(
                name=data.get("name"),
                description=data.get("description", ""),
                initial_capital=float(data.get("initial_capital", 1000000)),
                current_capital=float(data.get("initial_capital", 1000000)),
                risk_level=data.get("risk_level", "中等"),
            )

            session.add(strategy)
            session.commit()

            return jsonify(
                {
                    "success": True,
                    "message": "策略创建成功",
                    "strategy": {"id": strategy.id, "name": strategy.name},
                }
            )

        except Exception as e:
            session.rollback()
            return jsonify({"success": False, "error": str(e)}), 400
        finally:
            session.close()

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 交易记录接口 ====================


@position_bp.route("/transactions", methods=["GET"])
def get_transactions():
    """获取交易记录列表"""
    try:
        session = get_db_session()
        try:
            # 支持筛选参数
            position_id = request.args.get("position_id", type=int)
            strategy_id = request.args.get("strategy_id", type=int)
            transaction_type = request.args.get("transaction_type")

            query = session.query(Transaction).options(
                joinedload(Transaction.position), joinedload(Transaction.strategy)
            )

            if position_id:
                query = query.filter(Transaction.position_id == position_id)
            if strategy_id:
                query = query.filter(Transaction.strategy_id == strategy_id)
            if transaction_type:
                query = query.filter(Transaction.transaction_type == transaction_type)

            transactions = query.order_by(Transaction.transaction_date.desc()).all()

            result = []
            for txn in transactions:
                txn_dict = {
                    "id": txn.id,
                    "position_id": txn.position_id,
                    "strategy_id": txn.strategy_id,
                    "transaction_type": txn.transaction_type,
                    "symbol": txn.symbol,
                    "quantity": txn.quantity,
                    "price": float(txn.price),
                    "amount": float(txn.amount),
                    "fee": float(txn.fee) if txn.fee else 0,
                    "transaction_date": txn.transaction_date.isoformat()
                    if txn.transaction_date
                    else None,
                    "notes": txn.notes,
                    "created_at": txn.created_at.isoformat()
                    if txn.created_at
                    else None,
                }
                result.append(txn_dict)

            return jsonify({"success": True, "transactions": result})

        finally:
            session.close()

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@position_bp.route("/transactions", methods=["POST"])
def create_transaction():
    """记录新交易"""
    try:
        data = request.json
        session = get_db_session()
        try:
            transaction = Transaction(
                position_id=int(data.get("position_id")),
                strategy_id=data.get("strategy_id"),
                transaction_type=data.get("transaction_type"),
                symbol=data.get("symbol"),
                quantity=int(data.get("quantity", 0)),
                price=float(data.get("price", 0)),
                amount=float(data.get("amount", 0)),
                fee=float(data.get("fee", 0)),
                transaction_date=datetime.strptime(
                    data.get("transaction_date"), "%Y-%m-%d"
                ).date(),
                notes=data.get("notes", ""),
            )

            session.add(transaction)
            session.commit()

            return jsonify(
                {
                    "success": True,
                    "message": "交易记录成功",
                    "transaction": {"id": transaction.id},
                }
            )

        except Exception as e:
            session.rollback()
            return jsonify({"success": False, "error": str(e)}), 400
        finally:
            session.close()

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@position_bp.route("/transactions/<int:transaction_id>", methods=["PUT"])
def update_transaction(transaction_id):
    """修改交易记录

    请求体:
    {
        "price": 38.50,
        "quantity": 1000,
        "fee": 5.0,
        "reason": "价格录入错误"  # 必填
    }
    """
    session = get_db_session()
    try:
        transaction = session.query(Transaction).get(transaction_id)
        if not transaction:
            return jsonify({"error": "交易记录不存在"}), 404

        # 检查关联策略状态（Task 3软删除一致性）
        strategy = session.query(Strategy).get(transaction.strategy_id)
        if not strategy or strategy.status == "deleted":
            return jsonify({"error": "关联策略不存在或已删除"}), 400

        # 检查关联持仓是否存在
        if transaction.position_id:
            position = session.query(Position).get(transaction.position_id)
            if not position:
                return jsonify({"error": "关联持仓不存在"}), 400

        data = request.get_json()
        if not data:
            return jsonify({"error": "请求体不能为空"}), 400

        # reason字段必填
        if "reason" not in data or not data["reason"]:
            return jsonify({"error": "必须提供修改原因"}), 400

        # 记录原始值
        old_values = {}
        changes = []

        # 更新价格
        if "price" in data:
            if data["price"] <= 0:
                return jsonify({"error": "价格必须大于0"}), 400
            old_values["price"] = transaction.price
            transaction.price = data["price"]
            changes.append("price")

        # 更新数量
        if "quantity" in data:
            if data["quantity"] <= 0:
                return jsonify({"error": "数量必须大于0"}), 400
            old_values["quantity"] = transaction.quantity
            transaction.quantity = data["quantity"]
            changes.append("quantity")

        # 更新手续费
        if "fee" in data:
            if data["fee"] < 0:
                return jsonify({"error": "手续费不能为负数"}), 400
            old_values["fee"] = transaction.fee
            transaction.fee = data["fee"]
            changes.append("fee")

        if not changes:
            return jsonify({"error": "没有需要更新的字段"}), 400

        # 重新计算金额
        if "price" in data or "quantity" in data:
            transaction.amount = transaction.quantity * transaction.price
            if transaction.transaction_type == "sell":
                transaction.amount -= transaction.fee

        # 记录审计日志
        for field in changes:
            audit_log = TransactionAuditLog(
                transaction_id=transaction_id,
                field_name=field,
                old_value=str(old_values.get(field, "")),
                new_value=str(data[field]),
                change_reason=data["reason"],
                changed_at=datetime.now(),
            )
            session.add(audit_log)

        transaction.updated_at = datetime.now()

        # 标记策略为dirty（需要重算）
        recalc_service = RecalculationService(session)
        recalc_service.mark_strategy_dirty(transaction.strategy_id)

        session.commit()

        logger.info(
            f"交易{transaction_id}修改成功,策略{transaction.strategy_id}标记为dirty"
        )

        return jsonify(
            {
                "id": transaction.id,
                "symbol": transaction.symbol,
                "transaction_type": transaction.transaction_type,
                "quantity": transaction.quantity,
                "price": float(transaction.price),
                "amount": float(transaction.amount),
                "fee": float(transaction.fee) if transaction.fee else 0,
                "updated_at": transaction.updated_at.isoformat(),
            }
        )

    except Exception as e:
        session.rollback()
        logger.error(f"修改交易{transaction_id}失败: {e}")
        return jsonify({"error": f"修改失败: {str(e)}"}), 500
    finally:
        session.close()


@position_bp.route("/transactions/<int:transaction_id>/audit", methods=["GET"])
def get_transaction_audit_log(transaction_id):
    """获取交易记录的审计日志"""
    session = get_db_session()
    try:
        transaction = session.query(Transaction).get(transaction_id)
        if not transaction:
            return jsonify({"error": "交易记录不存在"}), 404

        audit_logs = (
            session.query(TransactionAuditLog)
            .filter_by(transaction_id=transaction_id)
            .order_by(TransactionAuditLog.changed_at.desc())
            .all()
        )

        return jsonify(
            [
                {
                    "id": log.id,
                    "field_name": log.field_name,
                    "old_value": log.old_value,
                    "new_value": log.new_value,
                    "change_reason": log.change_reason,
                    "changed_at": log.changed_at.isoformat(),
                }
                for log in audit_logs
            ]
        )

    except Exception as e:
        logger.error(f"获取审计日志失败: {e}")
        return jsonify({"error": f"获取失败: {str(e)}"}), 500
    finally:
        session.close()
