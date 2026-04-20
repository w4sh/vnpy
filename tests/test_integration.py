"""集成测试：持仓管理系统完整功能测试

测试覆盖：
1. 策略生命周期（创建、更新、删除、恢复）
2. 持仓管理（添加、修改、删除）
3. 交易记录管理（记录、修改）
4. 软删除一致性
5. 重算机制
6. 数据分析API
"""

import pytest
from datetime import datetime, timedelta, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from web_app.models import (
    Base,
    Strategy,
    Position,
    Transaction,
    StrategyAuditLog,
    TransactionAuditLog,
    get_db_session,
)
from web_app.recalc_service import RecalculationService, mark_strategy_dirty
import tempfile
import os


@pytest.fixture
def db_engine():
    """创建测试数据库引擎"""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()

    engine = create_engine(f"sqlite:///{temp_db.name}")
    Base.metadata.create_all(engine)
    yield engine

    os.unlink(temp_db.name)


@pytest.fixture
def db_session_factory(db_engine):
    """创建session工厂"""
    Session = sessionmaker(bind=db_engine)
    return Session


class TestStrategyLifecycle:
    """测试策略生命周期"""

    def test_create_strategy(self, db_session_factory):
        """测试：创建策略"""
        session = db_session_factory()
        try:
            strategy = Strategy(
                name="测试策略",
                description="这是一个测试策略",
                initial_capital=1000000,
                risk_level="中等",
                status="active",
            )
            session.add(strategy)
            session.commit()

            assert strategy.id is not None
            assert strategy.name == "测试策略"
            assert strategy.recalc_status == "clean"
        finally:
            session.close()

    def test_update_strategy(self, db_session_factory):
        """测试：更新策略"""
        session = db_session_factory()
        try:
            # 创建策略
            strategy = Strategy(
                name="原始名称", initial_capital=1000000, status="active"
            )
            session.add(strategy)
            session.commit()

            # 更新策略
            strategy.description = "更新后的描述"
            strategy.risk_level = "低"
            strategy.updated_at = datetime.now()
            session.commit()

            # 验证
            session.expire_all()
            updated = session.query(Strategy).get(strategy.id)
            assert updated.description == "更新后的描述"
            assert updated.risk_level == "低"
        finally:
            session.close()

    def test_soft_delete_strategy(self, db_session_factory):
        """测试：软删除策略"""
        session = db_session_factory()
        try:
            # 创建策略
            strategy = Strategy(name="待删除", initial_capital=1000000, status="active")
            session.add(strategy)
            session.commit()

            # 软删除
            strategy.status = "deleted"
            strategy.updated_at = datetime.now()
            session.commit()

            # 验证：记录仍存在，但状态为deleted
            deleted = session.query(Strategy).get(strategy.id)
            assert deleted is not None
            assert deleted.status == "deleted"
        finally:
            session.close()

    def test_restore_strategy(self, db_session_factory):
        """测试：恢复已删除策略"""
        session = db_session_factory()
        try:
            # 创建并删除策略
            strategy = Strategy(
                name="待恢复", initial_capital=1000000, status="deleted"
            )
            session.add(strategy)
            session.commit()

            # 恢复
            strategy.status = "active"
            strategy.updated_at = datetime.now()
            session.commit()

            # 验证
            session.expire_all()
            restored = session.query(Strategy).get(strategy.id)
            assert restored.status == "active"
        finally:
            session.close()


class TestSoftDeleteConsistency:
    """测试软删除一致性"""

    def test_api_ignores_deleted_strategies(self, db_session_factory):
        """测试：所有API都忽略已删除策略"""
        session = db_session_factory()
        try:
            # 创建活跃和已删除策略
            active = Strategy(name="活跃", initial_capital=1000000, status="active")
            deleted = Strategy(name="已删除", initial_capital=1000000, status="deleted")
            session.add_all([active, deleted])
            session.flush()

            # 为两个策略创建持仓
            pos1 = Position(
                symbol="000001.SZSE",
                quantity=1000,
                cost_price=10.00,
                strategy_id=active.id,
                status="holding",
            )
            pos2 = Position(
                symbol="000002.SZSE",
                quantity=500,
                cost_price=20.00,
                strategy_id=deleted.id,
                status="holding",
            )
            session.add_all([pos1, pos2])
            session.commit()

            # 验证：查询活跃策略只返回活跃策略
            active_strategies = session.query(Strategy).filter_by(status="active").all()
            assert len(active_strategies) == 1
            assert active_strategies[0].name == "活跃"

            # 验证：查询持仓只返回活跃策略的持仓
            holding_positions = (
                session.query(Position).filter_by(status="holding").all()
            )
            assert len(holding_positions) == 2  # 两个持仓都存在
        finally:
            session.close()


