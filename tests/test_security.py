"""测试安全工具函数"""

import pytest
from web_app.security import (
    validate_string_length,
    validate_stock_symbol,
    sanitize_text,
    validate_positive_number,
    validate_non_negative_number,
    validate_transaction_type,
    validate_strategy_status,
    validate_position_status,
    MAX_STRING_LENGTH,
    MAX_REASON_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_NAME_LENGTH,
)


class TestStringLengthValidation:
    """测试字符串长度验证"""

    def test_valid_string_length(self):
        """测试：正常长度字符串"""
        valid, error = validate_string_length("正常文本", MAX_STRING_LENGTH, "测试字段")
        assert valid is True
        assert error is None

    def test_exceeds_max_length(self):
        """测试：超长字符串"""
        long_text = "a" * (MAX_STRING_LENGTH + 1)
        valid, error = validate_string_length(long_text, MAX_STRING_LENGTH, "测试字段")
        assert valid is False
        assert "长度不能超过" in error

    def test_none_value(self):
        """测试：None值"""
        valid, error = validate_string_length(None, MAX_STRING_LENGTH, "测试字段")
        assert valid is True
        assert error is None

    def test_empty_string(self):
        """测试：空字符串"""
        valid, error = validate_string_length("", MAX_STRING_LENGTH, "测试字段")
        assert valid is True
        assert error is None


class TestStockSymbolValidation:
    """测试股票代码验证"""

    def test_valid_szse_symbol(self):
        """测试：有效的深交所代码"""
        valid, error = validate_stock_symbol("000001.SZSE")
        assert valid is True
        assert error is None

    def test_valid_shse_symbol(self):
        """测试：有效的上交所代码"""
        valid, error = validate_stock_symbol("600000.SHSE")
        assert valid is True
        assert error is None

    def test_empty_symbol(self):
        """测试：空代码"""
        valid, error = validate_stock_symbol("")
        assert valid is False
        assert error == "股票代码不能为空"

    def test_invalid_format(self):
        """测试：无效格式"""
        valid, error = validate_stock_symbol("INVALID")
        assert valid is False
        assert "格式错误" in error

    def test_wrong_exchange(self):
        """测试：错误的交易所代码"""
        valid, error = validate_stock_symbol("000001.NASDAQ")
        assert valid is False
        assert "格式错误" in error


class TestTextSanitization:
    """测试文本清理"""

    def test_normal_text(self):
        """测试：正常文本"""
        text = "这是正常文本"
        result = sanitize_text(text)
        assert result == text

    def test_text_with_control_chars(self):
        """测试：包含控制字符的文本"""
        text = "文本\x00包含\x01控制\x02字符"
        result = sanitize_text(text)
        assert "\x00" not in result
        assert "\x01" not in result
        assert "文本 包含 控制字符" == result

    def test_text_with_extra_spaces(self):
        """测试：多余空格"""
        text = "文本   包含   多余   空格"
        result = sanitize_text(text)
        assert result == "文本 包含 多余 空格"

    def test_empty_text(self):
        """测试：空文本"""
        result = sanitize_text("")
        assert result == ""

    def test_none_text(self):
        """测试：None"""
        result = sanitize_text(None)
        assert result is None


class TestNumberValidation:
    """测试数值验证"""

    def test_valid_positive_number(self):
        """测试：有效的正数"""
        valid, error = validate_positive_number(10.5, "测试字段")
        assert valid is True
        assert error is None

    def test_zero_is_not_positive(self):
        """测试：0不是正数"""
        valid, error = validate_positive_number(0, "测试字段")
        assert valid is False
        assert "必须大于0" in error

    def test_negative_number(self):
        """测试：负数"""
        valid, error = validate_positive_number(-5, "测试字段")
        assert valid is False
        assert "必须大于0" in error

    def test_valid_non_negative(self):
        """测试：有效的非负数"""
        valid, error = validate_non_negative_number(0, "测试字段")
        assert valid is True
        assert error is None

    def test_negative_is_not_non_negative(self):
        """测试：负数不是非负数"""
        valid, error = validate_non_negative_number(-5, "测试字段")
        assert valid is False
        assert "不能为负数" in error


class TestTransactionTypeValidation:
    """测试交易类型验证"""

    def test_valid_buy(self):
        """测试：有效的买入类型"""
        valid, error = validate_transaction_type("buy")
        assert valid is True
        assert error is None

    def test_valid_sell(self):
        """测试：有效的卖出类型"""
        valid, error = validate_transaction_type("sell")
        assert valid is True
        assert error is None

    def test_valid_dividend(self):
        """测试：有效的分红类型"""
        valid, error = validate_transaction_type("dividend")
        assert valid is True
        assert error is None

    def test_valid_bonus(self):
        """测试：有效的送股类型"""
        valid, error = validate_transaction_type("bonus")
        assert valid is True
        assert error is None

    def test_invalid_type(self):
        """测试：无效类型"""
        valid, error = validate_transaction_type("invalid")
        assert valid is False
        assert "必须是以下之一" in error


class TestStrategyStatusValidation:
    """测试策略状态验证"""

    def test_valid_active(self):
        """测试：有效的活跃状态"""
        valid, error = validate_strategy_status("active")
        assert valid is True
        assert error is None

    def test_valid_deleted(self):
        """测试：有效的删除状态"""
        valid, error = validate_strategy_status("deleted")
        assert valid is True
        assert error is None

    def test_invalid_status(self):
        """测试：无效状态"""
        valid, error = validate_strategy_status("invalid")
        assert valid is False
        assert "必须是以下之一" in error


class TestPositionStatusValidation:
    """测试持仓状态验证"""

    def test_valid_holding(self):
        """测试：有效的持有状态"""
        valid, error = validate_position_status("holding")
        assert valid is True
        assert error is None

    def test_valid_sold(self):
        """测试：有效的卖出状态"""
        valid, error = validate_position_status("sold")
        assert valid is True
        assert error is None

    def test_invalid_status(self):
        """测试：无效状态"""
        valid, error = validate_position_status("invalid")
        assert valid is False
        assert "必须是以下之一" in error
