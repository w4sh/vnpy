"""测试仪表盘数据分析API"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from web_app.models import (
    Base,
    Strategy,
    Position,
)
from web_app.analytics_api import analytics_bp
from flask import Flask
import tempfile
import os


@pytest.fixture
def app():
    """创建测试Flask应用"""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(analytics_bp)
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


def test_get_portfolio_analytics(app, db_session_factory):
    """测试：获取投资组合分析"""
    session = db_session_factory()
    try:
        # 创建测试策略
        strategy = Strategy(name="测试", initial_capital=1000000, status="active")
        session.add(strategy)
        session.flush()

        # 创建测试持仓
        position = Position(
            symbol="000001.SZSE",
            name="平安银行",
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
        session.commit()

        # Monkey patch get_db_session
        import web_app.analytics_api as analytics_api_module

        original_get_db_session = analytics_api_module.get_db_session
        analytics_api_module.get_db_session = lambda: session

        try:
            client = app.test_client()
            response = client.get("/api/analytics/portfolio")

            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            assert "analytics" in data
            assert "summary" in data["analytics"]
            assert data["analytics"]["summary"]["total_assets"] == 12000
            assert data["analytics"]["summary"]["position_count"] == 1
        finally:
            analytics_api_module.get_db_session = original_get_db_session

    finally:
        session.close()


def test_get_strategy_analytics(app, db_session_factory):
    """测试：获取策略分析"""
    session = db_session_factory()
    try:
        # 创建测试策略
        strategy = Strategy(
            name="测试策略",
            initial_capital=1000000,
            current_capital=1200000,
            status="active",
        )
        session.add(strategy)
        session.flush()

        # 创建测试持仓
        position = Position(
            symbol="000001.SZSE",
            name="平安银行",
            quantity=1000,
            cost_price=10.00,
            current_price=12.00,
            market_value=12000,
            strategy_id=strategy.id,
            status="holding",
        )
        session.add(position)
        session.commit()

        # Monkey patch get_db_session
        import web_app.analytics_api as analytics_api_module

        original_get_db_session = analytics_api_module.get_db_session
        analytics_api_module.get_db_session = lambda: session

        try:
            client = app.test_client()
            response = client.get(f"/api/analytics/strategy/{strategy.id}")

            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            assert data["analytics"]["strategy_id"] == strategy.id
            assert data["analytics"]["strategy_name"] == "测试策略"
            assert data["analytics"]["initial_capital"] == 1000000
            assert data["analytics"]["position_count"] == 1
        finally:
            analytics_api_module.get_db_session = original_get_db_session

    finally:
        session.close()


def test_compare_strategies(app, db_session_factory):
    """测试：策略对比分析"""
    session = db_session_factory()
    try:
        # 创建两个测试策略
        strategy1 = Strategy(
            name="策略A",
            initial_capital=1000000,
            risk_level="低",
            status="active",
        )
        strategy2 = Strategy(
            name="策略B",
            initial_capital=1000000,
            risk_level="高",
            status="active",
        )
        session.add_all([strategy1, strategy2])
        session.flush()

        # 为每个策略创建持仓
        position1 = Position(
            symbol="000001.SZSE",
            quantity=1000,
            cost_price=10.00,
            current_price=12.00,
            market_value=12000,
            strategy_id=strategy1.id,
            status="holding",
        )
        position2 = Position(
            symbol="000002.SZSE",
            quantity=500,
            cost_price=20.00,
            current_price=18.00,
            market_value=9000,
            strategy_id=strategy2.id,
            status="holding",
        )
        session.add_all([position1, position2])
        session.commit()

        # Monkey patch get_db_session
        import web_app.analytics_api as analytics_api_module

        original_get_db_session = analytics_api_module.get_db_session
        analytics_api_module.get_db_session = lambda: session

        try:
            client = app.test_client()
            response = client.get("/api/analytics/comparison")

            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            assert len(data["comparison"]) == 2
            assert data["comparison"][0]["strategy_name"] == "策略A"
            assert data["comparison"][1]["strategy_name"] == "策略B"
        finally:
            analytics_api_module.get_db_session = original_get_db_session

    finally:
        session.close()


def test_analytics_ignores_deleted_strategies(app, db_session_factory):
    """测试：分析API忽略已删除的策略"""
    session = db_session_factory()
    try:
        # 创建一个活跃策略和一个已删除策略
        active_strategy = Strategy(
            name="活跃策略",
            initial_capital=1000000,
            status="active",
        )
        deleted_strategy = Strategy(
            name="已删除策略",
            initial_capital=1000000,
            status="deleted",
        )
        session.add_all([active_strategy, deleted_strategy])
        session.flush()

        # 为两个策略都创建持仓
        position1 = Position(
            symbol="000001.SZSE",
            quantity=1000,
            cost_price=10.00,
            current_price=12.00,
            market_value=12000,
            strategy_id=active_strategy.id,
            status="holding",
        )
        position2 = Position(
            symbol="000002.SZSE",
            quantity=500,
            cost_price=20.00,
            current_price=22.00,
            market_value=11000,
            strategy_id=deleted_strategy.id,
            status="holding",
        )
        session.add_all([position1, position2])
        session.commit()

        # Monkey patch get_db_session
        import web_app.analytics_api as analytics_api_module

        original_get_db_session = analytics_api_module.get_db_session
        analytics_api_module.get_db_session = lambda: session

        try:
            client = app.test_client()
            response = client.get("/api/analytics/comparison")

            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            # 应该只返回活跃策略
            assert len(data["comparison"]) == 1
            assert data["comparison"][0]["strategy_name"] == "活跃策略"
        finally:
            analytics_api_module.get_db_session = original_get_db_session

    finally:
        session.close()
