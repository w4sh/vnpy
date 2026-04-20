#!/usr/bin/env python3
"""
用于集成测试的简化Flask应用
只包含持仓管理相关的blueprint，不依赖vnpy alpha模块
"""

from flask import Flask
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 导入持仓管理API蓝图
from web_app.position_api import position_bp
from web_app.strategy_api import strategy_bp
from web_app.analytics_api import analytics_bp

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False  # 支持中文
app.config["TESTING"] = True  # 测试模式

# 注册蓝图
app.register_blueprint(position_bp)
app.register_blueprint(strategy_bp)
app.register_blueprint(analytics_bp)


# 添加持仓管理页面路由（简单返回用于测试）
@app.route("/position_management")
def position_management():
    return """
    <!DOCTYPE html>
    <html><head><title>持仓管理</title></head>
    <body><h1>持仓概览 - vn.py量化交易平台</h1></body>
    </html>
    """


@app.route("/")
def index():
    return """
    <!DOCTYPE html>
    <html><head><title>vn.py量化交易平台</title></head>
    <body><h1>vn.py 量化交易系统</h1></body>
    </html>
    """


if __name__ == "__main__":
    print("🚀 启动测试用Flask应用...")
    print("📍 持仓管理: http://localhost:5001/position_management")
    print("📍 API端点:")
    print("   - GET  /api/positions")
    print("   - GET  /api/strategies")
    print("   - GET  /api/analytics/portfolio")
    print("   - POST /api/strategies")
    print("   - PUT  /api/strategies/<id>")
    print("   - DELETE /api/strategies/<id>")
    print("   - PUT  /api/positions/transactions/<id>")
    app.run(debug=False, host="0.0.0.0", port=5001)
