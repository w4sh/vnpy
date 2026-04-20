"""
安全工具函数
提供输入验证、数据清理等安全相关功能
"""

import re
from typing import Optional


# 输入长度限制
MAX_STRING_LENGTH = 1000
MAX_REASON_LENGTH = 500
MAX_DESCRIPTION_LENGTH = 2000
MAX_NAME_LENGTH = 100


def validate_string_length(
    value: Optional[str], max_length: int, field_name: str
) -> tuple[bool, Optional[str]]:
    """验证字符串长度

    Args:
        value: 待验证的字符串
        max_length: 最大允许长度
        field_name: 字段名称（用于错误消息）

    Returns:
        (是否有效, 错误消息)
    """
    if value is None:
        return True, None

    if len(value) > max_length:
        return False, f"{field_name}长度不能超过{max_length}个字符"

    return True, None


def validate_stock_symbol(symbol: str) -> tuple[bool, Optional[str]]:
    """验证股票代码格式

    支持格式：
    - 000001.SZSE (深交所)
    - 600000.SHSE (上交所)

    Args:
        symbol: 股票代码

    Returns:
        (是否有效, 错误消息)
    """
    if not symbol:
        return False, "股票代码不能为空"

    # 基本格式验证：6位数字.交易所代码
    pattern = r"^\d{6}\.(SZSE|SHSE)$"
    if not re.match(pattern, symbol):
        return False, "股票代码格式错误，应为6位数字.交易所代码（如000001.SZSE）"

    return True, None


def sanitize_text(text: str) -> str:
    """清理文本输入

    去除危险字符，防止XSS和注入攻击

    Args:
        text: 待清理的文本

    Returns:
        清理后的文本
    """
    if not text:
        return text

    # 去除控制字符（保留换行和制表符）
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)

    # 去除多余的空白字符
    text = " ".join(text.split())

    return text


def validate_positive_number(value, field_name: str) -> tuple[bool, Optional[str]]:
    """验证正数

    Args:
        value: 待验证的数值
        field_name: 字段名称

    Returns:
        (是否有效, 错误消息)
    """
    try:
        num_value = float(value)
        if num_value <= 0:
            return False, f"{field_name}必须大于0"
        return True, None
    except (ValueError, TypeError):
        return False, f"{field_name}必须是有效的数字"


def validate_non_negative_number(value, field_name: str) -> tuple[bool, Optional[str]]:
    """验证非负数

    Args:
        value: 待验证的数值
        field_name: 字段名称

    Returns:
        (是否有效, 错误消息)
    """
    try:
        num_value = float(value)
        if num_value < 0:
            return False, f"{field_name}不能为负数"
        return True, None
    except (ValueError, TypeError):
        return False, f"{field_name}必须是有效的数字"


def validate_transaction_type(transaction_type: str) -> tuple[bool, Optional[str]]:
    """验证交易类型

    Args:
        transaction_type: 交易类型

    Returns:
        (是否有效, 错误消息)
    """
    valid_types = ["buy", "sell", "dividend", "bonus"]
    if transaction_type not in valid_types:
        return False, f"交易类型必须是以下之一: {', '.join(valid_types)}"
    return True, None


def validate_strategy_status(status: str) -> tuple[bool, Optional[str]]:
    """验证策略状态

    Args:
        status: 策略状态

    Returns:
        (是否有效, 错误消息)
    """
    valid_statuses = ["active", "deleted"]
    if status not in valid_statuses:
        return False, f"策略状态必须是以下之一: {', '.join(valid_statuses)}"
    return True, None


def validate_position_status(status: str) -> tuple[bool, Optional[str]]:
    """验证持仓状态

    Args:
        status: 持仓状态

    Returns:
        (是否有效, 错误消息)
    """
    valid_statuses = ["holding", "sold"]
    if status not in valid_statuses:
        return False, f"持仓状态必须是以下之一: {', '.join(valid_statuses)}"
    return True, None
