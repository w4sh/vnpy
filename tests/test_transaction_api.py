"""测试交易记录修改API"""

import pytest
from web_app.models import (
    Transaction,
    TransactionAuditLog,
    Position,
    Strategy,
    Base,
    get_db_session,
)
from web_app.position_api import position_bp
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import date
import tempfile
import os


@pytest.fixture
def app():
    """创建测试Flask应用"""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(position_bp)
    return app


@pytest.fixture
def db_engine():
    """创建测试数据库引擎"""
    # 使用临时文件而不是内存数据库，以支持多个session
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()

    engine = create_engine(f"sqlite:///{temp_db.name}")
    Base.metadata.create_all(engine)
    yield engine

    # 清理临时文件
    os.unlink(temp_db.name)


@pytest.fixture
def db_session_factory(db_engine):
    """创建session工厂"""
    Session = sessionmaker(bind=db_engine)
    return Session


def test_update_transaction_price(app, db_session_factory):
    """测试:修改交易价格"""
    # 创建测试数据
    session = db_session_factory()
    strategy_id = None
    transaction_id = None

    try:
        strategy = Strategy(name="测试", initial_capital=1000000)
        session.add(strategy)
        session.flush()
        strategy_id = strategy.id

        position = Position(
            symbol="000001.SZSE",
            quantity=1000,
            cost_price=10.00,
            strategy_id=strategy.id,
        )
        session.add(position)
        session.flush()

        transaction = Transaction(
            position_id=position.id,
            strategy_id=strategy.id,
            transaction_type="buy",
            symbol="000001.SZSE",
            quantity=1000,
            price=10.00,
            amount=10000,
            transaction_date=date.today(),
        )
        session.add(transaction)
        session.flush()
        transaction_id = transaction.id
        session.commit()

        # Monkey patch get_db_session to use test database
        import web_app.position_api as position_api_module

        original_get_db_session = position_api_module.get_db_session
        position_api_module.get_db_session = lambda: session

        try:
            client = app.test_client()
            response = client.put(
                f"/api/transactions/{transaction_id}",
                json={"price": 15.00, "reason": "价格修正"},
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data["price"] == 15.00

            # 验证策略被标记为dirty
            session.expire_all()
            strategy = session.query(Strategy).get(strategy_id)
            assert strategy.recalc_status == "dirty"

            # 验证审计日志已创建
            audit_logs = (
                session.query(TransactionAuditLog)
                .filter_by(transaction_id=transaction_id)
                .all()
            )
            assert len(audit_logs) == 1
            assert audit_logs[0].field_name == "price"
            assert audit_logs[0].old_value in ["10.0", "10.00"]
            assert audit_logs[0].new_value == "15.0"
        finally:
            # Restore original function
            position_api_module.get_db_session = original_get_db_session

    finally:
        session.close()


def test_update_transaction_requires_reason(app, db_session_factory):
    """测试:修改交易必须提供原因"""
    session = db_session_factory()
    try:
        strategy = Strategy(name="测试", initial_capital=1000000)
        session.add(strategy)
        session.flush()

        position = Position(
            symbol="000001.SZSE",
            quantity=1000,
            cost_price=10.00,
            strategy_id=strategy.id,
        )
        session.add(position)
        session.flush()

        transaction = Transaction(
            position_id=position.id,
            strategy_id=strategy.id,
            transaction_type="buy",
            symbol="000001.SZSE",
            quantity=1000,
            price=10.00,
            amount=10000,
            transaction_date=date.today(),
        )
        session.add(transaction)
        session.commit()

        # Monkey patch get_db_session
        import web_app.position_api as position_api_module

        original_get_db_session = position_api_module.get_db_session
        position_api_module.get_db_session = lambda: session

        try:
            client = app.test_client()
            response = client.put(
                f"/api/transactions/{transaction.id}", json={"price": 15.00}
            )

            assert response.status_code == 400
            assert "必须提供修改原因" in response.get_json()["error"]
        finally:
            position_api_module.get_db_session = original_get_db_session

    finally:
        session.close()


def test_update_transaction_validation(app, db_session_factory):
    """测试:参数验证"""
    session = db_session_factory()
    try:
        strategy = Strategy(name="测试", initial_capital=1000000)
        session.add(strategy)
        session.flush()

        position = Position(
            symbol="000001.SZSE",
            quantity=1000,
            cost_price=10.00,
            strategy_id=strategy.id,
        )
        session.add(position)
        session.flush()

        transaction = Transaction(
            position_id=position.id,
            strategy_id=strategy.id,
            transaction_type="buy",
            symbol="000001.SZSE",
            quantity=1000,
            price=10.00,
            amount=10000,
            transaction_date=date.today(),
        )
        session.add(transaction)
        session.commit()

        # Monkey patch get_db_session
        import web_app.position_api as position_api_module

        original_get_db_session = position_api_module.get_db_session
        position_api_module.get_db_session = lambda: session

        try:
            client = app.test_client()

            # 测试价格<=0
            response = client.put(
                f"/api/transactions/{transaction.id}",
                json={"price": 0, "reason": "测试"},
            )
            assert response.status_code == 400
            assert "价格必须大于0" in response.get_json()["error"]

            # 测试数量<=0
            response = client.put(
                f"/api/transactions/{transaction.id}",
                json={"quantity": 0, "reason": "测试"},
            )
            assert response.status_code == 400
            assert "数量必须大于0" in response.get_json()["error"]

            # 测试手续费<0
            response = client.put(
                f"/api/transactions/{transaction.id}",
                json={"fee": -5.0, "reason": "测试"},
            )
            assert response.status_code == 400
            assert "手续费不能为负数" in response.get_json()["error"]
        finally:
            position_api_module.get_db_session = original_get_db_session

    finally:
        session.close()


def test_get_transaction_audit_log(app, db_session_factory):
    """测试:获取交易审计日志"""
    session = db_session_factory()
    try:
        strategy = Strategy(name="测试", initial_capital=1000000)
        session.add(strategy)
        session.flush()

        position = Position(
            symbol="000001.SZSE",
            quantity=1000,
            cost_price=10.00,
            strategy_id=strategy.id,
        )
        session.add(position)
        session.flush()

        transaction = Transaction(
            position_id=position.id,
            strategy_id=strategy.id,
            transaction_type="buy",
            symbol="000001.SZSE",
            quantity=1000,
            price=10.00,
            amount=10000,
            transaction_date=date.today(),
        )
        session.add(transaction)
        session.commit()

        # Monkey patch get_db_session
        import web_app.position_api as position_api_module

        original_get_db_session = position_api_module.get_db_session
        position_api_module.get_db_session = lambda: session

        try:
            # 修改交易
            client = app.test_client()
            response = client.put(
                f"/api/transactions/{transaction.id}",
                json={"price": 15.00, "reason": "测试修改"},
            )

            # 获取审计日志
            response = client.get(f"/api/transactions/{transaction.id}/audit")

            assert response.status_code == 200
            logs = response.get_json()
            assert len(logs) == 1
            assert logs[0]["field_name"] == "price"
            assert logs[0]["old_value"] in ["10.0", "10.00"]
            assert logs[0]["new_value"] == "15.0"
            assert logs[0]["change_reason"] == "测试修改"
        finally:
            position_api_module.get_db_session = original_get_db_session

    finally:
        session.close()
