"""
测试Phase 2数据库Schema变更
验证新增字段和审计日志表的功能
"""

import pytest
from web_app.models import (
    Strategy,
    Position,
    Transaction,
    DailyProfitLoss,
    Base,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="module")
def db_engine():
    """创建测试数据库引擎"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine


@pytest.fixture
def db_session(db_engine):
    """创建测试会话"""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


def test_position_new_columns(db_session):
    """测试：Position表新字段"""
    position = Position(
        symbol="000001.SZSE",
        quantity=1000,
        cost_price=10.00,
        user_id=1,
        prev_close_price=9.50,
    )
    db_session.add(position)
    db_session.commit()

    assert position.user_id == 1
    assert position.prev_close_price == 9.50


def test_strategy_new_columns(db_session):
    """测试：Strategy表新字段"""
    strategy = Strategy(
        name="测试策略", initial_capital=1000000, user_id=1, recalc_status="clean"
    )
    db_session.add(strategy)
    db_session.commit()

    assert strategy.user_id == 1
    assert strategy.recalc_status == "clean"
    assert strategy.recalc_retry_count == 0


def test_transaction_new_column(db_session):
    """测试：Transaction表新字段"""
    from datetime import date

    strategy = Strategy(name="测试", initial_capital=1000000)
    db_session.add(strategy)
    db_session.commit()

    position = Position(
        symbol="000001.SZSE",
        quantity=1000,
        cost_price=10.00,
        strategy_id=strategy.id,
    )
    db_session.add(position)
    db_session.commit()

    transaction = Transaction(
        position_id=position.id,
        strategy_id=strategy.id,
        transaction_type="buy",
        symbol="000001.SZSE",
        quantity=1000,
        price=10.00,
        amount=10000,
        user_id=1,
        transaction_date=date.today(),
    )
    db_session.add(transaction)
    db_session.commit()

    assert transaction.user_id == 1


def test_audit_log_tables(db_session):
    """测试：审计日志表创建成功"""
    # 检查表是否存在
    from sqlalchemy import inspect

    inspector = inspect(db_session.bind)
    tables = inspector.get_table_names()

    assert "transaction_audit_log" in tables
    assert "strategy_audit_log" in tables
    assert "daily_profit_loss" in tables

    # 验证字段
    transaction_audit_columns = [
        col["name"] for col in inspector.get_columns("transaction_audit_log")
    ]
    assert "transaction_id" in transaction_audit_columns
    assert "field_name" in transaction_audit_columns
    assert "old_value" in transaction_audit_columns
    assert "new_value" in transaction_audit_columns
    assert "change_reason" in transaction_audit_columns


def test_daily_profit_loss_table(db_session):
    """测试：每日盈亏快照表创建成功"""
    from datetime import date
    from sqlalchemy import inspect

    # 创建测试数据
    strategy = Strategy(name="测试", initial_capital=1000000)
    db_session.add(strategy)
    db_session.commit()

    position = Position(
        symbol="000001.SZSE",
        quantity=1000,
        cost_price=10.00,
        strategy_id=strategy.id,
    )
    db_session.add(position)
    db_session.commit()

    daily_pl = DailyProfitLoss(
        record_date=date.today(),
        position_id=position.id,
        symbol="000001.SZSE",
        prev_close_price=9.50,
        current_price=10.00,
        daily_profit_loss=500.00,
    )
    db_session.add(daily_pl)
    db_session.commit()

    # 验证数据
    assert daily_pl.id is not None
    assert daily_pl.symbol == "000001.SZSE"
    assert daily_pl.daily_profit_loss == 500.00

    # 验证表结构
    inspector = inspect(db_session.bind)
    daily_pl_columns = [
        col["name"] for col in inspector.get_columns("daily_profit_loss")
    ]
    assert "record_date" in daily_pl_columns
    assert "position_id" in daily_pl_columns
    assert "symbol" in daily_pl_columns
    assert "prev_close_price" in daily_pl_columns
    assert "current_price" in daily_pl_columns
    assert "daily_profit_loss" in daily_pl_columns
