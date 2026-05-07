#!/usr/bin/env python3
"""
vn.py 量化交易Web界面
提供策略回测和选股功能的Web应用
"""

import sys
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify
import numpy as np

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from vnpy.trader.constant import Interval
from vnpy.alpha.strategy.backtesting import BacktestingEngine
from vnpy.alpha import AlphaLab

# 导入策略
from scripts.dual_ma_strategy import DualMaStrategy
from scripts.dual_thrust_strategy import DualThrustStrategy
from scripts.bollinger_bands_strategy import BollingerBandsStrategy
from scripts.momentum_strategy import MomentumStrategy
from scripts.advanced_bollinger_picker import AdvancedBollingerPicker

# 导入股票名称映射
from web_app.stock_names import format_stock_symbol, get_stock_name
from web_app.models import CandidateStock, Position, get_db_session

# 导入持仓管理API蓝图
from web_app.position_api import position_bp

# 导入策略API蓝图
from web_app.strategy_api import strategy_bp

# 导入数据分析API蓝图
from web_app.analytics_api import analytics_bp

# 导入前瞻因子API蓝图
from web_app.factor_api import factor_bp

# 导入因子评估API蓝图
from web_app.evaluation_api import eval_bp

# 导入投资组合推荐API蓝图
from web_app.recommendation_api import recommendation_bp

# 导入ETF推荐API蓝图
from web_app.etf_recommendation_api import etf_recommendation_bp

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False  # 支持中文

# 注册持仓管理蓝图
app.register_blueprint(position_bp)
# 注册策略管理蓝图
app.register_blueprint(strategy_bp)
# 注册数据分析蓝图
app.register_blueprint(analytics_bp)
# 注册前瞻因子蓝图
app.register_blueprint(factor_bp)
# 注册因子评估蓝图
app.register_blueprint(eval_bp)
# 注册投资组合推荐蓝图
app.register_blueprint(recommendation_bp)
# 注册ETF推荐蓝图
app.register_blueprint(etf_recommendation_bp)

# 全局配置
LAB_PATH = "/Users/w4sh8899/project/vnpy/lab_data"
OUTPUT_PATH = "/Users/w4sh8899/project/vnpy/output"

# 可用策略定义
AVAILABLE_STRATEGIES = {
    "dual_ma": {
        "name": "双均线策略",
        "class": DualMaStrategy,
        "description": "快线上穿慢线买入，下穿卖出",
        "params": {
            "fast_window": {
                "name": "快线周期",
                "type": "int",
                "default": 5,
                "min": 3,
                "max": 30,
            },
            "slow_window": {
                "name": "慢线周期",
                "type": "int",
                "default": 20,
                "min": 10,
                "max": 60,
            },
        },
    },
    "dual_thrust": {
        "name": "Dual Thrust策略",
        "class": DualThrustStrategy,
        "description": "突破上轨做多，突破下轨做空",
        "params": {
            "k1": {
                "name": "上轨系数",
                "type": "float",
                "default": 0.3,
                "min": 0.1,
                "max": 1.0,
            },
            "k2": {
                "name": "下轨系数",
                "type": "float",
                "default": 0.3,
                "min": 0.1,
                "max": 1.0,
            },
            "init_days": {
                "name": "初始化天数",
                "type": "int",
                "default": 10,
                "min": 5,
                "max": 30,
            },
        },
    },
    "bollinger": {
        "name": "布林带策略",
        "class": BollingerBandsStrategy,
        "description": "触及下轨买入，触及上轨卖出",
        "params": {
            "ma_window": {
                "name": "均线周期",
                "type": "int",
                "default": 20,
                "min": 5,
                "max": 50,
            },
            "std_window": {
                "name": "标准差周期",
                "type": "int",
                "default": 20,
                "min": 5,
                "max": 50,
            },
            "dev_mult": {
                "name": "标准差倍数",
                "type": "float",
                "default": 2.0,
                "min": 1.0,
                "max": 3.0,
            },
            "init_days": {
                "name": "初始化天数",
                "type": "int",
                "default": 30,
                "min": 10,
                "max": 60,
            },
        },
    },
    "momentum": {
        "name": "动量策略",
        "class": MomentumStrategy,
        "description": "正动量买入，负动量卖出",
        "params": {
            "momentum_window": {
                "name": "动量周期",
                "type": "int",
                "default": 20,
                "min": 5,
                "max": 50,
            },
            "entry_threshold": {
                "name": "入场阈值",
                "type": "float",
                "default": 0.005,
                "min": 0.001,
                "max": 0.05,
            },
            "exit_threshold": {
                "name": "出场阈值",
                "type": "float",
                "default": -0.003,
                "min": -0.05,
                "max": -0.001,
            },
            "init_days": {
                "name": "初始化天数",
                "type": "int",
                "default": 30,
                "min": 10,
                "max": 60,
            },
        },
    },
}


