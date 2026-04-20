"""测试后台定时任务"""

import pytest
from datetime import datetime, timedelta, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from web_app.models import Base, Strategy, Position, Transaction
from web_app.scheduler_tasks import recalc_dirty_strategies, recover_stuck_strategies


@pytest.fixture
def db_session():
    """创建测试数据库和会话"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_recalc_dirty_strategies(db_session, monkeypatch):
    """测试：定时重算dirty策略"""

    # Mock get_db_session 返回我们的测试session
    def mock_get_db_session():
        return db_session

    monkeypatch.setattr("web_app.scheduler_tasks.get_db_session", mock_get_db_session)

    # 创建3个dirty策略
    strategies = []
    for i in range(3):
        strategy = Strategy(
            name=f"策略{i}",
            initial_capital=1000000,
            recalc_status="dirty",
            status="active",
        )
        db_session.add(strategy)
        db_session.flush()  # 确保strategy有ID

        position = Position(
            symbol="000001.SZSE",
            quantity=1000,
            cost_price=10.00,
            current_price=12.00,
            strategy_id=strategy.id,
            status="holding",
        )
        db_session.add(position)

        # 添加买入交易记录
        txn = Transaction(
            position_id=position.id,
            strategy_id=strategy.id,
            transaction_type="buy",
            symbol="000001.SZSE",
            quantity=1000,
            price=10.00,
            fee=5.0,
            amount=10005,
            transaction_date=date.today(),
        )
        db_session.add(txn)

        strategies.append(strategy)

    db_session.commit()

    # 执行定时任务
    recalc_dirty_strategies()

    # 验证：所有策略都变为clean
    for strategy in strategies:
        db_session.refresh(strategy)
        assert strategy.recalc_status == "clean"


def test_recalc_dirty_strategies_ignores_deleted(db_session, monkeypatch):
    """测试：重算任务忽略已删除的策略"""

    # Mock get_db_session
    def mock_get_db_session():
        return db_session

    monkeypatch.setattr("web_app.scheduler_tasks.get_db_session", mock_get_db_session)

    # 创建一个dirty策略和一个已删除的dirty策略
    active_strategy = Strategy(
        name="活跃策略",
        initial_capital=1000000,
        recalc_status="dirty",
        status="active",
    )
    db_session.add(active_strategy)
    db_session.flush()

    deleted_strategy = Strategy(
        name="已删除策略",
        initial_capital=1000000,
        recalc_status="dirty",
        status="deleted",
    )
    db_session.add(deleted_strategy)
    db_session.flush()

    # 为活跃策略添加持仓和交易
    position = Position(
        symbol="000001.SZSE",
        quantity=1000,
        cost_price=10.00,
        current_price=12.00,
        strategy_id=active_strategy.id,
        status="holding",
    )
    db_session.add(position)

    txn = Transaction(
        position_id=position.id,
        strategy_id=active_strategy.id,
        transaction_type="buy",
        symbol="000001.SZSE",
        quantity=1000,
        price=10.00,
        fee=5.0,
        amount=10005,
        transaction_date=date.today(),
    )
    db_session.add(txn)

    db_session.commit()

    # 执行定时任务
    recalc_dirty_strategies()

    # 验证：活跃策略被重算，已删除策略保持dirty
    db_session.refresh(active_strategy)
    db_session.refresh(deleted_strategy)

    assert active_strategy.recalc_status == "clean"
    assert deleted_strategy.recalc_status == "dirty"


def test_recover_stuck_strategies(db_session, monkeypatch):
    """测试：恢复卡死策略"""

    # Mock get_db_session
    def mock_get_db_session():
        return db_session

    monkeypatch.setattr("web_app.scheduler_tasks.get_db_session", mock_get_db_session)

    # 创建超时的recomputing策略
    strategy = Strategy(
        name="卡死策略",
        initial_capital=1000000,
        recalc_status="recomputing",
        status="active",
        updated_at=datetime.now() - timedelta(minutes=35),  # 35分钟前
    )
    db_session.add(strategy)
    db_session.commit()

    # 执行恢复任务
    recover_stuck_strategies()

    # 验证：状态已重置为dirty
    db_session.refresh(strategy)
    assert strategy.recalc_status == "dirty"
    assert "重算超时" in strategy.last_error


def test_recover_stuck_strategies_ignores_deleted(db_session, monkeypatch):
    """测试：恢复任务忽略已删除的策略"""

    # Mock get_db_session
    def mock_get_db_session():
        return db_session

    monkeypatch.setattr("web_app.scheduler_tasks.get_db_session", mock_get_db_session)

    # 创建一个超时的活跃策略和一个超时的已删除策略
    active_strategy = Strategy(
        name="活跃卡死策略",
        initial_capital=1000000,
        recalc_status="recomputing",
        status="active",
        updated_at=datetime.now() - timedelta(minutes=35),
    )
    db_session.add(active_strategy)

    deleted_strategy = Strategy(
        name="已删除卡死策略",
        initial_capital=1000000,
        recalc_status="recomputing",
        status="deleted",
        updated_at=datetime.now() - timedelta(minutes=35),
    )
    db_session.add(deleted_strategy)

    db_session.commit()

    # 执行恢复任务
    recover_stuck_strategies()

    # 验证：活跃策略被恢复，已删除策略保持recomputing
    db_session.refresh(active_strategy)
    db_session.refresh(deleted_strategy)

    assert active_strategy.recalc_status == "dirty"
    assert "重算超时" in active_strategy.last_error
    assert deleted_strategy.recalc_status == "recomputing"
    assert deleted_strategy.last_error is None


def test_no_recovery_for_recent_recomputing(db_session, monkeypatch):
    """测试：不重置最近的recomputing"""

    # Mock get_db_session
    def mock_get_db_session():
        return db_session

    monkeypatch.setattr("web_app.scheduler_tasks.get_db_session", mock_get_db_session)

    # 创建正常的recomputing策略（5分钟前）
    strategy = Strategy(
        name="正常策略",
        initial_capital=1000000,
        recalc_status="recomputing",
        status="active",
        updated_at=datetime.now() - timedelta(minutes=5),
    )
    db_session.add(strategy)
    db_session.commit()

    original_status = strategy.recalc_status

    # 执行恢复任务
    recover_stuck_strategies()

    # 验证：状态未改变
    db_session.refresh(strategy)
    assert strategy.recalc_status == original_status
    assert strategy.last_error is None