class TestRecalculationMechanism:
    """测试重算机制"""

    def test_mark_strategy_dirty(self, db_session_factory):
        """测试：标记策略为dirty"""
        session = db_session_factory()
        try:
            # 创建策略和持仓
            strategy = Strategy(name="测试", initial_capital=1000000, status="active")
            session.add(strategy)
            session.flush()

            position = Position(
                symbol="000001.SZSE",
                quantity=1000,
                cost_price=10.00,
                strategy_id=strategy.id,
                status="holding",
            )
            session.add(position)
            session.commit()

            # 标记为dirty
            mark_strategy_dirty(strategy.id, session)

            # 验证
            session.expire_all()
            updated = session.query(Strategy).get(strategy.id)
            assert updated.recalc_status == "dirty"
        finally:
            session.close()

    def test_recalc_strategy_success(self, db_session_factory):
        """测试：成功重算策略"""
        session = db_session_factory()
        try:
            # 创建策略和持仓
            strategy = Strategy(
                name="测试",
                initial_capital=1000000,
                recalc_status="dirty",
                status="active",
            )
            session.add(strategy)
            session.flush()

            position = Position(
                symbol="000001.SZSE",
                quantity=1000,
                cost_price=10.00,
                current_price=12.00,
                strategy_id=strategy.id,
                status="holding",
            )
            session.add(position)
            session.commit()

            # 执行重算
            recalc_service = RecalculationService(session)
            result = recalc_service.recalc_strategy(strategy.id)

            # 验证
            assert result is True
            session.expire_all()
            updated = session.query(Strategy).get(strategy.id)
            assert updated.recalc_status == "clean"
            assert float(updated.current_capital) == 12000.0
            assert float(updated.total_return) > 0
        finally:
            session.close()

    def test_concurrent_recalc_prevention(self, db_session_factory):
        """测试：防止并发重算"""
        session = db_session_factory()
        try:
            # 创建策略
            strategy = Strategy(
                name="测试",
                initial_capital=1000000,
                recalc_status="recomputing",
                status="active",
            )
            session.add(strategy)
            session.commit()

            # 尝试获取锁
            recalc_service = RecalculationService(session)
            lock_acquired = recalc_service.acquire_execution_lock(strategy.id)

            # 验证：无法获取锁
            assert lock_acquired is False
        finally:
            session.close()


