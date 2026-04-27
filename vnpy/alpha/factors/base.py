"""
前瞻因子引擎抽象基类

定义数据拉取 -> 因子计算 -> 持久化的标准三阶段接口。
所有维度（基本面/资金流向/市场情绪）都实现这三个接口。
"""

from abc import ABC, abstractmethod
from datetime import datetime

import polars as pl


class DataFetcher(ABC):
    """数据拉取器抽象基类

    从外部数据源（如 Tushare）获取原始数据。
    """

    @abstractmethod
    def fetch(self, symbols: list[str], date: datetime) -> pl.DataFrame:
        """拉取指定交易日/报告期的原始数据"""
        pass


class FactorComputer(ABC):
    """因子计算器抽象基类

    输入原始数据，输出因子长表。
    长表格式: date_col | vt_symbol | factor_name | factor_value
    """

    @abstractmethod
    def compute(self, raw_df: pl.DataFrame) -> pl.DataFrame:
        """计算因子值，返回长表 DataFrame"""
        pass


class FactorStorage(ABC):
    """因子存储器抽象基类

    负责因子数据的 Parquet 文件读写。
    """

    @abstractmethod
    def save(self, factors: pl.DataFrame) -> None:
        """保存因子长表到 Parquet 文件"""
        pass

    @abstractmethod
    def load(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        """按日期范围和品种加载因子数据"""
        pass

    @abstractmethod
    def get_latest(self, symbols: list[str]) -> pl.DataFrame:
        """获取每个品种最新的因子快照"""
        pass
