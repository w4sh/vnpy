#!/usr/bin/env python3
"""
实时行情API蓝图
提供价格更新、行情查询等功能
"""

from flask import Blueprint, request, jsonify
from data_feed.quote_service import get_quote_service
from data_feed.update_prices import update_position_prices
from models import Position, get_db_session
from datetime import datetime
import traceback

# 创建蓝图
quote_bp = Blueprint("quote", __name__, url_prefix="/api/quote")

# Tushare Token (用户提供的120积分账户)
TUSHARE_TOKEN = "8338d9ae4c26c3ec32cffbd1b337d97228c22ba84cea0996410513bb"


@quote_bp.route("/update", methods=["POST"])
def update_prices():
    """更新所有持仓的当前价格"""
    try:
        # 执行更新
        update_position_prices(TUSHARE_TOKEN, dry_run=False)

        return jsonify(
            {
                "success": True,
                "message": "价格更新成功",
                "update_time": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@quote_bp.route("/quote/<symbol>", methods=["GET"])
def get_quote(symbol):
    """获取单个标的的实时行情"""
    try:
        quote_service = get_quote_service(TUSHARE_TOKEN)

        # 判断是股票还是期货
        if (
            ".CF" in symbol.upper()
            or ".SH" in symbol.upper()
            or ".SZ" in symbol.upper()
        ):
            quote = quote_service.get_stock_quote(symbol)
        else:
            quote = quote_service.get_futures_quote(symbol)

        if quote:
            return jsonify({"success": True, "quote": quote})
        else:
            return jsonify({"success": False, "error": "未找到行情数据"}), 404

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@quote_bp.route("/usage", methods=["GET"])
def get_usage():
    """获取API使用情况"""
    try:
        quote_service = get_quote_service(TUSHARE_TOKEN)
        usage = quote_service.get_usage_info()

        return jsonify({"success": True, "usage": usage})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@quote_bp.route("/test", methods=["GET"])
def test_connection():
    """测试Tushare连接"""
    try:
        quote_service = get_quote_service(TUSHARE_TOKEN)

        # 尝试获取一个测试标的的数据
        test_quote = quote_service.get_stock_quote("000001.SZ")  # 平安银行

        if test_quote:
            return jsonify(
                {
                    "success": True,
                    "message": "连接成功",
                    "test_quote": test_quote,
                    "usage": quote_service.get_usage_info(),
                }
            )
        else:
            return jsonify({"success": False, "error": "无法获取测试数据"}), 500

    except Exception as e:
        error_detail = traceback.format_exc()
        return jsonify(
            {"success": False, "error": f"连接失败: {str(e)}", "detail": error_detail}
        ), 500
