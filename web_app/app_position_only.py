#!/usr/bin/env python3
"""
vn.py 量化交易Web界面 - 简化版
仅提供持仓管理功能的Web应用（不需要vnpy alpha模块）
"""

from flask import Flask, render_template, jsonify
from pathlib import Path

# 导入持仓管理API蓝图
from position_api import position_bp
from analytics_api import analytics_bp
from quote_api import quote_bp

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False  # 支持中文

# 注册持仓管理蓝图
app.register_blueprint(position_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(quote_bp)

# 全局配置
LAB_PATH = "/Users/w4sh8899/project/vnpy/lab_data"
OUTPUT_PATH = "/Users/w4sh8899/project/vnpy/output"


@app.route("/")
def index():
    """主页"""
    return render_template("index.html")


@app.route("/api/strategies")
def get_strategies():
    """获取可用策略列表（简化版，仅用于前端兼容）"""
    strategies = [
        {
            "key": "dual_ma",
            "name": "双均线策略",
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
        {
            "key": "bollinger",
            "name": "布林带策略",
            "description": "触及下轨买入，触及上轨卖出",
            "params": {
                "ma_window": {
                    "name": "均线周期",
                    "type": "int",
                    "default": 20,
                    "min": 5,
                    "max": 50,
                },
            },
        },
    ]
    return jsonify({"strategies": strategies})


@app.route("/api/backtest", methods=["POST"])
def run_backtest():
    """回测接口（简化版，仅用于前端兼容）"""
    return jsonify(
        {
            "success": False,
            "error": "完整版回测功能需要vnpy alpha模块支持，当前为简化版",
        }
    )


@app.route("/api/pick_stocks", methods=["POST"])
def pick_stocks():
    """选股接口（简化版，仅用于前端兼容）"""
    return jsonify(
        {
            "success": False,
            "error": "完整版选股功能需要vnpy alpha模块支持，当前为简化版",
        }
    )


@app.route("/api/compare_strategies", methods=["POST"])
def compare_strategies():
    """策略对比接口（简化版，仅用于前端兼容）"""
    return jsonify(
        {
            "success": False,
            "error": "完整版策略对比需要vnpy alpha模块支持，当前为简化版",
        }
    )


if __name__ == "__main__":
    # 创建模板目录
    template_dir = Path(__file__).parent / "templates"
    template_dir.mkdir(exist_ok=True)

    # 创建静态文件目录
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)

    print("启动vn.py量化交易Web界面（简化版 - 仅持仓管理）...")
    print("请访问: http://localhost:5001")
    print("注意：回测、选股等功能需要完整版vnpy环境")
    app.run(debug=True, host="0.0.0.0", port=5001)
