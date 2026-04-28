"""
图表配置Schema定义
支持多种图表类型和数据源配置
"""

from typing import Any
from enum import Enum
from datetime import datetime


class ChartType(str, Enum):
    """图表类型枚举"""

    LINE = "line"  # 折线图
    BAR = "bar"  # 柱状图
    PIE = "pie"  # 饼图
    AREA = "area"  # 面积图
    SCATTER = "scatter"  # 散点图


class DataSourceType(str, Enum):
    """数据源类型枚举"""

    POSITIONS = "positions"  # 持仓数据
    STRATEGY = "strategy"  # 策略数据
    TRANSACTION = "transaction"  # 交易数据
    CUSTOM = "custom"  # 自定义数据


class AxisConfig:
    """坐标轴配置"""

    def __init__(
        self,
        title: str = "",
        visible: bool = True,
        format: str = "number",  # number, percent, currency, date
        position: str = "left",  # left, right, top, bottom
    ):
        self.title = title
        self.visible = visible
        self.format = format
        self.position = position

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "visible": self.visible,
            "format": self.format,
            "position": self.position,
        }


class SeriesConfig:
    """数据系列配置"""

    def __init__(
        self,
        name: str,
        data_key: str,  # 数据字段key
        chart_type: str,  # 图表类型
        color: str = "#36A2EB",  # 颜色
        y_axis_id: str = "y",  # Y轴ID（多轴图表）
        visible: bool = True,
    ):
        self.name = name
        self.data_key = data_key
        self.chart_type = chart_type
        self.color = color
        self.y_axis_id = y_axis_id
        self.visible = visible

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "data_key": self.data_key,
            "chart_type": self.chart_type,
            "color": self.color,
            "y_axis_id": self.y_axis_id,
            "visible": self.visible,
        }


class ChartConfig:
    """图表配置主类"""

    def __init__(
        self,
        id: str,
        name: str,
        chart_type: ChartType,
        data_source: DataSourceType,
        series: list[SeriesConfig],
        title: str = "",
        x_axis: AxisConfig | None = None,
        y_axis: AxisConfig | None = None,
        options: dict[str, Any] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        self.id = id
        self.name = name
        self.chart_type = chart_type
        self.data_source = data_source
        self.series = series
        self.title = title
        self.x_axis = x_axis or AxisConfig(title="X轴")
        self.y_axis = y_axis or AxisConfig(title="Y轴")
        self.options = options or {}
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于JSON序列化）"""
        return {
            "id": self.id,
            "name": self.name,
            "chart_type": self.chart_type.value,
            "data_source": self.data_source.value,
            "series": [s.to_dict() for s in self.series],
            "title": self.title,
            "x_axis": self.x_axis.to_dict(),
            "y_axis": self.y_axis.to_dict(),
            "options": self.options,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChartConfig":
        """从字典创建实例"""
        x_axis = AxisConfig(**data["x_axis"]) if data.get("x_axis") else None
        y_axis = AxisConfig(**data["y_axis"]) if data.get("y_axis") else None

        series = [SeriesConfig(**s) for s in data.get("series", [])]

        return cls(
            id=data["id"],
            name=data["name"],
            chart_type=ChartType(data["chart_type"]),
            data_source=DataSourceType(data["data_source"]),
            series=series,
            title=data.get("title", ""),
            x_axis=x_axis,
            y_axis=y_axis,
            options=data.get("options", {}),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else None,
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else None,
        )


# 预设模板
PRESET_TEMPLATES = {
    "portfolio_overview": ChartConfig(
        id="portfolio_overview",
        name="投资组合总览",
        chart_type=ChartType.PIE,
        data_source=DataSourceType.POSITIONS,
        series=[
            SeriesConfig(
                name="市值分布",
                data_key="market_value",
                chart_type="pie",
                color="#36A2EB",
            )
        ],
        title="持仓市值分布",
        x_axis=AxisConfig(title="股票", visible=False),
        y_axis=AxisConfig(title="市值", visible=False),
    ),
    "strategy_comparison": ChartConfig(
        id="strategy_comparison",
        name="策略对比",
        chart_type=ChartType.BAR,
        data_source=DataSourceType.STRATEGY,
        series=[
            SeriesConfig(
                name="总资产",
                data_key="current_value",
                chart_type="bar",
                color="#36A2EB",
            ),
            SeriesConfig(
                name="收益率",
                data_key="total_return_pct",
                chart_type="line",
                color="#FF6384",
            ),
        ],
        title="策略表现对比",
        x_axis=AxisConfig(title="策略"),
        y_axis=AxisConfig(title="金额/收益率", format="currency"),
    ),
    "profit_loss_trend": ChartConfig(
        id="profit_loss_trend",
        name="盈亏趋势",
        chart_type=ChartType.LINE,
        data_source=DataSourceType.POSITIONS,
        series=[
            SeriesConfig(
                name="累计盈亏",
                data_key="cumulative_profit",
                chart_type="line",
                color="#4BC0C0",
            )
        ],
        title="持仓盈亏趋势",
        x_axis=AxisConfig(title="日期", format="date"),
        y_axis=AxisConfig(title="盈亏金额", format="currency"),
    ),
    "position_allocation": ChartConfig(
        id="position_allocation",
        name="持仓配置",
        chart_type=ChartType.BAR,
        data_source=DataSourceType.POSITIONS,
        series=[
            SeriesConfig(
                name="持仓数量", data_key="quantity", chart_type="bar", color="#FFCE56"
            )
        ],
        title="持仓数量分布",
        x_axis=AxisConfig(title="股票"),
        y_axis=AxisConfig(title="数量"),
    ),
}