def convert_numpy_types(obj):
    """转换numpy类型为Python原生类型，用于JSON序列化"""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    return obj


# 选股策略定义
PICKER_STRATEGIES = {
    "oversold": {"name": "超卖策略", "description": "价格触及下轨，买入机会"},
    "overbought": {"name": "超买策略", "description": "价格触及上轨，卖出机会"},
    "breakout_up": {"name": "向上突破", "description": "强势突破买入"},
    "breakout_down": {"name": "向下突破", "description": "强势突破卖出"},
    "squeeze": {"name": "布林带收缩", "description": "波动率低，即将突破"},
}


@app.route("/")
def index():
    """主页"""
    return render_template("index.html")


@app.route("/api/strategies")
def get_strategies():
    """获取可用策略列表"""
    strategies = []
    for key, config in AVAILABLE_STRATEGIES.items():
        strategy_info = {
            "key": key,
            "name": config["name"],
            "description": config["description"],
            "params": config["params"],
        }
        strategies.append(strategy_info)

    return jsonify({"strategies": strategies})


@app.route("/api/backtest", methods=["POST"])
def run_backtest():
    """运行回测"""
    try:
        data = request.json
        strategies_config = data.get("strategies", [])
        symbols = data.get("symbols", ["000001.SZSE"])
        start_date = datetime.strptime(data.get("start_date", "2020-01-01"), "%Y-%m-%d")
        end_date = datetime.strptime(data.get("end_date", "2025-01-01"), "%Y-%m-%d")
        capital = int(data.get("capital", 1000000))

        results = []

        for strategy_config in strategies_config:
            strategy_key = strategy_config.get("key")
            params = strategy_config.get("params", {})

            if strategy_key not in AVAILABLE_STRATEGIES:
                continue

            strategy_class = AVAILABLE_STRATEGIES[strategy_key]["class"]

            # 运行回测
            lab = AlphaLab(LAB_PATH)
            engine = BacktestingEngine(lab)

            engine.set_parameters(
                vt_symbols=symbols,
                interval=Interval.DAILY,
                start=start_date,
                end=end_date,
                capital=capital,
            )

            import polars as pl

            signal_df = pl.DataFrame({"datetime": [], "vt_symbol": [], "signal": []})
            engine.add_strategy(strategy_class, params, signal_df)

            try:
                engine.load_data()
                engine.run_backtesting()
                engine.calculate_result()
                stats = engine.calculate_statistics()

                result = {
                    "strategy": AVAILABLE_STRATEGIES[strategy_key]["name"],
                    "total_return": stats.get("total_return", 0),
                    "annual_return": stats.get("annual_return", 0),
                    "max_ddpercent": stats.get("max_ddpercent", 0),
                    "sharpe_ratio": stats.get("sharpe_ratio", 0),
                    "total_trades": stats.get("total_trade_count", 0),
                }
                # 转换numpy类型为Python原生类型
                result = convert_numpy_types(result)
                results.append(result)

            except Exception as e:
                results.append(
                    {
                        "strategy": AVAILABLE_STRATEGIES[strategy_key]["name"],
                        "error": str(e),
                    }
                )

        return jsonify({"success": True, "results": results})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/pick_stocks", methods=["POST"])
