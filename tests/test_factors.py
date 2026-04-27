"""
前瞻因子引擎单元测试
"""

import tempfile
from datetime import datetime

import numpy as np
import polars as pl

from vnpy.alpha.factors.base import DataFetcher, FactorComputer, FactorStorage
from vnpy.alpha.factors.engine import FactorEngine


# ---------------------------------------------------------------------------
# 测试辅助: Mock 实现
# ---------------------------------------------------------------------------


class MockFetcher(DataFetcher):
    """返回模拟日频估值数据"""

    def fetch(self, symbols, date):
        rows = []
        for sym in symbols:
            rows.append(
                {
                    "trade_date": "20241025",
                    "ts_code": sym.replace("SZSE", "SZ").replace("SSE", "SH"),
                    "pe_ttm": 10.0 + hash(sym) % 100,
                    "pb": 2.0 + (hash(sym) % 10) * 0.1,
                    "ps_ttm": 3.0 + (hash(sym) % 5) * 0.2,
                }
            )
        return pl.DataFrame(rows)


class MockComputer(FactorComputer):
    """将 raw df 直接当因子输出"""

    def compute(self, raw_df):
        return raw_df


class MockStorage(FactorStorage):
    """内存存储"""

    def __init__(self):
        self._data = None

    def save(self, factors):
        self._data = factors

    def load(self, symbols, start, end):
        if self._data is None:
            raise FileNotFoundError("no data")
        return self._data

    def get_latest(self, symbols):
        if self._data is None:
            return pl.DataFrame()
        return self._data

    # 额外方法供 Engine 调用
    def save_daily(self, factors):
        self._data = factors

    def save_quarterly(self, factors):
        pass


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------


class TestFactorEngine:
    """因子引擎调度器测试"""

    def test_register_and_run_daily(self):
        """测试管线注册与日终运行"""
        engine = FactorEngine()
        engine.register(
            "test_dim",
            MockFetcher(),
            MockComputer(),
            MockStorage(),
        )

        symbols = ["000001.SZSE", "600036.SSE"]
        engine.run_daily(symbols, "20241025")

        assert engine.pipelines

    def test_get_latest_snapshot(self):
        """测试获取最新快照"""
        engine = FactorEngine()
        storage = MockStorage()
        engine.register("test", MockFetcher(), MockComputer(), storage)

        symbols = ["000001.SZSE", "600036.SSE"]
        engine.run_daily(symbols, "20241025")
        # run_daily skips non-fundamental pipelines; directly save sample data
        storage.save_daily(
            pl.DataFrame(
                {
                    "trade_date": ["20241025", "20241025"],
                    "vt_symbol": symbols,
                    "pe_ttm": [10.0, 20.0],
                }
            )
        )
        snapshot = engine.get_latest_snapshot(symbols)

        assert not snapshot.is_empty()
        assert "trade_date" in snapshot.columns


class TestDimensionScorer:
    """维度评分器测试"""

    def test_equal_weight_scoring(self):
        from vnpy.alpha.factors.fusion import DimensionScorer

        df = pl.DataFrame(
            {
                "vt_symbol": ["A.SSE", "B.SSE", "C.SSE", "D.SSE"],
                "factor1": [10.0, 20.0, 30.0, 40.0],
                "factor2": [0.1, 0.2, 0.15, 0.05],
            }
        )

        scorer = DimensionScorer()
        result = scorer.score(df, ["factor1", "factor2"])

        assert len(result) == 4
        assert "dimension_score" in result.columns
        scores = result["dimension_score"].to_list()
        assert scores[0] < scores[3]  # D should score highest

    def test_single_factor(self):
        from vnpy.alpha.factors.fusion import DimensionScorer

        df = pl.DataFrame(
            {
                "vt_symbol": ["A.SSE", "B.SSE"],
                "pe_ttm": [1.0, 2.0],
            }
        )
        scorer = DimensionScorer()
        result = scorer.score(df, ["pe_ttm"], {"pe_ttm": 1.0})
        assert len(result) == 2
        # 高 PE 得高分 (rank 1 → 100)
        assert result["dimension_score"][1] > result["dimension_score"][0]

    def test_nan_handling(self):
        from vnpy.alpha.factors.fusion import DimensionScorer

        df = pl.DataFrame(
            {
                "vt_symbol": ["A.SSE", "B.SSE", "C.SSE"],
                "factor1": [10.0, None, float("nan")],
            }
        )
        scorer = DimensionScorer()
        result = scorer.score(df, ["factor1"])
        scores = result["dimension_score"].to_list()
        for s in scores:
            assert not np.isnan(s)


class TestSignalFusion:
    """信号融合器测试"""

    def test_two_dimension_fusion(self):
        from vnpy.alpha.factors.fusion import SignalFusion

        fund_df = pl.DataFrame(
            {
                "vt_symbol": ["A.SSE", "B.SSE"],
                "dimension_score": [80.0, 60.0],
            }
        )
        tech_df = pl.DataFrame(
            {
                "vt_symbol": ["A.SSE", "B.SSE"],
                "dimension_score": [40.0, 90.0],
            }
        )

        fusion = SignalFusion({"technical": 0.5, "fundamental": 0.5})
        result = fusion.fuse(
            datetime.now(),
            ["A.SSE", "B.SSE"],
            {"technical": tech_df, "fundamental": fund_df},
        )

        assert len(result) == 2
        assert "final_score" in result.columns
        assert "detail_json" in result.columns

        scores = result["final_score"].to_list()
        a_score = [
            s for i, s in enumerate(scores) if result["vt_symbol"][i] == "A.SSE"
        ][0]
        b_score = [
            s for i, s in enumerate(scores) if result["vt_symbol"][i] == "B.SSE"
        ][0]
        assert abs(a_score - 60.0) < 1.0
        assert abs(b_score - 75.0) < 1.0


class TestFundamentalStorage:
    """存储层测试"""

    def test_parquet_save_and_load(self):
        from vnpy.alpha.factors.fundamental.storage import FundamentalStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FundamentalStorage(tmpdir)

            df = pl.DataFrame(
                {
                    "trade_date": ["20241025", "20241025"],
                    "vt_symbol": ["A.SSE", "B.SSE"],
                    "pe_ttm": [10.0, 20.0],
                }
            )
            storage.save_daily(df)

            latest = storage.get_latest(["A.SSE", "B.SSE"])
            assert len(latest) == 2

            loaded = storage.load(
                ["A.SSE"],
                datetime(2024, 10, 1),
                datetime(2024, 11, 1),
            )
            assert len(loaded) == 1
            assert loaded["vt_symbol"][0] == "A.SSE"

    def test_dedup_on_append(self):
        from vnpy.alpha.factors.fundamental.storage import FundamentalStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FundamentalStorage(tmpdir)

            df1 = pl.DataFrame(
                {
                    "trade_date": ["20241025"],
                    "vt_symbol": ["A.SSE"],
                    "pe_ttm": [10.0],
                }
            )
            storage.save_daily(df1)
            storage.save_daily(df1)

            latest = storage.get_latest(["A.SSE"])
            assert len(latest) == 1
