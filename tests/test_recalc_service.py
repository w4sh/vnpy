"""测试重算服务核心逻辑"""

import pytest
from datetime import datetime, timedelta, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from web_app.models import Base, Strategy, Position, Transaction
from web_app.recalc_service import RecalculationService, handle_recalc_failure
from web_app.models import get_db_session


@pytest.fixture
def db_session():
    """创建测试数据库和会话"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_mark_strategy_dirty(db_session):
    """测试：标记策略为dirty"""
    strategy = Strategy(name="测试策略", initial_capital=1000000, recalc_status="clean")
    db_session.add(strategy)
    db_session.commit()

    service = RecalculationService(db_session)
    result = service.mark_strategy_dirty(strategy.id)

    assert result is True

    strategy = db_session.query(Strategy).get(strategy.id)
    assert strategy.recalc_status == "dirty"
    assert strategy.recalc_retry_count == 0


def test_mark_strategy_dirty_idempotent(db_session):
    """测试：重复标记dirty不改变状态"""
    strategy = Strategy(name="测试策略", initial_capital=1000000, recalc_status="dirty")
    db_session.add(strategy)
    db_session.commit()

    service = RecalculationService(db_session)
    service.mark_strategy_dirty(strategy.id)

    # 状态仍为dirty，重试次数不变
    strategy = db_session.query(Strategy).get(strategy.id)
    assert strategy.recalc_status == "dirty"
    assert strategy.recalc_retry_count == 0


def test_acquire_lock_success(db_session):
    """测试：成功获取执行锁"""
    strategy = Strategy(name="测试策略", initial_capital=1000000, recalc_status="dirty")
    db_session.add(strategy)
    db_session.commit()

    service = RecalculationService(db_session)
    result = service.acquire_execution_lock(strategy.id)

    assert result is True

    strategy = db_session.query(Strategy).get(strategy.id)
    assert strategy.recalc_status == "recomputing"


def test_acquire_lock_failed(db_session):
    """测试：获取锁失败（已被抢占）"""
    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status="recomputing",  # 已经在执行
    )
    db_session.add(strategy)
    db_session.commit()

    service = RecalculationService(db_session)
    result = service.acquire_execution_lock(strategy.id)

    assert result is False


def test_weighted_average_cost_calculation(db_session):
    """测试：加权平均成本法计算"""
    # 创建策略
    strategy = Strategy(name="测试策略", initial_capital=1000000, recalc_status="clean")
    db_session.add(strategy)
    db_session.commit()

    # 创建持仓
    position = Position(
        symbol="000001.SZSE",
        strategy_id=strategy.id,
        quantity=0,
        cost_price=0.00,
        current_price=10.00,
        status="holding",
    )
    db_session.add(position)
    db_session.commit()

    # 第一次买入
    txn1 = Transaction(
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
    db_session.add(txn1)
    db_session.commit()

    # 重算
    service = RecalculationService(db_session)
    service._recalc_position_cost(position)
    db_session.commit()

    position = db_session.query(Position).get(position.id)
    # 成本 = (1000 * 10.00 + 5) / 1000 = 10.005
    # 由于Decimal精度问题,结果可能是10.005或10.01
    assert abs(float(position.cost_price) - 10.005) < 0.01
    assert position.quantity == 1000


def test_recalc_strategy_full_flow(db_session):
    """测试：完整重算流程"""
    # 创建策略和持仓
    strategy = Strategy(name="测试策略", initial_capital=1000000, recalc_status="dirty")
    db_session.add(strategy)
    db_session.flush()  # 确保strategy有ID

    positions = []
    for i in range(3):
        position = Position(
            symbol=f"00000{i + 1}.SZSE",
            strategy_id=strategy.id,
            quantity=1000 * (i + 1),
            cost_price=10.00 + i,
            current_price=12.00 + i,
            status="holding",
        )
        db_session.add(position)
        positions.append(position)

    db_session.flush()  # 确保所有position都有ID

    # 为每个持仓添加买入交易记录
    for i, position in enumerate(positions):
        txn = Transaction(
            position_id=position.id,
            strategy_id=strategy.id,
            transaction_type="buy",
            symbol=position.symbol,
            quantity=1000 * (i + 1),
            price=10.00 + i,
            fee=5.0,
            amount=(1000 * (i + 1) * (10.00 + i)) + 5.0,
            transaction_date=date.today(),
        )
        db_session.add(txn)

    db_session.commit()  # 提交所有更改

    # 执行重算
    service = RecalculationService(db_session)
    service.recalc_strategy(strategy.id)

    # 验证结果
    db_session.expire_all()  # 清除session缓存
    strategy = db_session.query(Strategy).get(strategy.id)
    assert strategy.recalc_status == "clean"
    assert strategy.recalc_retry_count == 0
    # 每个持仓的market_value = quantity * current_price
    # pos1: 1000 * 12.00 = 12000
    # pos2: 2000 * 13.00 = 26000
    # pos3: 3000 * 14.00 = 42000
    # total = 80000
    assert abs(float(strategy.current_capital) - 80000) < 1


def test_recalc_strategy_rollback_on_error(db_session):
    """测试：重算失败时回滚"""
    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status="dirty",
        current_capital=50000,
    )
    db_session.add(strategy)
    db_session.commit()

    # 添加一个持仓，确保会调用_recalc_position_cost
    position = Position(
        symbol="000001.SZSE",
        strategy_id=strategy.id,
        quantity=1000,
        cost_price=10.00,
        current_price=12.00,
        status="holding",
    )
    db_session.add(position)
    db_session.commit()

    original_capital = strategy.current_capital

    service = RecalculationService(db_session)

    # 模拟重算失败
    def mock_recalc_position(position):
        raise Exception("模拟失败")

    service._recalc_position_cost = mock_recalc_position

    # 执行重算（应该失败）
    with pytest.raises(Exception):
        service.recalc_strategy(strategy.id)

    # 验证数据未改变（回滚成功）
    strategy = db_session.query(Strategy).get(strategy.id)
    assert strategy.current_capital == original_capital
    assert strategy.recalc_status == "dirty"


def test_handle_recalc_failure_under_limit(db_session):
    """测试：失败处理（未达到重试上限）"""
    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status="recomputing",
        recalc_retry_count=1,
    )
    db_session.add(strategy)
    db_session.commit()
    strategy_id = strategy.id

    # 直接调用handle_recalc_failure,传入db_session用于测试
    handle_recalc_failure(strategy_id, "模拟失败", session=db_session)

    # 清除缓存并验证
    db_session.expire_all()
    strategy = db_session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == "dirty"
    assert strategy.recalc_retry_count == 2  # 1 + 1 = 2
    assert "模拟失败" in strategy.last_error


def test_handle_recalc_failure_max_retries(db_session):
    """测试：失败处理（达到重试上限）"""
    strategy = Strategy(
        name="测试策略",
        initial_capital=1000000,
        recalc_status="recomputing",
        recalc_retry_count=3,
    )
    db_session.add(strategy)
    db_session.commit()
    strategy_id = strategy.id

    # 直接调用handle_recalc_failure,传入db_session用于测试
    handle_recalc_failure(strategy_id, "模拟失败", session=db_session)

    # 清除缓存并验证
    db_session.expire_all()
    strategy = db_session.query(Strategy).get(strategy_id)
    assert strategy.recalc_status == "failed"
    assert "Max retries exceeded" in strategy.last_error
    # 重试次数应该保持为3,不再增加
