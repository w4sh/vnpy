"""候选股数据获取引擎

负责：
- 股票池加载（优先 StockPoolManager，回退到手选列表）
- Tushare Pro API 管理
- 全市场 / 单只股票日线数据获取
- 本地缓存读写
"""

from __future__ import annotations

import json
import os
import time
import logging
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 股票池 — 优先从 StockPoolManager 获取全量A股，回退到手选列表
# ---------------------------------------------------------------------------

_FALLBACK_STOCK_POOL: list[str] = [
    "000001.SZSE",
    "002142.SZSE",
    "600000.SSE",
    "600015.SSE",
    "600016.SSE",
    "600036.SSE",
    "601009.SSE",
    "601166.SSE",
    "601169.SSE",
    "601288.SSE",
    "601318.SSE",
    "601328.SSE",
    "601398.SSE",
    "601628.SSE",
    "601818.SSE",
    "601939.SSE",
    "601988.SSE",
    "600030.SSE",
    "600837.SSE",
    "000776.SZSE",
    "002736.SZSE",
    "601211.SSE",
    "601688.SSE",
    "600999.SSE",
    "002797.SZSE",
    "000725.SZSE",
    "002415.SZSE",
    "002230.SZSE",
    "300750.SZSE",
    "002049.SZSE",
    "603986.SSE",
    "300782.SZSE",
    "002371.SZSE",
    "688981.SSE",
    "688012.SSE",
    "688256.SSE",
    "300661.SZSE",
    "300433.SZSE",
    "002475.SZSE",
    "600745.SSE",
    "000063.SZSE",
    "002241.SZSE",
    "300136.SZSE",
    "600703.SSE",
    "300408.SZSE",
    "000977.SZSE",
    "688111.SSE",
    "688036.SSE",
    "002456.SZSE",
    "002185.SZSE",
    "603501.SSE",
    "300124.SZSE",
    "600584.SSE",
    "002916.SZSE",
    "000858.SZSE",
    "000568.SZSE",
    "600519.SSE",
    "002304.SZSE",
    "000895.SZSE",
    "600887.SSE",
    "603288.SSE",
    "002568.SZSE",
    "600809.SSE",
    "300146.SZSE",
    "000596.SZSE",
    "600600.SSE",
    "600132.SSE",
    "002557.SZSE",
    "603345.SSE",
    "002847.SZSE",
    "603517.SSE",
    "002507.SZSE",
    "600882.SSE",
    "002891.SZSE",
    "300760.SZSE",
    "600276.SSE",
    "000538.SZSE",
    "300015.SZSE",
    "002007.SZSE",
    "300122.SZSE",
    "600196.SSE",
    "300529.SZSE",
    "300347.SZSE",
    "688180.SSE",
    "000963.SZSE",
    "300759.SZSE",
    "002001.SZSE",
    "600085.SSE",
    "300003.SZSE",
    "600535.SSE",
    "688185.SSE",
    "300142.SZSE",
    "002821.SZSE",
    "300558.SZSE",
    "300274.SZSE",
    "601012.SSE",
    "002129.SZSE",
    "600438.SSE",
    "300450.SZSE",
    "002459.SZSE",
    "300763.SZSE",
    "688599.SSE",
    "002074.SZSE",
    "300117.SZSE",
    "601615.SSE",
    "002460.SZSE",
    "300207.SZSE",
    "600406.SSE",
    "002709.SZSE",
    "300014.SZSE",
    "002812.SZSE",
    "601877.SSE",
    "300118.SZSE",
    "002611.SZSE",
    "600031.SSE",
    "000157.SZSE",
    "600585.SSE",
    "601668.SSE",
    "600104.SSE",
    "000338.SZSE",
    "600690.SSE",
    "000651.SZSE",
    "002594.SZSE",
    "601857.SSE",
    "601088.SSE",
    "600028.SSE",
    "601899.SSE",
    "601390.SSE",
    "601800.SSE",
    "600048.SSE",
    "000002.SZSE",
    "001979.SZSE",
    "600383.SSE",
    "600606.SSE",
    "600340.SSE",
    "000069.SZSE",
    "601186.SSE",
    "601618.SSE",
    "600170.SSE",
    "600111.SSE",
    "000831.SZSE",
    "002466.SZSE",
    "603799.SSE",
    "600516.SSE",
    "000630.SZSE",
    "600019.SSE",
    "000932.SZSE",
    "600309.SSE",
    "002601.SZSE",
    "600989.SSE",
    "600426.SSE",
    "002648.SZSE",
    "601233.SSE",
    "002493.SZSE",
    "000792.SZSE",
    "600160.SSE",
    "002064.SZSE",
    "603260.SSE",
    "601168.SSE",
    "601766.SSE",
    "600741.SSE",
    "000625.SZSE",
    "002920.SZSE",
    "601689.SSE",
    "600066.SSE",
    "601238.SSE",
    "000800.SZSE",
    "601127.SSE",
    "600115.SSE",
    "600029.SSE",
    "601111.SSE",
    "603786.SSE",
    "601021.SSE",
    "002714.SZSE",
    "300498.SZSE",
    "000876.SZSE",
    "600737.SSE",
    "002311.SZSE",
    "000998.SZSE",
    "002385.SZSE",
    "300189.SZSE",
    "600598.SSE",
    "002041.SZSE",
    "300059.SZSE",
    "002555.SZSE",
    "002624.SZSE",
    "300418.SZSE",
    "300033.SZSE",
    "002027.SZSE",
    "603444.SSE",
    "002739.SZSE",
    "300413.SZSE",
    "300251.SZSE",
    "600637.SSE",
    "000681.SZSE",
    "002131.SZSE",
    "300383.SZSE",
    "600986.SSE",
    "000333.SZSE",
    "002032.SZSE",
    "002050.SZSE",
    "000921.SZSE",
    "002668.SZSE",
    "603486.SSE",
    "002242.SZSE",
    "002959.SZSE",
    "000100.SZSE",
    "600900.SSE",
    "600886.SSE",
    "000027.SZSE",
    "600025.SSE",
    "601985.SSE",
    "600011.SSE",
    "003816.SZSE",
    "601158.SSE",
    "300070.SZSE",
    "600325.SSE",
    "600185.SSE",
    "002146.SZSE",
    "600893.SSE",
    "002025.SZSE",
    "600760.SSE",
    "600118.SSE",
    "002179.SZSE",
    "600862.SSE",
    "600435.SSE",
    "002013.SZSE",
    "600391.SSE",
    "300034.SZSE",
    "002024.SZSE",
    "601933.SSE",
    "300792.SZSE",
    "002127.SZSE",
    "002315.SZSE",
    "600415.SSE",
    "002416.SZSE",
    "600859.SSE",
    "000785.SZSE",
    "601828.SSE",
]