def pick_stocks():
    """选股接口"""
    try:
        data = request.json
        strategy = data.get("strategy", "oversold")
        top_n = int(data.get("top_n", 20))
        min_price = float(data.get("min_price", 5.0))
        max_price = float(data.get("max_price", 200.0))
        min_volume = int(data.get("min_volume", 5000000))
        ma_window = int(data.get("ma_window", 20))
        std_window = int(data.get("std_window", 20))
        dev_mult = float(data.get("dev_mult", 2.0))

        picker = AdvancedBollingerPicker(LAB_PATH)

        results = picker.scan_with_strategy(
            strategy=strategy,
            ma_window=ma_window,
            std_window=std_window,
            dev_mult=dev_mult,
            min_price=min_price,
            max_price=max_price,
            min_volume=min_volume,
            top_n=top_n,
        )

        formatted_results = []
        for stock in results:
            # 格式化股票显示为中文名称(代码)
            formatted_symbol = format_stock_symbol(stock["vt_symbol"])

            formatted_results.append(
                {
                    "symbol": formatted_symbol,  # 使用格式化后的显示
                    "raw_symbol": stock["vt_symbol"],  # 保留原始代码用于后续处理
                    "price": stock["close_price"],
                    "volume": stock["volume"],
                    "bb_position": stock["bb_position"],
                    "upper_band": stock["upper_band"],
                    "middle_band": stock["middle_band"],
                    "lower_band": stock["lower_band"],
                    "bb_width": stock["bb_width"],
                    "score": stock["score"],
                }
            )

        return jsonify({"success": True, "results": formatted_results})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/compare_strategies", methods=["POST"])
def compare_strategies():
    """策略对比接口"""
    try:
        data = request.json
        strategy_keys = data.get("strategies", ["dual_ma", "bollinger"])
        symbols = data.get(
            "symbols",
            ["000001.SZSE", "000002.SZSE", "600000.SSE", "600036.SSE", "601318.SSE"],
        )
        start_date = datetime.strptime(data.get("start_date", "2020-01-01"), "%Y-%m-%d")
        end_date = datetime.strptime(data.get("end_date", "2025-01-01"), "%Y-%m-%d")

        results = []

        for strategy_key in strategy_keys:
            if strategy_key not in AVAILABLE_STRATEGIES:
                continue

            strategy_config = AVAILABLE_STRATEGIES[strategy_key]
            strategy_class = strategy_config["class"]

            # 使用默认参数
            params = {}
            for param_key, param_config in strategy_config["params"].items():
                params[param_key] = param_config["default"]

            # 运行回测
            lab = AlphaLab(LAB_PATH)
            engine = BacktestingEngine(lab)

            engine.set_parameters(
                vt_symbols=symbols,
                interval=Interval.DAILY,
                start=start_date,
                end=end_date,
                capital=1000000,
            )

            import polars as pl

            signal_df = pl.DataFrame({"datetime": [], "vt_symbol": [], "signal": []})
            engine.add_strategy(strategy_class, params, signal_df)

            try:
                engine.load_data()
                engine.run_backtesting()
                engine.calculate_result()
                stats = engine.calculate_statistics()

                result_dict = {
                    "strategy": strategy_config["name"],
                    "total_return": stats.get("total_return", 0),
                    "annual_return": stats.get("annual_return", 0),
                    "max_ddpercent": stats.get("max_ddpercent", 0),
                    "sharpe_ratio": stats.get("sharpe_ratio", 0),
                    "total_trades": stats.get("total_trade_count", 0),
                }
                # 转换numpy类型为Python原生类型
                result_dict = convert_numpy_types(result_dict)
                results.append(result_dict)

            except Exception as e:
                results.append({"strategy": strategy_config["name"], "error": str(e)})

        return jsonify({"success": True, "results": results})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/candidates/latest")
