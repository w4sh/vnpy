"""候选股推荐系统测试套件

测试覆盖:
- 回测指标计算
- 因子计算函数
- 综合打分和排序逻辑
- API 端点
"""

from datetime import date

import numpy as np
import pytest

from web_app.candidate.backtest import calculate_backtest_metrics, normalize_score
from web_app.candidate.screening_engine import (
    calc_momentum_score,
    calc_trend_score,
    calc_volume_score,
    calc_volatility_score,
    score_stock,
    _symbol_to_tushare,
)


# ============================================================================
# 回测指标测试
# ============================================================================


class TestBacktestMetrics:
    """测试回测绩效指标计算"""

    def test_upward_trend(self):
        """上涨趋势的股票，收益为正，回撤为负"""
        rng = np.random.default_rng(42)
        # 带随机波动的上涨，确保有回撤
        trend = np.linspace(10, 20, 100)
        noise = rng.normal(0, 0.3, 100)
        prices = trend + noise
        dates = np.array(["2024-01-01"] * 100)

        result = calculate_backtest_metrics(prices, dates)

        assert result["total_return"] > 0
        assert result["annual_return"] > 0
        assert result["max_drawdown"] < 0
        assert result["sharpe_ratio"] > 0

    def test_downward_trend(self):
        """下跌趋势的股票"""
        prices = np.linspace(20, 10, 100)
        dates = np.array(["2024-01-01"] * 100)

        result = calculate_backtest_metrics(prices, dates)

        assert result["total_return"] < 0
        assert result["annual_return"] < 0
        assert result["max_drawdown"] < 0

    def test_flat_market(self):
        """横盘市场"""
        prices = np.ones(50) * 10.0
        dates = np.array(["2024-01-01"] * 50)

        result = calculate_backtest_metrics(prices, dates)

        assert result["total_return"] == pytest.approx(0.0, abs=0.001)
        assert result["sharpe_ratio"] == pytest.approx(0.0, abs=0.001)

    def test_max_drawdown_calculation(self):
        """验证最大回撤计算正确"""
        prices = np.array([100, 120, 80, 140, 100])
        dates = np.array(["2024-01-01"] * 5)

        result = calculate_backtest_metrics(prices, dates)

        # 从 120 到 80 的回撤: (80-120)/120 = -0.333
        assert result["max_drawdown"] == pytest.approx(-0.333, abs=0.001)

    def test_sharpe_positive(self):
        """稳定上涨 = 高夏普"""
        prices = np.array([10 + i * 0.1 for i in range(200)])  # 稳定上涨
        dates = np.array(["2024-01-01"] * 200)

        result = calculate_backtest_metrics(prices, dates)

        assert result["sharpe_ratio"] > 1.0

    def test_few_prices(self):
        """价格序列太短时返回默认值"""
        prices = np.array([10.0])
        dates = np.array(["2024-01-01"])

        result = calculate_backtest_metrics(prices, dates)

        assert result["total_return"] == 0.0
        assert result["sharpe_ratio"] == 0.0

    def test_annual_return_clamp(self):
        """年化收益应在 [-1, 10] 区间内"""
        prices = np.array([10, 100])  # 极端上涨
        dates = np.array(["2024-01-01"] * 2)

        result = calculate_backtest_metrics(prices, dates)

        assert -1.0 <= result["annual_return"] <= 10.0


# ============================================================================
# normalize_score 测试
# ============================================================================


class TestNormalizeScore:
    """测试得分标准化函数"""

    def test_normalize_range(self):
        """标准化后应在 [0, 100] 范围内"""
        values = np.array([10, 20, 30, 40, 50])
        result = normalize_score(values)

        assert np.all(result >= 0.0)
        assert np.all(result <= 100.0)
        assert result[0] == pytest.approx(0.0)
        assert result[-1] == pytest.approx(100.0)

    def test_identical_values(self):
        """所有值相同时返回全 0"""
        values = np.array([42, 42, 42, 42])
        result = normalize_score(values)

        assert np.all(result == 0.0)

    def test_two_values(self):
        """两个值：最小 0，最大 100"""
        values = np.array([15.5, 88.2])
        result = normalize_score(values)

        assert result[0] == pytest.approx(0.0)
        assert result[1] == pytest.approx(100.0)


# ============================================================================
# 因子计算测试 (synthetic data)
# ============================================================================


