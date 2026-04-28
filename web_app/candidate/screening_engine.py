#!/usr/bin/env python3
"""
候选股筛选引擎

每日收盘后：
1. 获取候选池股票日线数据（Tushare Pro）
2. 计算四类技术因子得分（动量/趋势/量价/波动）
3. 综合打分排序，产出 Top 20 推荐列表
4. 计算每只推荐个股的回测绩效
5. 结果存入 CandidateStock 数据库表
"""

import json
import os
import time
import logging
from datetime import date, timedelta
from pathlib import Path
from dataclasses import dataclass

import numpy as np

from web_app.models import CandidateStock, get_db_session
from web_app.candidate.backtest import calculate_backtest_metrics, normalize_score

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 股票池 — 优先从 StockPoolManager 获取全量A股，回退到手选列表
# 格式: "代码.交易所后缀",  SZSE=深交所  SSE=上交所
# ---------------------------------------------------------------------------


def _load_stock_pool() -> list[str]:
    """加载股票池：优先从 StockPoolManager 获取全量A股

    若 Tushare Token 未配置或同步失败，回退到手选约 250 只列表。
    """
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


_FALLBACK_STOCK_POOL: list[str] = [
    # ---- 金融（银行/保险/券商）----
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
    # ---- 科技 / 电子 ----
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
    "300433.SZSE",
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
    # ---- 消费 / 食品饮料 ----
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
    # ---- 医药健康 ----
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
    # ---- 新能源 / 光伏 / 锂电池 ----
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
    # ---- 工业 / 建筑 / 机械 ----
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
    # ---- 有色 / 化工 / 材料 ----
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
    # ---- 汽车 / 交运 ----
    "601766.SSE",
    "600741.SSE",
    "000625.SZSE",
    "002920.SZSE",
    "601689.SSE",
    "600066.SSE",
    "601238.SSE",
    "000800.SZSE",
    "002594.SZSE",
    "601127.SSE",
    "600115.SSE",
    "600029.SSE",
    "601111.SSE",
    "603786.SSE",
    "601021.SSE",
    # ---- 农业 / 养殖 ----
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
    # ---- 传媒 / 游戏 / 互联网 ----
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
    # ---- 家电 ----
    "000333.SZSE",
    "600690.SSE",
    "002032.SZSE",
    "002050.SZSE",
    "000921.SZSE",
    "002668.SZSE",
    "603486.SSE",
    "002242.SZSE",
    "002959.SZSE",
    "000100.SZSE",
    # ---- 公用事业 / 环保 ----
    "600900.SSE",
    "600886.SSE",
    "000027.SZSE",
    "600025.SSE",
    "601985.SSE",
    "600011.SSE",
    "003816.SZSE",
    "600886.SSE",
    "601158.SSE",
    "300070.SZSE",
    # ---- 房地产 ----
    "600048.SSE",
    "001979.SZSE",
    "600383.SSE",
    "600340.SSE",
    "000002.SZSE",
    "600606.SSE",
    "600325.SSE",
    "600185.SSE",
    "000069.SZSE",
    "002146.SZSE",
    # ---- 军工 / 航天 ----
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
    # ---- 商贸零售 ----
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

# 去重
_FALLBACK_STOCK_POOL = list(dict.fromkeys(_FALLBACK_STOCK_POOL))

# 最终股票池：优先 StockPoolManager，回退到手选列表
STOCK_POOL: list[str] = _load_stock_pool()

# ---------------------------------------------------------------------------
# 因子权重配置（可调整）
# ---------------------------------------------------------------------------
FACTOR_WEIGHTS = {
    "momentum": 0.25,  # 动量因子
    "trend": 0.25,  # 趋势因子
    "volume": 0.25,  # 量价因子
    "volatility": 0.25,  # 波动率因子
}

# 数据需求：最少需要多少根日线 K 线
MIN_BARS_REQUIRED = 60
LOOKBACK_BARS = 120  # 推荐下载数量

# 缓存目录
CACHE_DIR = Path(__file__).parent / "data_cache"


def _symbol_to_tushare(symbol: str) -> str:
    """将 vnpy 格式(000001.SZSE)转为 tushare 格式(000001.SZ)

    SSE -> .SH,  SZSE -> .SZ
    """
    code, exchange = symbol.split(".")
    suffix = "SH" if exchange == "SSE" else "SZ"
    return f"{code}.{suffix}"


def _ts_code_to_symbol(ts_code: str) -> str:
    """将 tushare 格式(000001.SZ)转为 vnpy 格式(000001.SZSE)"""
    code, suffix = ts_code.split(".")
    exchange = "SSE" if suffix == "SH" else "SZSE"
    return f"{code}.{exchange}"


# ---------------------------------------------------------------------------
# 全市场数据获取（按日期批量拉取）
# ---------------------------------------------------------------------------
def get_recent_trade_dates(n: int = 120) -> list[str]:
    """生成最近 n 个工作日的日期列表（倒序）

    不依赖 trade_cal 接口，直接按日历跳过周末。
    非交易日（节假日）在拉取时会被自动跳过。

    返回: ['20260424', '20260423', ...]
    """
    dates: list[str] = []
    d = date.today()
    while len(dates) < n:
        if d.weekday() < 5:  # 跳过周末
            dates.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return dates


def fetch_all_stocks_data(
    trade_dates: list[str] | None = None,
    n_days: int = 120,
) -> dict[str, dict]:
    """按日期批量获取全 A 股日线数据

    调用 pro.daily(trade_date=xxx) 逐日拉取，每次返回全市场 ~5000 只。
    在内存中按股票代码分组，组装成每只股票的时间序列。

    返回: {symbol: {"symbol": ..., "dates": [...], "close": [...], ...}}
    """
    _get_tushare_api()
    import tushare as ts

    pro = ts.pro_api()

    if trade_dates is None:
        trade_dates = get_recent_trade_dates(n_days)

    # 按日期拉取
    stock_data: dict[str, dict] = {}
    valid_dates = []

    for i, td in enumerate(trade_dates):
        try:
            df = pro.daily(trade_date=td)
        except Exception as e:
            logger.warning(f"获取 {td} 全市场数据失败: {e}")
            time.sleep(2)
            continue

        if df is None or len(df) == 0:
            continue

        valid_dates.append(td)

        for _, row in df.iterrows():
            ts_code = row["ts_code"]
            symbol = _ts_code_to_symbol(ts_code)

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

        # 频率控制
        if i < len(trade_dates) - 1:
            time.sleep(1.2)

    # 日期倒序 → 升序（pro.daily 返回的 trade_dates 是倒序的）
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


def _cache_path(symbol: str) -> Path:
    """单个股票的缓存文件路径"""
    return CACHE_DIR / f"{symbol.replace('.', '_')}.json"


# ---------------------------------------------------------------------------
# 数据获取（Tushare Pro）
# ---------------------------------------------------------------------------
def _get_tushare_api():
    """延迟初始化 Tushare Pro API（避免 import 时就连接）"""
    import tushare as ts

    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN 环境变量未设置")
    ts.set_token(token)
    return ts.pro_api()


def fetch_daily_data(symbol: str, lookback: int = LOOKBACK_BARS) -> dict | None:
    """获取单只股票日线数据

    优先读缓存，缓存不存在或过期时通过 Tushare Pro 下载。
    返回 {"dates": [...], "close": [...], "open": [...], "high": [...], "low": [...], "volume": [...]}
    若数据不可用返回 None
    """
    cache_file = _cache_path(symbol)

    # --- 尝试读缓存 ---
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            dates = cached.get("dates", [])
            today_str = date.today().isoformat()
            need_latest = not dates or dates[-1] < today_str
            if not need_latest and len(dates) >= lookback:
                return cached
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    # --- 从 Tushare Pro 下载 ---
    max_retries = 3
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            _get_tushare_api()  # 确保 token 已设置
            ts_code = _symbol_to_tushare(symbol)
            end_str = date.today().strftime("%Y%m%d")
            start_str = (date.today() - timedelta(days=lookback * 2)).strftime("%Y%m%d")

            # 使用 pro_bar 获取前复权数据
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

            # pro_bar 返回倒序，需要按日期升序
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

            # 写缓存
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return result

        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = 2**attempt
                logger.debug(
                    f"获取 {symbol} 失败，{wait}s 后重试 ({attempt}/{max_retries}): {e}"
                )
                time.sleep(wait)

    # 所有重试均失败，回退到缓存（即使略有过期）
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if len(cached.get("dates", [])) >= MIN_BARS_REQUIRED:
                logger.debug(f"{symbol}: 下载失败，使用过期缓存")
                return cached
        except Exception:
            pass

    logger.warning(f"获取 {symbol} 数据失败（重试 {max_retries} 次后）: {last_error}")
    return None


# ---------------------------------------------------------------------------
# 因子计算
# ---------------------------------------------------------------------------
def calc_momentum_score(close_arr: np.ndarray) -> float:
    """动量因子：5/10/20 日收益率加权，标准化到 0-100

    score = minmax(5d_ret*0.5 + 10d_ret*0.3 + 20d_ret*0.2)
    """
    if len(close_arr) < 21:
        return 50.0

    ret_5d = close_arr[-1] / close_arr[-6] - 1
    ret_10d = close_arr[-1] / close_arr[-11] - 1
    ret_20d = close_arr[-1] / close_arr[-21] - 1

    raw = ret_5d * 0.5 + ret_10d * 0.3 + ret_20d * 0.2
    return float(raw)


def calc_trend_score(close_arr: np.ndarray) -> float:
    """趋势因子：价格相对 5/10/20/60 均线的位置

    价格在各均线上方 + 均线多头排列 给高分
    """
    if len(close_arr) < 60:
        return 50.0

    price = close_arr[-1]
    mas = {
        "ma5": np.mean(close_arr[-5:]),
        "ma10": np.mean(close_arr[-10:]),
        "ma20": np.mean(close_arr[-20:]),
        "ma60": np.mean(close_arr[-60:]),
    }

    # 价格在各均线上方的百分比
    deviations = [(price / v - 1) for v in mas.values()]

    # 均线排列得分：ma5 > ma10 > ma20 > ma60 项
    alignment = 0
    if mas["ma5"] > mas["ma10"]:
        alignment += 1
    if mas["ma10"] > mas["ma20"]:
        alignment += 1
    if mas["ma20"] > mas["ma60"]:
        alignment += 1

    # 综合：偏离均线程度 + 排列加分
    avg_dev = np.mean(deviations) * 100  # 百分比偏离
    raw = max(-10, min(10, avg_dev)) * 5 + alignment * 10 + 50
    return float(raw)


def calc_volume_score(df_volume: np.ndarray) -> float:
    """量价因子：5 日均量 / 20 日均量 + 放量上涨加分

    score = minmax(volume_ratio * 50), range [0, 100]
    """
    if len(df_volume) < 20:
        return 50.0

    vol_5 = np.mean(df_volume[-5:])
    vol_20 = np.mean(df_volume[-20:])

    if vol_20 == 0:
        return 50.0

    ratio = vol_5 / vol_20
    # ratio > 1 表示放量，ratio < 1 表示缩量
    # 居中于 50，放量最多 +30，缩量最多 -20
    raw = 50 + (ratio - 1) * 30
    return float(raw)


def calc_volatility_score(close_arr: np.ndarray) -> float:
    """波动率因子：布林带位置 + 低波动加分

    - 价格在布林带中轨上方加分
    - 布林带宽度适中加分
    - 低波动率加分（ATR 相对价格）
    """
    if len(close_arr) < 20:
        return 50.0

    window = 20
    recent = close_arr[-window:]
    ma = np.mean(recent)
    std = np.std(recent)

    if ma == 0:
        return 50.0

    price = close_arr[-1]
    upper = ma + 2 * std
    lower = ma - 2 * std

    # 布林带位置得分：在中轨上方为正
    if upper - lower > 0:
        bb_pos = (price - ma) / (upper - lower)  # 约 [-0.5, 0.5]
    else:
        bb_pos = 0.0

    bb_score = bb_pos * 40 + 50  # 中轨 50，上方 >50

    # ATR 波动得分：低波动 = 高得分
    atr = np.mean(np.abs(np.diff(recent))) / ma * 100  # 日波动百分比

    # ATR 在 1%-3% 之间最理想，超出扣分
    if atr < 1.0:
        atr_score = 25  # 太稳定
    elif atr < 2.5:
        atr_score = 30 - (atr - 1.0) * 10  # 1-2.5%: 30→15
    elif atr < 5.0:
        atr_score = 15 - (atr - 2.5) * 4  # 2.5-5%: 15→5
    else:
        atr_score = 0  # 波动太大

    raw = bb_score * 0.6 + atr_score * 0.4
    return float(raw)


# ---------------------------------------------------------------------------
# 综合打分与批量筛选
# ---------------------------------------------------------------------------
@dataclass
class CandidateResult:
    """单只股票的筛选结果"""

    symbol: str
    name: str
    score: float
    rank: int
    momentum_score: float
    trend_score: float
    volume_score: float
    volatility_score: float
    current_price: float
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe_ratio: float


def score_stock(data: dict) -> CandidateResult | None:
    """对单只股票打分并计算回测"""
    symbol = data["symbol"]
    close_arr = np.array(data["close"], dtype=np.float64)
    volume_arr = np.array(data["volume"], dtype=np.float64)
    dates_arr = np.array(data["dates"])

    if len(close_arr) < MIN_BARS_REQUIRED:
        return None

    # 计算原始因子值
    raw_momentum = calc_momentum_score(close_arr)
    raw_trend = calc_trend_score(close_arr)
    raw_volume = calc_volume_score(volume_arr)
    raw_volatility = calc_volatility_score(close_arr)

    # 保留原始值，由 run_screening 统一做 minmax 标准化
    momentum = round(raw_momentum, 4)
    trend = round(raw_trend, 4)
    volume = round(raw_volume, 4)
    volatility = round(raw_volatility, 4)

    # 回测指标
    backtest = calculate_backtest_metrics(close_arr, dates_arr)

    return CandidateResult(
        symbol=symbol,
        name="",
        score=0.0,
        rank=0,
        momentum_score=momentum,
        trend_score=trend,
        volume_score=volume,
        volatility_score=volatility,
        current_price=round(float(close_arr[-1]), 2),
        total_return=round(backtest["total_return"], 4),
        annual_return=round(backtest["annual_return"], 4),
        max_drawdown=round(backtest["max_drawdown"], 4),
        sharpe_ratio=round(backtest["sharpe_ratio"], 4),
    )


def run_screening(
    stock_pool: list[str] | None = None,
    top_n: int = 20,
    mode: str = "pool",
) -> tuple[list[dict], int, float]:
    """执行一次完整筛选

    Args:
        stock_pool: 股票池列表，仅 mode="pool" 时使用
        top_n: 返回 Top N 只
        mode: "pool" 使用手动股票池逐只获取，"full" 全市场批量获取

    返回: (top_results, stock_count, elapsed_seconds)
    """
    start = time.time()
    results: list[CandidateResult] = []

    if mode == "full":
        # 全市场模式：按日期批量拉取
        all_data = fetch_all_stocks_data()
        pool_size = len(all_data)
        logger.info(f"开始全市场筛选，股票池 {pool_size} 只")

        for data in all_data.values():
            result = score_stock(data)
            if result:
                results.append(result)
    else:
        # 手动池模式：逐只获取
        if stock_pool is None:
            stock_pool = STOCK_POOL

        pool_size = len(stock_pool)
        logger.info(f"开始筛选，股票池 {pool_size} 只")

        for symbol in stock_pool:
            data = fetch_daily_data(symbol)
            if data is None:
                continue
            time.sleep(0.2)

            result = score_stock(data)
            if result:
                results.append(result)

    # --- 标准化因子得分 ---
    if len(results) >= 3:
        m_arr = np.array([r.momentum_score for r in results])
        t_arr = np.array([r.trend_score for r in results])
        v_arr = np.array([r.volume_score for r in results])
        vl_arr = np.array([r.volatility_score for r in results])

        m_norm = normalize_score(m_arr)
        t_norm = normalize_score(t_arr)
        v_norm = normalize_score(v_arr)
        vl_norm = normalize_score(vl_arr)

        for i, r in enumerate(results):
            r.momentum_score = round(float(m_norm[i]), 2)
            r.trend_score = round(float(t_norm[i]), 2)
            r.volume_score = round(float(v_norm[i]), 2)
            r.volatility_score = round(float(vl_norm[i]), 2)

    # --- 综合评分 ---
    for r in results:
        r.score = round(
            r.momentum_score * FACTOR_WEIGHTS["momentum"]
            + r.trend_score * FACTOR_WEIGHTS["trend"]
            + r.volume_score * FACTOR_WEIGHTS["volume"]
            + r.volatility_score * FACTOR_WEIGHTS["volatility"],
            2,
        )

    # --- 按综合分排序 ---
    results.sort(key=lambda x: x.score, reverse=True)

    # --- 取 Top N ---
    top_results = results[:top_n]
    for i, r in enumerate(top_results):
        r.rank = i + 1

    elapsed = round(time.time() - start, 1)
    logger.info(
        f"筛选完成：{len(results)} 只有效股票 → Top {len(top_results)}，耗时 {elapsed}s"
    )

    # 转换为 dict 方便存库和返回
    output = []
    for r in top_results:
        output.append(
            {
                "symbol": r.symbol,
                "name": r.name,
                "score": r.score,
                "rank": r.rank,
                "momentum_score": r.momentum_score,
                "trend_score": r.trend_score,
                "volume_score": r.volume_score,
                "volatility_score": r.volatility_score,
                "current_price": r.current_price,
                "total_return": r.total_return,
                "annual_return": r.annual_return,
                "max_drawdown": r.max_drawdown,
                "sharpe_ratio": r.sharpe_ratio,
            }
        )

    return output, pool_size, elapsed


def save_results_to_db(
    results: list[dict],
    screening_date: date,
    session=None,
):
    """将筛选结果存入数据库"""
    close_session = False
    if session is None:
        session = get_db_session()
        close_session = True

    try:
        for r in results:
            candidate = CandidateStock(
                symbol=r["symbol"],
                name=r["name"],
                score=r["score"],
                rank=r["rank"],
                screening_date=screening_date,
                momentum_score=r["momentum_score"],
                trend_score=r["trend_score"],
                volume_score=r["volume_score"],
                volatility_score=r["volatility_score"],
                current_price=r["current_price"],
                total_return=r["total_return"],
                annual_return=r["annual_return"],
                max_drawdown=r["max_drawdown"],
                sharpe_ratio=r["sharpe_ratio"],
            )
            session.add(candidate)

        session.commit()
        logger.info(f"已保存 {len(results)} 条候选股推荐到数据库")
    except Exception as e:
        logger.error(f"保存结果失败: {e}")
        session.rollback()
        raise
    finally:
        if close_session:
            session.close()


def run_daily_screening():
    """每日筛选主入口 — 由调度器调用"""
    logger.info("=== 开始每日候选股筛选 ===")
    try:
        results, pool_size, elapsed = run_screening()
        save_results_to_db(results, date.today())
        logger.info(
            f"=== 每日候选股筛选完成，股票池 {pool_size}，Top {len(results)}，耗时 {elapsed}s ==="
        )
        return results, pool_size, elapsed
    except Exception as e:
        logger.error(f"每日候选股筛选失败: {e}")
        raise
