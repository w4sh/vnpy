"""
资金流向因子 Parquet 存储层
"""

import os
from datetime import datetime
from pathlib import Path

import polars as pl

from vnpy.alpha.factors.base import FactorStorage

DEFAULT_DATA_DIR = os.path.join(os.path.expanduser("~"), ".vntrader", "factors")


class FlowStorage(FactorStorage):
    """资金流向因子 Parquet 存储"""

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.data_dir / "flow_daily.parquet"

    def save(self, factors: pl.DataFrame) -> None:
        """追加资金流向因子（按 trade_date 去重）"""
        factors = factors.unique(subset=["trade_date"])
        if self.file_path.exists():
            existing = pl.read_parquet(self.file_path)
            combined = pl.concat([existing, factors]).unique(subset=["trade_date"])
            combined.write_parquet(self.file_path)
        else:
            factors.write_parquet(self.file_path)

    def load(
        self,
        symbols: list[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pl.DataFrame:
        """加载资金流向数据"""
        if not self.file_path.exists():
            raise FileNotFoundError(f"{self.file_path} 不存在")
        return pl.read_parquet(self.file_path)

    def get_latest(self, symbols: list[str] | None = None) -> pl.DataFrame:
        """获取最近一个交易日的资金流数据"""
        if not self.file_path.exists():
            raise FileNotFoundError(f"{self.file_path} 不存在")
        df = pl.read_parquet(self.file_path)
        if df.is_empty():
            return df
        return df.tail(1)

    def get_latest_score(self) -> float:
        """获取最新 flow_score，默认 50.0"""
        latest = self.get_latest()
        if latest.is_empty() or "flow_score" not in latest.columns:
            return 50.0
        val = latest["flow_score"][0]
        return float(val) if val is not None else 50.0
