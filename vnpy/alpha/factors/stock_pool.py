"""
全量A股股票池管理器

通过 Tushare stock_basic 接口获取全量A股代码列表，
支持本地缓存、ST过滤、代码格式转换。

使用示例::

    manager = StockPoolManager()
    symbols = manager.get_full_pool()
    # symbols: ["000001.SZSE", "000002.SZSE", ...]
"""

import json
import logging
import os
from datetime import date

logger = logging.getLogger(__name__)


def _to_tushare_code(symbol: str) -> str:
    """vnpy 格式 (000001.SZSE) → tushare 格式 (000001.SZ)"""
    code, exchange = symbol.split(".")
    suffix = "SH" if exchange == "SSE" else "SZ"
    return f"{code}.{suffix}"


def _to_vnpy_code(ts_code: str) -> str:
    """tushare 格式 (000001.SZ) → vnpy 格式 (000001.SZSE)"""
    code, suffix = ts_code.split(".")
    exchange = "SSE" if suffix == "SH" else "SZSE"
    return f"{code}.{exchange}"


class StockPoolManager:
    """全量A股股票池管理器

    负责从 Tushare 获取全市场A股代码列表，过滤 ST 股票，
    并将结果缓存到本地 JSON 文件。
    """

    def __init__(self, data_dir: str | None = None):
        """初始化股票池管理器

        参数:
            data_dir: 缓存目录路径，默认为 ~/.vntrader/factors/
        """
        if data_dir is None:
            data_dir = os.path.expanduser("~/.vntrader/factors/")
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self._cache_path = os.path.join(self.data_dir, "stock_pool.json")

    def sync(self) -> list[str]:
        """从 Tushare 同步全量A股代码列表

        调用 stock_basic 接口获取上市股票，过滤名称中包含
        "ST" 或 "*ST" 的股票，转换为 vnpy 代码格式后缓存
        到本地 JSON 文件。

        返回:
            vnpy 格式的股票代码列表，如 ["000001.SZSE", ...]

        异常:
            RuntimeError: 未设置 TUSHARE_TOKEN 环境变量
            Exception: Tushare API 调用失败时向上抛出
        """
        import tushare as ts

        token = os.environ.get("TUSHARE_TOKEN", "")
        if not token:
            raise RuntimeError("TUSHARE_TOKEN 环境变量未设置")

        ts.set_token(token)
        pro = ts.pro_api()

        logger.info("正在从 Tushare 同步全量A股代码列表 ...")
        try:
            raw = pro.stock_basic(
                list_status="L",
                fields="ts_code,name,list_status",
            )
        except Exception:
            logger.exception("调用 stock_basic 失败")
            raise

        if raw is None or len(raw) == 0:
            logger.warning("stock_basic 返回空数据")
            return []

        # 过滤名称中包含 "ST" 或 "*ST" 的股票
        st_mask = raw["name"].str.contains(r"\*?ST", na=False)
        filtered = raw[~st_mask]

        # 转换为 vnpy 代码格式
        symbols = [_to_vnpy_code(code) for code in filtered["ts_code"]]

        # 写入本地缓存
        cache_data = {
            "updated": str(date.today()),
            "symbols": symbols,
            "count": len(symbols),
        }
        with open(self._cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

        logger.info(f"同步完成: 共 {len(symbols)} 只股票（已排除 ST）")
        return symbols

    def get_full_pool(self) -> list[str]:
        """获取全量股票池

        优先从本地缓存读取；若缓存不存在或为空，则调用 sync()
        从 Tushare 同步。

        返回:
            vnpy 格式的股票代码列表
        """
        if os.path.exists(self._cache_path):
            try:
                with open(self._cache_path, encoding="utf-8") as f:
                    cache_data = json.load(f)
                symbols = cache_data.get("symbols", [])
                if symbols:
                    logger.debug(f"从缓存读取股票池: {len(symbols)} 只")
                    return symbols
            except (json.JSONDecodeError, KeyError):
                logger.warning("缓存文件损坏，将重新同步")

        return self.sync()

    def get_filtered_pool(self, rules: dict | None = None) -> list[str]:
        """获取筛选后的股票池（预留接口）

        参数:
            rules: 筛选规则字典，当前未使用，预留供后续扩展。

        返回:
            vnpy 格式的股票代码列表
        """
        _ = rules
        return self.get_full_pool()