_FALLBACK_STOCK_POOL = list(dict.fromkeys(_FALLBACK_STOCK_POOL))


def _load_stock_pool() -> list[str]:
    """加载股票池：优先从 StockPoolManager 获取全量A股"""
    try:
        from vnpy.alpha.factors.stock_pool import StockPoolManager

        pool = StockPoolManager().get_full_pool()
        if pool:
            logger.info(f"从 StockPoolManager 加载全量股票池: {len(pool)} 只")
            return pool
    except Exception as e:
        logger.warning(f"StockPoolManager 加载失败，使用手选列表: {e}")
    logger.info("使用手选股票池")
    return _FALLBACK_STOCK_POOL


STOCK_POOL: list[str] = _load_stock_pool()

# ---------------------------------------------------------------------------
# 全局配置
# ---------------------------------------------------------------------------

FACTOR_WEIGHTS = {
    "momentum": 0.25,
    "trend": 0.25,
    "volume": 0.25,
    "volatility": 0.25,
}

MIN_BARS_REQUIRED = 60
LOOKBACK_BARS = 120

CACHE_DIR = Path(__file__).parent / "data_cache"

# ---------------------------------------------------------------------------
# 格式转换
# ---------------------------------------------------------------------------


def symbol_to_tushare(symbol: str) -> str:
    """vnpy 格式(000001.SZSE) → tushare 格式(000001.SZ)"""
    code, exchange = symbol.split(".")
    suffix = "SH" if exchange == "SSE" else "SZ"
    return f"{code}.{suffix}"


def ts_code_to_symbol(ts_code: str) -> str:
    """tushare 格式(000001.SZ) → vnpy 格式(000001.SZSE)"""
    code, suffix = ts_code.split(".")
    exchange = "SSE" if suffix == "SH" else "SZSE"
    return f"{code}.{exchange}"


# ---------------------------------------------------------------------------
# 日期工具
# ---------------------------------------------------------------------------


def get_recent_trade_dates(n: int = 120) -> list[str]:
    """生成最近 n 个工作日日期列表"""
    dates: list[str] = []
    d = date.today()
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return dates


# ---------------------------------------------------------------------------
# Tushare API
# ---------------------------------------------------------------------------


