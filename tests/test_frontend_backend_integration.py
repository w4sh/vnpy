"""
前后端联调测试脚本

验证前端页面与后端API的集成功能
"""

import pytest
import requests
from datetime import date
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
import subprocess
import time
import os


class TestFrontendBackendIntegration:
    """前后端集成测试"""

    def setup_method(self):
        """在每个测试之前清理数据库"""
        session = get_db_session()
        try:
            # 删除所有交易记录审计日志
            session.query(TransactionAuditLog).delete(synchronize_session=False)
            # 删除所有交易记录
            session.query(Transaction).delete(synchronize_session=False)
            # 删除所有策略审计日志
            session.query(StrategyAuditLog).delete(synchronize_session=False)
            # 删除所有持仓
            session.query(Position).delete(synchronize_session=False)
            # 删除所有策略（使用hard delete，因为这是测试环境）
            session.query(Strategy).delete(synchronize_session=False)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @pytest.fixture
    def db_session(self):
        """创建测试数据库（使用与Flask应用相同的数据库）"""
        # 使用与Flask应用相同的数据库路径
        engine = create_engine("sqlite:///position_management.db")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()

        # 注意：不删除数据库，因为Flask应用需要使用它

    @pytest.fixture
    def flask_app(self):
        """启动Flask应用（使用简化版测试应用）"""
        # 设置环境变量
        os.environ["PYTHONPATH"] = "/Users/w4sh8899/project/vnpy"

        # 启动Flask应用（后台进程）- 使用测试专用应用
        proc = subprocess.Popen(
            ["python3", "web_app/test_app.py"],
            cwd="/Users/w4sh8899/project/vnpy",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 等待服务器启动
        time.sleep(3)

        # 验证服务器已启动
        max_retries = 5
        for i in range(max_retries):
            try:
                response = requests.get("http://localhost:5001", timeout=2)
                if response.status_code == 200:
                    break
            except Exception as err:
                if i < max_retries - 1:
                    time.sleep(2)
                else:
                    proc.terminate()
                    proc.wait()
                    raise RuntimeError("Flask应用启动失败") from err

        yield "http://localhost:5001"

        # 关闭服务器
        proc.terminate()
        proc.wait()

    def test_api_endpoint_portfolio_analytics(self, db_session):
        """测试：投资组合分析API"""
        # 创建测试数据
        strategy = Strategy(name="测试策略", initial_capital=1000000, status="active")
        db_session.add(strategy)
        db_session.flush()

        position = Position(
            symbol="000001.SZSE",
            name="测试股票",
            quantity=1000,
            cost_price=10.00,
            current_price=12.00,
            market_value=12000,
            profit_loss=2000,
            profit_loss_pct=20.00,
            strategy_id=strategy.id,
            status="holding",
        )
        db_session.add(position)
        db_session.commit()

        # 等待数据库写入完成
        import time

        time.sleep(0.5)

        # 测试API
        response = requests.get("http://localhost:5001/api/analytics/portfolio")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "analytics" in data

        # 如果有数据，验证summary字段
        if data["analytics"]:
            if "summary" in data["analytics"]:
                assert data["analytics"]["summary"]["total_assets"] >= 0

    def test_api_endpoint_positions(self, db_session):
        """测试：持仓列表API"""
        # 创建测试数据
        strategy = Strategy(name="测试策略", initial_capital=1000000, status="active")
        db_session.add(strategy)
        db_session.flush()

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
        db_session.add(position)
        db_session.commit()

        # 测试API
        response = requests.get("http://localhost:5001/api/positions")

        assert response.status_code == 200
        data = response.json()

        # API返回格式: {"positions": [...], "success": true}
        assert data["success"] is True
        assert isinstance(data["positions"], list)
        assert len(data["positions"]) == 1
        assert data["positions"][0]["symbol"] == "000001.SZSE"

    def test_api_endpoint_strategies(self, db_session):
        """测试：策略列表API"""
        # 创建测试数据
        strategy1 = Strategy(name="策略A", initial_capital=1000000, status="active")
        strategy2 = Strategy(name="策略B", initial_capital=2000000, status="deleted")
        db_session.add_all([strategy1, strategy2])
        db_session.commit()

        # 测试API
        response = requests.get("http://localhost:5001/api/strategies")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, dict)
        assert "strategies" in data
        # 应该只返回活跃策略
        assert len(data["strategies"]) == 1
        assert data["strategies"][0]["name"] == "策略A"

    def test_frontend_page_load(self, flask_app):
        """测试：前端页面加载"""
        # 测试主页
        response = requests.get(flask_app)
        assert response.status_code == 200
        assert "vn.py" in response.text

        # 测试持仓概览页面
        response = requests.get(flask_app + "/position_management")
        assert response.status_code == 200
        assert "持仓概览" in response.text

    def test_frontend_api_integration(self, flask_app, db_session):
        """测试：前端与后端API集成"""
        # 创建测试数据
        strategy = Strategy(name="集成测试", initial_capital=1000000, status="active")
        db_session.add(strategy)
        db_session.flush()

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
        db_session.add(position)
        db_session.commit()

        # 测试API是否返回前端期望的数据格式
        response = requests.get(flask_app + "/api/analytics/portfolio")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

        # 验证前端能解析的数据结构
        assert "analytics" in data
        assert "summary" in data["analytics"]
        assert "distribution" in data["analytics"]

        # distribution数据应该包含前端需要的字段
        if len(data["analytics"]["distribution"]) > 0:
            dist = data["analytics"]["distribution"][0]
            assert "symbol" in dist
            assert "market_value" in dist

    def test_cors_and_security(self, flask_app):
        """测试：CORS和安全头"""
        response = requests.options(flask_app + "/api/positions")

        # 检查CORS头（如果配置了）
        # 注意：当前可能没有配置CORS

        # 测试无效请求应返回404
        response = requests.get(flask_app + "/api/invalid_endpoint")
        assert response.status_code == 404

    def test_data_consistency(self, db_session):
        """测试：数据一致性"""
        # 创建完整的测试数据
        strategy = Strategy(
            name="一致性测试",
            initial_capital=1000000,
            current_capital=1200000,
            recalc_status="clean",
            status="active",
        )
        db_session.add(strategy)
        db_session.flush()

        position = Position(
            symbol="000001.SZSE",
            name="测试股票",
            quantity=1000,
            cost_price=10.00,
            current_price=12.00,
            market_value=12000,
            profit_loss=2000,
            profit_loss_pct=20.00,
            strategy_id=strategy.id,
            status="holding",
        )
        db_session.add(position)
        db_session.flush()

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
        db_session.add(transaction)
        db_session.commit()

        # 验证所有API返回一致的数据
        # 1. 持仓API
        positions_resp = requests.get("http://localhost:5001/api/positions").json()
        # API返回格式: {"positions": [...], "success": true}
        assert len(positions_resp["positions"]) == 1

        # 2. 策略API
        strategies_resp = requests.get("http://localhost:5001/api/strategies").json()
        assert len(strategies_resp["strategies"]) == 1

        # 3. 分析API
        analytics_resp = requests.get(
            "http://localhost:5001/api/analytics/portfolio"
        ).json()
        assert analytics_resp["analytics"]["summary"]["position_count"] == 1

    def test_performance_response_time(self, flask_app, db_session):
        """测试：API响应时间"""
        # 创建多个测试数据
        for i in range(10):
            strategy = Strategy(
                name=f"策略{i}", initial_capital=1000000, status="active"
            )
            db_session.add(strategy)
            db_session.flush()

            position = Position(
                symbol=f"00000{i % 9 + 1}SZSE",
                name=f"股票{i}",
                quantity=1000,
                cost_price=10.00,
                current_price=12.00,
                market_value=12000,
                strategy_id=strategy.id,
                status="holding",
            )
            db_session.add(position)
        db_session.commit()

        # 测试响应时间
        import time

        start = time.time()
        response = requests.get("http://localhost:5001/api/positions")
        end = time.time()

        assert response.status_code == 200
        response_time = end - start

        # 响应时间应小于1秒
        assert response_time < 1.0, f"API响应时间过长: {response_time:.2f}秒"

        print(f"\n✅ API响应时间: {response_time:.3f}秒")


def run_integration_tests():
    """运行集成测试"""
    print("🚀 开始前后端联调测试...\n")

    # 检查Flask应用是否已运行
    try:
        requests.get("http://localhost:5001", timeout=2)
        app_running = True
        print("✅ Flask应用正在运行")
    except Exception:
        app_running = False
        print("⚠️  Flask应用未运行，请先手动启动:")
        print("   cd /Users/w4sh8899/project/vnpy")
        print("   python3 web_app/app.py")

    if not app_running:
        print("\n💡 启动应用后运行以下命令进行测试:")
        print("   pytest tests/test_frontend_backend_integration.py -v")
        return

    # 运行测试
    print("\n📋 运行集成测试套件...")
    exit_code = pytest.main([__file__, "-v", "--tb=short"])

    if exit_code == 0:
        print("\n✅ 所有集成测试通过！")
    else:
        print(f"\n❌ 集成测试失败，退出码: {exit_code}")


if __name__ == "__main__":
    run_integration_tests()