def get_latest_candidates():
    """获取最近一次候选股推荐结果"""
    session = None
    try:
        session = get_db_session()

        latest_date_row = (
            session.query(CandidateStock.screening_date)
            .order_by(CandidateStock.screening_date.desc())
            .first()
        )

        if not latest_date_row:
            return jsonify(
                {
                    "success": True,
                    "screening_date": None,
                    "count": 0,
                    "candidates": [],
                    "message": "暂无候选股推荐数据，请在交易日收盘后运行筛选",
                }
            )

        screening_date = latest_date_row[0].strftime("%Y-%m-%d")

        # 获取当前持仓，用于标记已持有股票
        held_symbols = {
            p.symbol
            for p in session.query(Position.symbol).filter(Position.status == "holding")
        }

        latest = (
            session.query(CandidateStock)
            .filter(CandidateStock.screening_date == latest_date_row[0])
            .order_by(
                CandidateStock.combined_score.desc(),
                CandidateStock.total_return.desc(),
                CandidateStock.sharpe_ratio.desc(),
            )
            .all()
        )

        candidates = []
        for c in latest:
            candidates.append(
                {
                    "rank": c.rank,
                    "symbol": c.symbol,
                    "name": c.name or get_stock_name(c.symbol),
                    "is_held": c.symbol in held_symbols,
                    "score": float(c.score) if c.score else 0,
                    "technical_score": float(c.technical_score)
                    if c.technical_score
                    else 0,
                    "performance_score": float(c.performance_score)
                    if c.performance_score
                    else 0,
                    "combined_score": float(c.combined_score)
                    if c.combined_score
                    else 0,
                    "momentum_score": float(c.momentum_score)
                    if c.momentum_score
                    else 0,
                    "trend_score": float(c.trend_score) if c.trend_score else 0,
                    "volume_score": float(c.volume_score) if c.volume_score else 0,
                    "volatility_score": float(c.volatility_score)
                    if c.volatility_score
                    else 0,
                    "current_price": float(c.current_price) if c.current_price else 0,
                    "total_return": float(c.total_return) if c.total_return else 0,
                    "max_drawdown": float(c.max_drawdown) if c.max_drawdown else 0,
                    "sharpe_ratio": float(c.sharpe_ratio) if c.sharpe_ratio else 0,
                }
            )

        return jsonify(
            {
                "success": True,
                "screening_date": screening_date,
                "count": len(candidates),
                "candidates": candidates,
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        if session:
            session.close()


@app.route("/api/candidates/dates")
def get_candidate_dates():
    """获取所有有候选股数据的日期列表"""
    session = None
    try:
        session = get_db_session()
        rows = (
            session.query(CandidateStock.screening_date)
            .distinct()
            .order_by(CandidateStock.screening_date.desc())
            .all()
        )
        dates = [r[0].strftime("%Y-%m-%d") for r in rows if r[0]]
        return jsonify({"success": True, "dates": dates, "count": len(dates)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        if session:
            session.close()


@app.route("/api/candidates/history")
def get_candidates_history():
    """查询指定日期的候选股历史记录"""
    session = None
    try:
        date_str = request.args.get("date", "")
        session = get_db_session()

        # 获取当前持仓，用于标记已持有股票
        held_symbols = {p.symbol for p in session.query(Position.symbol).filter(Position.status == "holding")}

        query = session.query(CandidateStock).order_by(
            CandidateStock.combined_score.desc(),
            CandidateStock.total_return.desc(),
            CandidateStock.sharpe_ratio.desc(),
        )

        if date_str:
            from datetime import datetime as dt

            target_date = dt.strptime(date_str, "%Y-%m-%d").date()
            query = query.filter(CandidateStock.screening_date == target_date)

        candidates = query.all()

        # 按日期分组
        results_by_date: dict = {}
        for c in candidates:
            d = c.screening_date.strftime("%Y-%m-%d")
            if d not in results_by_date:
                results_by_date[d] = []
            results_by_date[d].append(
                {
                    "rank": c.rank,
                    "symbol": c.symbol,
                    "name": c.name or get_stock_name(c.symbol),
                    "is_held": c.symbol in held_symbols,
                    "score": float(c.score) if c.score else 0,
                    "technical_score": float(c.technical_score)
                    if c.technical_score
                    else 0,
                    "performance_score": float(c.performance_score)
                    if c.performance_score
                    else 0,
                    "combined_score": float(c.combined_score)
                    if c.combined_score
                    else 0,
                    "momentum_score": float(c.momentum_score)
                    if c.momentum_score
                    else 0,
                    "trend_score": float(c.trend_score) if c.trend_score else 0,
                    "volume_score": float(c.volume_score) if c.volume_score else 0,
                    "volatility_score": float(c.volatility_score)
                    if c.volatility_score
                    else 0,
                    "current_price": float(c.current_price) if c.current_price else 0,
                    "total_return": float(c.total_return) if c.total_return else 0,
                    "max_drawdown": float(c.max_drawdown) if c.max_drawdown else 0,
                    "sharpe_ratio": float(c.sharpe_ratio) if c.sharpe_ratio else 0,
                }
            )

        return jsonify({"success": True, "results": results_by_date})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        if session:
            session.close()


@app.route("/position_management")
def position_management():
    """持仓管理页面"""
    return render_template("position_overview.html")


@app.route("/etf_overview")
def etf_overview():
    """ETF 推荐面板"""
    return render_template("etf_overview.html")


if __name__ == "__main__":
    # 创建模板目录
    template_dir = Path(__file__).parent / "templates"
    template_dir.mkdir(exist_ok=True)

    # 创建静态文件目录
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)

    print("启动vn.py量化交易Web界面...")
    print("请访问: http://localhost:5001")
    app.run(debug=True, host="0.0.0.0", port=5001)