def _get_tushare_api():
    """延迟初始化 Tushare Pro API

    优先级：环境变量 TUSHARE_TOKEN > $(pwd)/.env > ~/.env
    """
    import tushare as ts

    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        # 环境变量未设置时，尝试从 .env 文件加载
        for env_file in (Path.cwd() / ".env", Path.home() / ".env"):
            if not env_file.exists():
                continue
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, *rest = line.split("=", 1)
                if key.strip() == "TUSHARE_TOKEN":
                    token = rest[0].strip().strip("'").strip('"')
                    if token:
                        os.environ["TUSHARE_TOKEN"] = token
                    break
            if token:
                break

    if not token:
        raise RuntimeError(
            "TUSHARE_TOKEN 环境变量未设置。"
            "请在项目根目录 .env 文件中设置 "
            "TUSHARE_TOKEN=your_token_here"
        )
    ts.set_token(token)
    return ts.pro_api()


# ---------------------------------------------------------------------------
# 单只股票数据获取
# ---------------------------------------------------------------------------


def _cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol.replace('.', '_')}.json"


def fetch_daily_data(symbol: str, lookback: int = LOOKBACK_BARS) -> dict | None:
    """获取单只股票日线数据

    优先读缓存，缓存过期时通过 Tushare Pro 下载。
    """
    cache_file = _cache_path(symbol)

    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            dates = cached.get("dates", [])
            today_str = date.today().isoformat()
            if not dates or dates[-1] >= today_str:
                if len(dates) >= lookback:
                    return cached
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    max_retries = 3
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            _get_tushare_api()
            ts_code = symbol_to_tushare(symbol)
            end_str = date.today().strftime("%Y%m%d")
            start_str = (date.today() - timedelta(days=lookback * 2)).strftime("%Y%m%d")

            import tushare as ts

            df = ts.pro_bar(
                ts_code=ts_code,
                start_date=start_str,
                end_date=end_str,
                adj="qfq",
                asset="E",
                freq="D",
            )

            if df is None or len(df) < MIN_BARS_REQUIRED:
                return None

            df = df.sort_values("trade_date").reset_index(drop=True)

            result = {
                "symbol": symbol,
                "dates": df["trade_date"].tolist(),
                "open": df["open"].astype(float).tolist(),
                "close": df["close"].astype(float).tolist(),
                "high": df["high"].astype(float).tolist(),
                "low": df["low"].astype(float).tolist(),
                "volume": df["vol"].astype(float).tolist(),
            }

            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return result

        except Exception as e:
            last_error = e
            if attempt < max_retries:
                time.sleep(2**attempt)

    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if len(cached.get("dates", [])) >= MIN_BARS_REQUIRED:
                return cached
        except Exception:
            pass

    logger.warning(f"获取 {symbol} 数据失败（重试 {max_retries} 次后）: {last_error}")
    return None


# ---------------------------------------------------------------------------
# 全市场批量数据获取
# ---------------------------------------------------------------------------


def fetch_all_stocks_data(
    trade_dates: list[str] | None = None,
    n_days: int = 120,
) -> dict[str, dict]:
    """按日期批量获取全 A 股日线数据

    调用 pro.daily(trade_date=xxx) 逐日拉取，组装成每只股票的时间序列。
    """
    _get_tushare_api()
    import tushare as ts

    pro = ts.pro_api()

    if trade_dates is None:
        trade_dates = get_recent_trade_dates(n_days)

    stock_data: dict[str, dict] = {}

    for i, td in enumerate(trade_dates):
        try:
            df = pro.daily(trade_date=td)
        except Exception as e:
            logger.warning(f"获取 {td} 全市场数据失败: {e}")
            time.sleep(2)
            continue

        if df is None or len(df) == 0:
            continue

        for _, row in df.iterrows():
            symbol = ts_code_to_symbol(row["ts_code"])

            if symbol not in stock_data:
                stock_data[symbol] = {
                    "symbol": symbol,
                    "dates": [],
                    "open": [],
                    "close": [],
                    "high": [],
                    "low": [],
                    "volume": [],
                }

            stock_data[symbol]["dates"].append(td)
            stock_data[symbol]["open"].append(float(row["open"]))
            stock_data[symbol]["close"].append(float(row["close"]))
            stock_data[symbol]["high"].append(float(row["high"]))
            stock_data[symbol]["low"].append(float(row["low"]))
            stock_data[symbol]["volume"].append(float(row["vol"]))

        if i < len(trade_dates) - 1:
            time.sleep(1.2)

    for sym_data in stock_data.values():
        sym_data["dates"].reverse()
        sym_data["open"].reverse()
        sym_data["close"].reverse()
        sym_data["high"].reverse()
        sym_data["low"].reverse()
        sym_data["volume"].reverse()

    logger.info(
        f"全市场数据获取完成: {len(trade_dates)} 个交易日, {len(stock_data)} 只有效股票"
    )
    return stock_data


# 港交所自 2024年8月20日起停止发布日度北向资金个股持股明细，改为季度披露。
# fetch_hk_hold_data() 已移除，北向因子回退至 4 因子模型。