class TestFactorCalculations:
    """测试各因子的计算逻辑"""

    def test_momentum_positive(self):
        """上涨股票：动量为正（原始返回值，非 0-100）"""
        close = np.linspace(10, 15, 30)
        raw = calc_momentum_score(close)

        # 原始动量 > 0 表示正收益
        assert raw > 0

    def test_momentum_negative(self):
        """下跌股票：动量为负"""
        close = np.linspace(15, 10, 30)
        raw = calc_momentum_score(close)

        assert raw < 0

    def test_momentum_short_data(self):
        """数据不足时返回默认值"""
        close = np.array([10, 11, 12])
        score = calc_momentum_score(close)

        assert score == pytest.approx(50.0)

    def test_trend_above_all_mas(self):
        """价格在所有均线上方，趋势分高"""
        close = np.array([9.0 + i * 0.02 for i in range(80)])
        score = calc_trend_score(close)

        assert score > 50

    def test_trend_below_all_mas(self):
        """价格在所有均线下方，趋势分低"""
        close = np.array([12.0 - i * 0.02 for i in range(80)])
        score = calc_trend_score(close)

        assert score < 50

    def test_trend_short_data(self):
        """数据不足时返回默认值"""
        close = np.array([10, 11, 12])
        score = calc_trend_score(close)

        assert score == pytest.approx(50.0)

    def test_volume_high_ratio(self):
        """近期放量：量价分偏高"""
        vol = np.array([1000] * 15 + [2000] * 5)
        score = calc_volume_score(vol)

        assert score > 50

    def test_volume_low_ratio(self):
        """近期缩量：量价分偏低"""
        vol = np.array([2000] * 15 + [1000] * 5)
        score = calc_volume_score(vol)

        assert score < 50

    def test_volume_zero_mean(self):
        """成交量为 0 时返回 50"""
        vol = np.zeros(20)
        score = calc_volume_score(vol)

        assert score == pytest.approx(50.0)

    def test_volatility_normal_range(self):
        """正常波动范围"""
        rng = np.random.default_rng(42)
        close = 10.0 + np.cumsum(rng.normal(0, 0.02, 30))
        score = calc_volatility_score(close)

        assert 0 <= score <= 100


# ============================================================================
# 辅助工具测试
# ============================================================================


class TestSymbolConversion:
    """测试股票代码格式转换"""

    def test_szse_symbol(self):
        result = _symbol_to_tushare("000001.SZSE")
        assert result == "000001.SZ"

    def test_sse_symbol(self):
        result = _symbol_to_tushare("600519.SSE")
        assert result == "600519.SH"


# ============================================================================
# 综合打分测试
# ============================================================================


class TestScoreStock:
    """测试单只股票打分"""

    def make_synthetic_data(self, n_bars: int = 80, trend: float = 0.001) -> dict:
        """生成合成的日线数据"""
        rng = np.random.default_rng(42)
        noise = rng.normal(0, 0.01, n_bars)
        close = 10.0 + np.cumsum(noise + trend * np.ones(n_bars))
        dates = [f"2024-{i:02d}-01" for i in range(1, min(n_bars, 30) + 1)]
        dates = dates[:n_bars]

        return {
            "symbol": "TEST.SZSE",
            "dates": dates,
            "open": list(close * 0.99),
            "close": list(close),
            "high": list(close * 1.02),
            "low": list(close * 0.98),
            "volume": list(np.abs(rng.normal(1000000, 200000, n_bars))),
        }

    def test_score_stock_returns_result(self):
        """正常数据应返回有效结果"""
        data = self.make_synthetic_data(80)
        result = score_stock(data)

        assert result is not None
        assert result.symbol == "TEST.SZSE"
        assert 0 <= result.momentum_score <= 100
        assert 0 <= result.trend_score <= 100
        assert 0 <= result.volume_score <= 100
        assert 0 <= result.volatility_score <= 100
        assert result.current_price > 0

    def test_score_stock_insufficient_data(self):
        """数据不足 60 根 K 线应返回 None"""
        data = self.make_synthetic_data(10)
        result = score_stock(data)

        assert result is None


# ============================================================================
# API 端点集成测试
# ============================================================================


@pytest.mark.integration
class TestCandidateAPI:
    """测试候选股 API 端点"""

    @pytest.fixture
    def client(self):
        from web_app.app import app

        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_get_latest_empty(self, client):
        """无数据时返回空结果但有正确结构"""
        response = client.get("/api/candidates/latest")
        data = response.get_json()

        assert response.status_code == 200
        assert data["success"] is True
        assert isinstance(data["results"], list)

    def test_get_history_no_params(self, client):
        """不带参数查询历史"""
        response = client.get("/api/candidates/history")
        data = response.get_json()

        assert response.status_code == 200
        assert data["success"] is True
        assert isinstance(data["results"], dict)

    def test_get_history_with_date(self, client):
        """带日期参数查询历史"""
        response = client.get("/api/candidates/history?date=2024-01-01")
        data = response.get_json()

        assert response.status_code == 200
        assert data["success"] is True


# ============================================================================
# 数据库模型测试
# ============================================================================


class TestCandidateStockModel:
    """测试 CandidateStock 数据库模型"""

    def test_model_fields(self):
        """验证模型字段定义"""
        from web_app.models import CandidateStock

        assert hasattr(CandidateStock, "symbol")
        assert hasattr(CandidateStock, "score")
        assert hasattr(CandidateStock, "rank")
        assert hasattr(CandidateStock, "screening_date")

    def test_create_instance(self):
        """可以创建模型实例"""
        from web_app.models import CandidateStock

        c = CandidateStock(
            symbol="000001.SZSE",
            name="平安银行",
            score=85.5,
            rank=1,
            screening_date=date.today(),
            momentum_score=80.0,
            trend_score=90.0,
            volume_score=75.0,
            volatility_score=88.0,
            current_price=15.80,
        )
        assert c.symbol == "000001.SZSE"
        assert c.score == 85.5
        assert c.rank == 1
