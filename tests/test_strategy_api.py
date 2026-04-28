"""测试策略管理API"""

import pytest
from web_app.models import Strategy, StrategyAuditLog, Position, Base
from flask import Flask
from web_app.strategy_api import strategy_bp
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def app():
    """创建测试Flask应用"""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(strategy_bp)
    return app


@pytest.fixture
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


@pytest.fixture(autouse=True)
def _patch_get_db_session(db_engine, monkeypatch):
    """将 strategy_api 的 get_db_session 替换为测试数据库会话

    由于 strategy_api 会在请求结束时 close session，每次调用
    get_db_session 都需要创建一个新的 session 从同一个 engine。
    """
    import web_app.strategy_api as strategy_api_module

    def _make_session():
        Session = sessionmaker(bind=db_engine)
        return Session()

    monkeypatch.setattr(strategy_api_module, "get_db_session", _make_session)


def test_update_strategy_description(app, db_session):
    """测试:更新策略描述"""
    strategy = Strategy(name="测试策略", initial_capital=1000000, recalc_status="clean")
    db_session.add(strategy)
    db_session.commit()

    client = app.test_client()
    response = client.put(
        f"/api/strategies/{strategy.id}", json={"description": "更新后的描述"}
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["description"] == "更新后的描述"

    # 验证审计日志
    db_session.expire_all()
    audit = (
        db_session.query(StrategyAuditLog)
        .filter_by(strategy_id=strategy.id, field_name="description")
        .first()
    )
    assert audit is not None


def test_update_strategy_reject_protected_fields(app, db_session):
    """测试:拒绝修改受保护字段"""
    strategy = Strategy(name="测试策略2", initial_capital=1000000)
    db_session.add(strategy)
    db_session.commit()

    client = app.test_client()
    response = client.put(f"/api/strategies/{strategy.id}", json={"name": "新名称"})

    assert response.status_code == 400
    assert "不允许修改" in response.get_json()["error"]


def test_delete_strategy_success(app, db_session):
    """测试:成功删除策略(软删除)"""
    strategy = Strategy(name="测试策略3", initial_capital=1000000)
    db_session.add(strategy)
    db_session.commit()
    strategy_id = strategy.id

    client = app.test_client()
    response = client.delete(f"/api/strategies/{strategy.id}?reason=测试删除")

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "deleted"
    assert "message" in data
    assert "已删除" in data["message"]

    # 验证软删除:策略仍存在但状态为deleted
    db_session.expire_all()
    strategy = db_session.query(Strategy).get(strategy_id)
    assert strategy is not None  # 仍然存在
    assert strategy.status == "deleted"  # 状态已改变


def test_delete_strategy_with_active_positions(app, db_session):
    """测试:拒绝删除有活跃持仓的策略"""
    strategy = Strategy(name="测试策略4", initial_capital=1000000)
    db_session.add(strategy)
    db_session.commit()

    # 创建活跃持仓
    position = Position(
        symbol="000001.SZSE",
        quantity=1000,
        cost_price=10.00,
        strategy_id=strategy.id,
        status="holding",
    )
    db_session.add(position)
    db_session.commit()

    client = app.test_client()
    response = client.delete(f"/api/strategies/{strategy.id}")

    assert response.status_code == 400
    assert "活跃持仓" in response.get_json()["error"]


def test_get_strategy_details(app, db_session):
    """测试:获取策略详情"""
    strategy = Strategy(
        name="测试策略5",
        description="策略描述",
        initial_capital=1000000,
        current_capital=1200000,
        total_return=0.2,
        recalc_status="clean",
    )
    db_session.add(strategy)
    db_session.commit()

    client = app.test_client()
    response = client.get(f"/api/strategies/{strategy.id}")

    assert response.status_code == 200
    data = response.get_json()
    assert data["name"] == "测试策略5"
    assert data["description"] == "策略描述"
    assert data["recalc_status"] == "clean"


def test_get_strategy_positions(app, db_session):
    """测试:获取策略持仓列表"""
    # 创建策略
    strategy = Strategy(name="测试策略6", initial_capital=1000000)
    db_session.add(strategy)
    db_session.commit()

    # 创建持仓
    position = Position(
        symbol="000001.SZSE",
        name="平安银行",
        quantity=1000,
        cost_price=10.00,
        current_price=12.00,
        strategy_id=strategy.id,
        status="holding",
    )
    db_session.add(position)
    db_session.commit()

    client = app.test_client()
    response = client.get(f"/api/strategies/{strategy.id}/positions")

    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 1
    assert data[0]["symbol"] == "000001.SZSE"
    assert data[0]["quantity"] == 1000


def test_get_strategy_details_after_deletion(app, db_session):
    """测试:获取已删除策略的详情(应该返回404)"""
    strategy = Strategy(
        name="测试策略7",
        description="策略描述",
        initial_capital=1000000,
        recalc_status="clean",
    )
    db_session.add(strategy)
    db_session.commit()
    strategy_id = strategy.id

    # 软删除策略
    strategy.status = "deleted"
    db_session.commit()

    client = app.test_client()
    response = client.get(f"/api/strategies/{strategy_id}")

    # 应该返回404,因为策略已删除
    assert response.status_code == 404
    assert "不存在" in response.get_json()["error"]
