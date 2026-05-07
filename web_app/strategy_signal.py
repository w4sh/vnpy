"""策略信号计算服务

将回测策略逻辑应用到当前持仓，生成买入/卖出/持有信号。
支持: DualMaStrategy, BollingerBandsStrategy, MomentumStrategy, DualThrustStrategy, AdvancedBollingerPicker
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 信号类型
# ---------------------------------------------------------------------------

SIGNALS = {
    "STRONG_BUY": {"label": "强烈买入", "color": "#28a745"},
    "BUY": {"label": "买入", "color": "#17a2b8"},
    "HOLD": {"label": "持有", "color": "#ffc107"},
    "SELL": {"label": "卖出", "color": "#dc3545"},
    "STRONG_SELL": {"label": "强烈卖出", "color": "#dc3545"},
    "WAIT": {"label": "观望", "color": "#6c757d"},
}


def _to_tushare_ts_code(symbol: str) -> str:
    """将 vt_symbol (如 000001.SZSE) 转为 Tushare ts_code (如 000001.SZ)"""
    s = symbol.upper().strip()
    if "." in s:
        code, exchange = s.split(".", 1)
        if exchange in ("SZSE", "SZ"):
            return f"{code}.SZ"
        if exchange in ("SSE", "SH"):
            return f"{code}.SH"
    return s


# ---------------------------------------------------------------------------
# 行情数据获取
# ---------------------------------------------------------------------------


def _fetch_kline(symbol: str, days: int = 60) -> list[dict[str, Any]] | None:
    """获取股票日线行情

    Args:
        symbol: vt_symbol 格式 (如 000001.SZSE)
        days: 拉取天数

    Returns:
        list of {trade_date, open, high, low, close, vol}
        按 trade_date 升序排列
    """
    try:
        from vnpy.alpha.factors.tushare_config import get_pro_api

        pro = get_pro_api()
    except Exception as e:
        logger.warning("Tushare 初始化失败: %s", e)
        return None

    ts_code = _to_tushare_ts_code(symbol)
    end_date = datetime.now().strftime("%Y%m%d")
    start = datetime.now() - timedelta(days=days)
    start_date = start.strftime("%Y%m%d")

    try:
        df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return None

        df = df.sort_values("trade_date")
        return df.to_dict("records")
    except Exception as e:
        logger.warning("拉取 %s 日线失败: %s", ts_code, e)
        return None


# ---------------------------------------------------------------------------
# 策略信号计算器
# ---------------------------------------------------------------------------


def _signal_dual_ma(prices: list[float], params: dict[str, Any]) -> dict[str, Any]:
    """双均线信号: fast_ma vs slow_ma"""
    fast = params.get("fast_window", 5)
    slow = params.get("slow_window", 20)

    if len(prices) < slow:
        return {
            "signal": "WAIT",
            "indicator": {},
            "desc": f"数据不足({len(prices)}/{slow})",
        }

    def ma(win: int) -> float:
        return sum(prices[-win:]) / win

    cur_fast = ma(fast)
    cur_slow = ma(slow)
    prev_fast = (
        sum(prices[-(fast + 1) : -1]) / fast if len(prices) >= fast + 1 else cur_fast
    )
    prev_slow = (
        sum(prices[-(slow + 1) : -1]) / slow if len(prices) >= slow + 1 else cur_slow
    )

    signal = "HOLD"
    desc = f"MA{fast}({cur_fast:.2f}) MA{slow}({cur_slow:.2f})"

    if prev_fast <= prev_slow and cur_fast > cur_slow:
        signal = "BUY"
        desc += " 金叉↑，买入信号"
    elif prev_fast >= prev_slow and cur_fast < cur_slow:
        signal = "SELL"
        desc += " 死叉↓，卖出信号"
    elif cur_fast > cur_slow:
        signal = "HOLD"
        desc += " 多头排列，持有"
    else:
        signal = "HOLD"
        desc += " 空头排列，观望"

    return {
        "signal": signal,
        "indicator": {f"MA{fast}": round(cur_fast, 2), f"MA{slow}": round(cur_slow, 2)},
        "desc": desc,
    }


def _signal_bollinger(prices: list[float], params: dict[str, Any]) -> dict[str, Any]:
    """布林带信号: 价格在布林带中的位置"""
    window = params.get("ma_window", 20)
    k = params.get("dev_mult", 2.0)

    if len(prices) < window:
        return {
            "signal": "WAIT",
            "indicator": {},
            "desc": f"数据不足({len(prices)}/{window})",
        }

    recent = prices[-window:]
    cur_price = prices[-1]
    ma = sum(recent) / window
    variance = sum((x - ma) ** 2 for x in recent) / window
    std = math.sqrt(variance)
    upper = ma + k * std
    lower = ma - k * std
    bb_pos = (cur_price - lower) / (upper - lower) if upper != lower else 0.5

    signal = "HOLD"
    desc = f"价格{cur_price:.2f} 中轨{ma:.2f} 上轨{upper:.2f} 下轨{lower:.2f}"

    if bb_pos <= 0.2:
        signal = "BUY"
        desc += " 触及下轨超卖区，买入信号"
    elif bb_pos >= 0.8:
        signal = "SELL"
        desc += " 触及上轨超买区，卖出信号"
    else:
        signal = "HOLD"
        desc += " 中轨区间，持有"

    return {
        "signal": signal,
        "indicator": {
            "中轨": round(ma, 2),
            "上轨": round(upper, 2),
            "下轨": round(lower, 2),
            "带宽%": round(bb_pos * 100, 1),
        },
        "desc": desc,
    }


def _signal_momentum(prices: list[float], params: dict[str, Any]) -> dict[str, Any]:
    """动量信号: N日收益率"""
    window = params.get("momentum_window", 20)
    entry_threshold = params.get("entry_threshold", 0.005)

    if len(prices) < window + 1:
        return {
            "signal": "WAIT",
            "indicator": {},
            "desc": f"数据不足({len(prices)}/{window + 1})",
        }

    cur_price = prices[-1]
    past_price = prices[-(window + 1)]
    momentum = (cur_price - past_price) / past_price if past_price > 0 else 0

    signal = "HOLD"
    desc = f"动量({momentum:.2%}) 阈值({entry_threshold:.2%})"

    if momentum > entry_threshold:
        signal = "BUY"
        desc += " 正向动量，买入信号"
    elif momentum < -entry_threshold:
        signal = "SELL"
        desc += " 负向动量，卖出信号"
    else:
        desc += " 动量平缓，持有"

    return {
        "signal": signal,
        "indicator": {
            "动量": round(momentum * 100, 2),
            "当前价": round(cur_price, 2),
            "N日前价": round(past_price, 2),
        },
        "desc": desc,
    }


def _signal_dual_thrust(
    prices: list[float], highs: list[float], lows: list[float], params: dict[str, Any]
) -> dict[str, Any]:
    """双通道突破信号"""
    window = params.get("channel_window", 20)
    k1 = params.get("k1", 0.7)
    k2 = params.get("k2", 0.7)

    if len(prices) < window:
        return {
            "signal": "WAIT",
            "indicator": {},
            "desc": f"数据不足({len(prices)}/{window})",
        }

    hh = max(highs[-window:])
    ll = min(lows[-window:])
    range_val = hh - ll
    upper = prices[-1] - ll * k1 / window  # simplified
    # 实际 DT 用开盘价 + K1*Range 和开盘价 - K2*Range
    open_price = prices[-1]  # 近似
    buy_line = open_price + k1 * range_val
    sell_line = open_price - k2 * range_val
    cur_price = prices[-1]

    signal = "HOLD"
    desc = f"HH={hh:.2f} LL={ll:.2f} Range={range_val:.2f} 上轨={buy_line:.2f} 下轨={sell_line:.2f}"

    if cur_price > buy_line:
        signal = "BUY"
        desc += " 向上突破通道，买入信号"
    elif cur_price < sell_line:
        signal = "SELL"
        desc += " 向下突破通道，卖出信号"
    else:
        desc += " 通道内运行，持有"

    return {
        "signal": signal,
        "indicator": {
            "通道上轨": round(buy_line, 2),
            "通道下轨": round(sell_line, 2),
            "通道宽度": round(range_val, 2),
        },
        "desc": desc,
    }


# ---------------------------------------------------------------------------
# 策略注册表
# ---------------------------------------------------------------------------


def _get_strategy_params() -> list[dict[str, Any]]:
    """返回所有可用的回测策略及其参数定义"""
    return [
        {
            "class": "DualMaStrategy",
            "name": "双均线策略",
            "description": "快线上穿慢线买入，下穿卖出",
            "params": [
                {
                    "key": "fast_window",
                    "label": "快线周期",
                    "type": "int",
                    "default": 5,
                    "min": 2,
                    "max": 60,
                },
                {
                    "key": "slow_window",
                    "label": "慢线周期",
                    "type": "int",
                    "default": 20,
                    "min": 5,
                    "max": 120,
                },
            ],
        },
        {
            "class": "BollingerBandsStrategy",
            "name": "布林带策略",
            "description": "价格触及下轨买入，触及上轨卖出",
            "params": [
                {
                    "key": "ma_window",
                    "label": "均线周期",
                    "type": "int",
                    "default": 20,
                    "min": 5,
                    "max": 60,
                },
                {
                    "key": "dev_mult",
                    "label": "标准差倍数",
                    "type": "float",
                    "default": 2.0,
                    "min": 1.0,
                    "max": 4.0,
                },
            ],
        },
        {
            "class": "MomentumStrategy",
            "name": "动量策略",
            "description": "N日收益率为正且超阈值买入，为负卖出",
            "params": [
                {
                    "key": "momentum_window",
                    "label": "动量周期",
                    "type": "int",
                    "default": 20,
                    "min": 5,
                    "max": 60,
                },
                {
                    "key": "entry_threshold",
                    "label": "入场阈值(%)",
                    "type": "float",
                    "default": 0.5,
                    "min": 0.1,
                    "max": 10.0,
                },
            ],
        },
        {
            "class": "DualThrustStrategy",
            "name": "双通道突破策略",
            "description": "价格突破通道上下轨时买卖",
            "params": [
                {
                    "key": "channel_window",
                    "label": "通道周期",
                    "type": "int",
                    "default": 20,
                    "min": 5,
                    "max": 60,
                },
                {
                    "key": "k1",
                    "label": "上轨系数",
                    "type": "float",
                    "default": 0.7,
                    "min": 0.1,
                    "max": 2.0,
                },
                {
                    "key": "k2",
                    "label": "下轨系数",
                    "type": "float",
                    "default": 0.7,
                    "min": 0.1,
                    "max": 2.0,
                },
            ],
        },
    ]


def get_available_strategies() -> list[dict[str, Any]]:
    """获取可选回测策略列表（供前端下拉菜单使用）"""
    return _get_strategy_params()


def get_strategy_param_defaults(strategy_class: str) -> dict[str, Any]:
    """获取策略参数的默认值"""
    for s in _get_strategy_params():
        if s["class"] == strategy_class:
            return {p["key"]: p["default"] for p in s["params"]}
    return {}


# ---------------------------------------------------------------------------
# 信号计算主函数
# ---------------------------------------------------------------------------


def compute_position_signals(
    strategy_class: str,
    strategy_params: dict[str, Any] | None,
    positions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """为指定策略的所有持仓计算信号

    Args:
        strategy_class: 策略类名 (如 DualMaStrategy)
        strategy_params: 策略参数字典
        positions: 持仓列表, 每项包含 symbol, name, quantity, current_price

    Returns:
        每项增加 signal, indicator, signal_desc 字段
    """
    if strategy_params is None:
        strategy_params = get_strategy_param_defaults(strategy_class)

    result = []
    for pos in positions:
        symbol = pos.get("symbol", "")
        current_price = pos.get("current_price") or 0

        # 获取日线数据
        klines = _fetch_kline(symbol, days=90)
        if klines is None or len(klines) < 5:
            result.append(
                {
                    **pos,
                    "signal": "WAIT",
                    "signal_label": "数据不足",
                    "indicator": {},
                    "signal_desc": "无法获取行情数据",
                }
            )
            continue

        prices = [k["close"] for k in klines]
        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]

        # 根据策略类型计算信号
        signal_result: dict[str, Any] = {}

        if strategy_class == "DualMaStrategy":
            signal_result = _signal_dual_ma(prices, strategy_params)
        elif strategy_class == "BollingerBandsStrategy":
            signal_result = _signal_bollinger(prices, strategy_params)
        elif strategy_class == "MomentumStrategy":
            signal_result = _signal_momentum(prices, strategy_params)
        elif strategy_class == "DualThrustStrategy":
            signal_result = _signal_dual_thrust(prices, highs, lows, strategy_params)
        else:
            signal_result = {
                "signal": "HOLD",
                "indicator": {},
                "desc": "不支持的策略类型",
            }

        signal_type = signal_result.get("signal", "HOLD")
        signal_info = SIGNALS.get(signal_type, SIGNALS["HOLD"])

        result.append(
            {
                **pos,
                "signal": signal_type,
                "signal_label": signal_info["label"],
                "signal_color": signal_info["color"],
                "indicator": signal_result.get("indicator", {}),
                "signal_desc": signal_result.get("desc", ""),
            }
        )

    return result