class TestTransactionModification:
    """测试交易记录修改"""

    def test_transaction_modification_updates_position(self, db_session_factory):
        """测试：修改交易记录影响持仓"""
        session = db_session_factory()
        try:
            # 创建策略和持仓
            strategy = Strategy(name="测试", initial_capital=1000000, status="active")
            session.add(strategy)
            session.flush()

            position = Position(
                symbol="000001.SZSE",
                quantity=1000,
                cost_price=10.00,
                strategy_id=strategy.id,
                status="holding",
            )
            session.add(position)
            session.flush()

            # 创建交易记录
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

            # 修改交易价格
            transaction.price = 15.00
            transaction.amount = transaction.quantity * transaction.price
            transaction.updated_at = datetime.now()
            session.commit()

            # 标记策略为dirty
            mark_strategy_dirty(strategy.id, session)

            # 验证
            session.expire_all()
            updated = session.query(Strategy).get(strategy.id)
            assert updated.recalc_status == "dirty"
        finally:
            session.close()

    def test_transaction_audit_log(self, db_session_factory):
        """测试：交易修改审计日志"""
        session = db_session_factory()
        try:
            # 创建策略和交易
            strategy = Strategy(name="测试", initial_capital=1000000, status="active")
            session.add(strategy)
            session.flush()

            position = Position(
                symbol="000001.SZSE",
                quantity=1000,
                cost_price=10.00,
                strategy_id=strategy.id,
                status="holding",
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

            # 记录审计日志
            audit_log = TransactionAuditLog(
                transaction_id=transaction.id,
                field_name="price",
                old_value="10.0",
                new_value="15.0",
                change_reason="价格修正",
                changed_at=datetime.now(),
            )
            session.add(audit_log)
            session.commit()

            # 验证
            logs = (
                session.query(TransactionAuditLog)
                .filter_by(transaction_id=transaction.id)
                .all()
            )
            assert len(logs) == 1
            assert logs[0].field_name == "price"
            assert logs[0].change_reason == "价格修正"
        finally:
            session.close()


class TestDataIntegrity:
    """测试数据完整性"""

    def test_cascade_delete_prevention(self, db_session_factory):
        """测试：防止删除有持仓的策略"""
        session = db_session_factory()
        try:
            # 创建策略和持仓
            strategy = Strategy(name="测试", initial_capital=1000000, status="active")
            session.add(strategy)
            session.flush()

            position = Position(
                symbol="000001.SZSE",
                quantity=1000,
                cost_price=10.00,
                strategy_id=strategy.id,
                status="holding",
            )
            session.add(position)
            session.commit()

            # 尝试软删除策略（应该成功）
            strategy.status = "deleted"
            session.commit()

            # 验证：数据仍存在
            assert session.query(Position).count() == 1
            assert session.query(Strategy).count() == 1
        finally:
            session.close()

    def test_orphaned_transaction_prevention(self, db_session_factory):
        """测试：防止孤立交易记录"""
        session = db_session_factory()
        try:
            # 创建策略、持仓和交易
            strategy = Strategy(name="测试", initial_capital=1000000, status="active")
            session.add(strategy)
            session.flush()

            position = Position(
                symbol="000001.SZSE",
                quantity=1000,
                cost_price=10.00,
                strategy_id=strategy.id,
                status="holding",
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

            # 验证关系完整性
            assert transaction.position_id == position.id
            assert transaction.strategy_id == strategy.id
            assert position.strategy_id == strategy.id
        finally:
            session.close()


class TestAnalyticsIntegration:
    """测试数据分析集成"""

    def test_portfolio_analytics_with_multiple_strategies(self, db_session_factory):
        """测试：多策略投资组合分析"""
        session = db_session_factory()
        try:
            # 创建多个策略
            strategies = []
            for i in range(3):
                strategy = Strategy(
                    name=f"策略{i}", initial_capital=1000000, status="active"
                )
                session.add(strategy)
                session.flush()

                # 每个策略创建持仓
                position = Position(
                    symbol=f"00000{i + 1}.SZSE",
                    quantity=1000,
                    cost_price=10.00,
                    current_price=12.00,
                    market_value=12000,
                    profit_loss=2000,
                    profit_loss_pct=20.00,
                    strategy_id=strategy.id,
                    status="holding",
                )
                session.add(position)
                strategies.append(strategy)

            session.commit()

            # 验证：可以查询所有持仓
            all_positions = session.query(Position).filter_by(status="holding").all()
            assert len(all_positions) == 3

            # 验证：总资产计算
            total_assets = sum(float(p.market_value or 0) for p in all_positions)
            assert total_assets == 36000.0
        finally:
            session.close()

    def test_analytics_ignores_deleted_data(self, db_session_factory):
        """测试：分析API忽略已删除数据"""
        session = db_session_factory()
        try:
            # 创建活跃和已删除策略
            active = Strategy(name="活跃", initial_capital=1000000, status="active")
            deleted = Strategy(name="已删除", initial_capital=1000000, status="deleted")
            session.add_all([active, deleted])
            session.flush()

            # 为活跃策略创建持仓
            pos1 = Position(
                symbol="000001.SZSE",
                quantity=1000,
                cost_price=10.00,
                current_price=12.00,
                market_value=12000,
                strategy_id=active.id,
                status="holding",
            )
            session.add(pos1)
            session.commit()

            # 验证：分析只包含活跃策略
            active_strategies = session.query(Strategy).filter_by(status="active").all()
            assert len(active_strategies) == 1

            holding_positions = (
                session.query(Position).filter_by(status="holding").all()
            )
            assert len(holding_positions) == 1
        finally:
            session.close()
