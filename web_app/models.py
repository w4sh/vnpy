#!/usr/bin/env python3
"""
持仓管理系统数据模型
定义持仓、策略、交易记录和风险指标的数据结构
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Numeric,
    Date,
    DateTime,
    ForeignKey,
    DECIMAL,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Position(Base):
    """持仓表 - 存储股票持仓信息"""

    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)  # 股票代码
    name = Column(String(50))  # 股票名称
    quantity = Column(Integer, nullable=False)  # 持仓数量
    cost_price = Column(Numeric(10, 2), nullable=False)  # 成本价
    current_price = Column(Numeric(10, 2))  # 当前价
    market_value = Column(Numeric(15, 2))  # 市值
    profit_loss = Column(Numeric(15, 2))  # 盈亏金额
    profit_loss_pct = Column(Numeric(8, 4))  # 盈亏百分比
    strategy_id = Column(Integer, ForeignKey("strategies.id"))  # 关联策略ID
    buy_date = Column(Date)  # 买入日期
    status = Column(String(20), default="holding")  # 状态: holding/sold
    stop_loss = Column(Numeric(10, 2))  # 止损价
    take_profit = Column(Numeric(10, 2))  # 止盈价
    notes = Column(Text)  # 备注
    prev_close_price = Column(Numeric(10, 2))  # 昨收价
    user_id = Column(Integer, nullable=False, default=1)  # 用户ID
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    strategy = relationship("Strategy", back_populates="positions")
    transactions = relationship("Transaction", back_populates="position")

    def __repr__(self):
        return (
            f"<Position(id={self.id}, symbol={self.symbol}, quantity={self.quantity})>"
        )


class Strategy(Base):
    """策略表 - 管理不同的交易策略"""

    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)  # 策略名称
    description = Column(Text)  # 策略描述
    initial_capital = Column(Numeric(15, 2), nullable=False)  # 初始资金
    current_capital = Column(Numeric(15, 2))  # 当前资金
    total_return = Column(Numeric(8, 4))  # 总收益率
    max_drawdown = Column(Numeric(8, 4))  # 最大回撤
    sharpe_ratio = Column(Numeric(6, 4))  # 夏普比率
    risk_level = Column(String(20))  # 风险等级
    user_id = Column(Integer, nullable=False, default=1)  # 用户ID
    recalc_status = Column(String(20), nullable=False, default="clean")  # 重算状态
    recalc_retry_count = Column(Integer, nullable=False, default=0)  # 重试次数
    last_error = Column(Text)  # 最后错误
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    positions = relationship("Position", back_populates="strategy")
    transactions = relationship("Transaction", back_populates="strategy")
    risk_metrics = relationship("RiskMetric", back_populates="strategy")

    def __repr__(self):
        return f"<Strategy(id={self.id}, name={self.name})>"


class Transaction(Base):
    """交易记录表 - 记录完整的交易历史"""

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(Integer, ForeignKey("positions.id"))  # 关联持仓ID
    strategy_id = Column(Integer, ForeignKey("strategies.id"))  # 关联策略ID
    transaction_type = Column(
        String(20), nullable=False
    )  # 类型: buy/sell/dividend/bonus
    symbol = Column(String(20), nullable=False)  # 股票代码
    quantity = Column(Integer, nullable=False)  # 数量
    price = Column(Numeric(10, 2), nullable=False)  # 价格
    amount = Column(Numeric(15, 2), nullable=False)  # 金额
    fee = Column(Numeric(10, 2))  # 手续费
    transaction_date = Column(Date, nullable=False)  # 交易日期
    notes = Column(Text)  # 备注
    user_id = Column(Integer, nullable=False, default=1)  # 用户ID
    created_at = Column(DateTime, default=datetime.now)

    # 关系
    position = relationship("Position", back_populates="transactions")
    strategy = relationship("Strategy", back_populates="transactions")

    def __repr__(self):
        return f"<Transaction(id={self.id}, type={self.transaction_type}, symbol={self.symbol})>"


class RiskMetric(Base):
    """风险指标表 - 存储持仓风险分析数据"""

    __tablename__ = "risk_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(Integer, ForeignKey("positions.id"))  # 关联持仓ID
    strategy_id = Column(Integer, ForeignKey("strategies.id"))  # 关联策略ID
    volatility = Column(Numeric(8, 4))  # 波动率
    var = Column(Numeric(10, 2))  # 风险价值
    beta = Column(Numeric(6, 4))  # 贝塔系数
    concentration = Column(Numeric(6, 4))  # 集中度
    risk_score = Column(Numeric(6, 4))  # 风险评分
    calculated_at = Column(DateTime)  # 计算时间

    # 关系
    strategy = relationship("Strategy", back_populates="risk_metrics")

    def __repr__(self):
        return f"<RiskMetric(id={self.id}, risk_score={self.risk_score})>"


class TransactionAuditLog(Base):
    """交易记录审计日志表"""

    __tablename__ = "transaction_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    field_name = Column(String(50), nullable=False)
    old_value = Column(Text)
    new_value = Column(Text, nullable=False)
    change_reason = Column(Text, nullable=False)
    changed_at = Column(DateTime, default=datetime.now)
    changed_by = Column(Integer, nullable=False, default=1)

    def __repr__(self):
        return f"<TransactionAuditLog(id={self.id}, transaction_id={self.transaction_id}, field_name={self.field_name})>"


class StrategyAuditLog(Base):
    """策略审计日志表"""

    __tablename__ = "strategy_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    field_name = Column(String(50), nullable=False)
    old_value = Column(Text)
    new_value = Column(Text, nullable=False)
    change_reason = Column(Text, nullable=False)
    changed_at = Column(DateTime, default=datetime.now)
    changed_by = Column(Integer, nullable=False, default=1)

    def __repr__(self):
        return f"<StrategyAuditLog(id={self.id}, strategy_id={self.strategy_id}, field_name={self.field_name})>"


# 数据库初始化和辅助函数
def init_database(db_url="sqlite:///position_management.db"):
    """初始化数据库"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url)
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    return Session


def get_db_session(db_url="sqlite:///position_management.db"):
    """获取数据库会话"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    return Session()


if __name__ == "__main__":
    # 测试数据库创建
    print("创建持仓管理数据库...")
    init_database()
    print("数据库创建成功！")

    # 测试数据插入
    session = get_db_session()
    try:
        # 创建测试策略
        strategy = Strategy(
            name="双均线策略",
            description="基于双均线信号的交易策略",
            initial_capital=1000000,
            current_capital=1000000,
            risk_level="中等",
        )
        session.add(strategy)
        session.commit()
        print(f"测试策略创建成功: {strategy.name}")

    except Exception as e:
        print(f"测试失败: {e}")
        session.rollback()
    finally:
        session.close()
