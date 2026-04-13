"""
Unit tests for vnpy.trader.object module.

Demonstrates how to write unit tests for vnpy core modules.
"""

import pytest
from datetime import datetime
from vnpy.trader.object import (
    TickData,
    OrderData,
    TradeData,
    PositionData,
    AccountData,
    ContractData,
)


class TestTickData:
    """测试 TickData 对象"""

    def test_create_tick(self):
        """测试创建 TickData 对象"""
        tick = TickData(
            gateway_name="CTP",
            symbol="IF2501",
            exchange="CFFEX",
            datetime=datetime(2025, 1, 10, 9, 30, 0),
            name="沪深300指数2501",
            last_price=3500.0,
            volume=1234,
            open_interest=5678,
        )

        assert tick.symbol == "IF2501"
        assert tick.exchange.value == "CFFEX"
        assert tick.last_price == 3500.0
        assert tick.volume == 1234

    def test_tick_vt_symbol(self):
        """测试 vt_symbol 属性"""
        tick = TickData(
            gateway_name="CTP",
            symbol="IF2501",
            exchange="CFFEX",
            datetime=datetime.now(),
        )

        assert tick.vt_symbol == "IF2501.CFFEX"


class TestOrderData:
    """测试 OrderData 对象"""

    def test_create_order(self):
        """测试创建 OrderData 对象"""
        order = OrderData(
            gateway_name="CTP",
            symbol="IF2501",
            exchange="CFFEX",
            orderID="12345",
            direction="LONG",
            offset="OPEN",
            price=3500.0,
            volume=1,
            status="NOTTRADED",
        )

        assert order.symbol == "IF2501"
        assert order.direction.value == "LONG"
        assert order.status.value == "NOTTRADED"

    def test_order_vt_symbol(self):
        """测试 vt_symbol 属性"""
        order = OrderData(
            gateway_name="CTP",
            symbol="IF2501",
            exchange="CFFEX",
            orderID="12345",
        )

        assert order.vt_symbol == "IF2501.CFFEX"
        assert order.vt_orderid == "CTP.12345"


class TestPositionData:
    """测试 PositionData 对象"""

    def test_create_position(self):
        """测试创建 PositionData 对象"""
        position = PositionData(
            gateway_name="CTP",
            symbol="IF2501",
            exchange="CFFEX",
            direction="LONG",
            volume=10,
            price=3500.0,
            pnl=1000.0,
        )

        assert position.symbol == "IF2501"
        assert position.direction.value == "LONG"
        assert position.volume == 10

    def test_position_vt_symbol(self):
        """测试 vt_position_name 属性"""
        position = PositionData(
            gateway_name="CTP",
            symbol="IF2501",
            exchange="CFFEX",
            direction="LONG",
        )

        assert position.vt_symbol == "IF2501.CFFEX"
        assert position.vt_position_name == "IF2501.CFFEX.LONG"


@pytest.mark.unit
class TestContractData:
    """测试 ContractData 对象"""

    def test_create_contract(self):
        """测试创建 ContractData 对象"""
        contract = ContractData(
            gateway_name="CTP",
            symbol="IF2501",
            exchange="CFFEX",
            name="沪深300指数2501",
            product="期货",
            size=200,
            pricetick=0.2,
            min_volume=1,
        )

        assert contract.symbol == "IF2501"
        assert contract.size == 200
        assert contract.pricetick == 0.2


@pytest.mark.integration
class TestDataIntegration:
    """集成测试示例"""

    def test_tick_to_order_conversion(self):
        """测试从 TickData 生成订单的逻辑"""
        tick = TickData(
            gateway_name="CTP",
            symbol="IF2501",
            exchange="CFFEX",
            datetime=datetime.now(),
            last_price=3500.0,
            ask_price_1=3500.2,
            bid_price_1=3499.8,
        )

        # 假设的买入逻辑:使用卖价买入
        buy_price = tick.ask_price_1
        assert buy_price == 3500.2

        # 假设的卖出逻辑:使用买价卖出
        sell_price = tick.bid_price_1
        assert sell_price == 3499.8
