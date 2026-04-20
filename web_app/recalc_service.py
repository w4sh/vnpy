"""策略重算服务

实现策略数据的全量重算，包括：
- 状态机管理（clean/dirty/recomputing/failed）
- 单一事务保证原子性
- 乐观锁实现并发控制
- 自动重试和失败处理
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import exc
import logging

logger = logging.getLogger(__name__)


class RecalculationService:
    """策略重算服务"""

    def __init__(self, session: Session):
        """初始化重算服务

        Args:
            session: SQLAlchemy session，必须在调用方事务中使用
        """
        self.session = session

    def mark_strategy_dirty(self, strategy_id: int) -> bool:
        """标记策略为dirty状态

        Args:
            strategy_id: 策略ID

        Returns:
            bool: 标记成功返回True
        """
        from web_app.models import Strategy

        strategy = self.session.query(Strategy).get(strategy_id)
        if not strategy:
            logger.warning(f"策略{strategy_id}不存在")
            return False

        if strategy.recalc_status == "clean":
            strategy.recalc_status = "dirty"
            strategy.recalc_retry_count = 0
            strategy.last_error = None
            logger.info(f"策略{strategy_id}标记为dirty")

        return True

    def acquire_execution_lock(self, strategy_id: int) -> bool:
        """获取重算执行权（乐观锁）

        Args:
            strategy_id: 策略ID

        Returns:
            bool: 成功获取返回True，已被其他worker抢占返回False
        """
        from web_app.models import Strategy

        rows_affected = (
            self.session.query(Strategy)
            .filter_by(id=strategy_id, recalc_status="dirty")
            .update(
                {"recalc_status": "recomputing", "updated_at": datetime.now()},
                synchronize_session=False,
            )
        )

        if rows_affected == 0:
            logger.info(f"策略{strategy_id}已被其他worker抢占")
            return False

        self.session.commit()
        logger.info(f"策略{strategy_id}获取执行权成功")
        return True

    def recalc_strategy(self, strategy_id: int) -> None:
        """重算策略的所有衍生数据

        关键约束：
        1. 整个重算过程必须在单一事务中完成
        2. 保证原子性：要么全部成功，要么全部回滚

        Args:
            strategy_id: 策略ID

        Raises:
            ValueError: 策略不存在
            Exception: 重算失败
        """
        from web_app.models import Strategy, Position

        try:
            # 获取策略对象
            strategy = self.session.query(Strategy).get(strategy_id)
            if not strategy:
                raise ValueError(f"策略{strategy_id}不存在")

            # 获取所有持仓
            positions = (
                self.session.query(Position)
                .filter_by(strategy_id=strategy_id, status="holding")
                .all()
            )

            # 为每个持仓重新计算成本和数量
            for position in positions:
                self._recalc_position_cost(position)

            # 更新策略指标
            total_market_value = sum(float(p.market_value or 0) for p in positions)
            strategy.current_capital = total_market_value
            if strategy.initial_capital and float(strategy.initial_capital) > 0:
                strategy.total_return = (
                    float(strategy.current_capital) - float(strategy.initial_capital)
                ) / float(strategy.initial_capital)
            else:
                strategy.total_return = 0

            # 所有计算成功后，统一更新状态
            strategy.recalc_status = "clean"
            strategy.recalc_retry_count = 0
            strategy.last_error = None
            strategy.updated_at = datetime.now()

            # 单一事务提交点
            self.session.commit()
            logger.info(f"策略{strategy_id}重算成功")

        except Exception as e:
            # 任何失败都回滚整个事务
            self.session.rollback()
            logger.error(f"策略{strategy_id}重算失败: {e}")
            raise

    def _recalc_position_cost(self, position) -> None:
        """重算持仓的成本和数量（加权平均成本法）

        Args:
            position: 持仓对象（必须在session中）
        """
        from web_app.models import Transaction

        # 获取所有相关交易（按时间顺序）
        transactions = (
            self.session.query(Transaction)
            .filter_by(position_id=position.id)
            .order_by(Transaction.transaction_date)
            .all()
        )

        total_qty = 0
        total_cost = 0.0

        for txn in transactions:
            if txn.transaction_type == "buy":
                # 买入：加权平均成本
                amount = float(txn.quantity) * float(txn.price) + float(txn.fee)
                new_qty = total_qty + txn.quantity
                if new_qty > 0:
                    new_cost = (total_cost * total_qty + amount) / new_qty
                else:
                    new_cost = 0

                total_qty = new_qty
                total_cost = new_cost

            elif txn.transaction_type == "sell":
                # 卖出：成本不变，减少持仓
                total_qty -= txn.quantity
                # 成本保持不变

        # 更新持仓（不单独commit，由外层统一提交）
        position.quantity = total_qty
        position.cost_price = total_cost
        position.market_value = float(position.current_price or 0) * total_qty
        position.profit_loss = (
            position.market_value - (total_cost * total_qty) if total_qty > 0 else 0
        )

        if position.cost_price and position.cost_price > 0:
            position.profit_loss_pct = (
                position.profit_loss / (total_cost * total_qty)
            ) * 100
        else:
            position.profit_loss_pct = 0

        position.updated_at = datetime.now()


def handle_recalc_failure(strategy_id: int, error_msg: str) -> None:
    """处理重算失败（独立事务）

    Args:
        strategy_id: 策略ID
        error_msg: 错误信息
    """
    from web_app.models import Strategy, get_db_session

    session = get_db_session()
    try:
        strategy = session.query(Strategy).get(strategy_id)
        if not strategy:
            logger.error(f"策略{strategy_id}不存在，无法处理失败")
            return

        # 增加重试计数
        strategy.recalc_retry_count += 1

        if strategy.recalc_retry_count >= 3:
            # 已达到最大重试次数，标记为failed
            strategy.recalc_status = "failed"
            strategy.last_error = f"Max retries exceeded: {error_msg}"
            logger.error(f"策略{strategy_id}达到最大重试次数")
        else:
            # 保持dirty状态，等待下次重试
            strategy.recalc_status = "dirty"
            strategy.last_error = error_msg
            logger.warning(f"策略{strategy_id}重算失败，将重试")

        session.commit()

    except Exception as e:
        session.rollback()
        logger.error(f"处理策略{strategy_id}失败时出错: {e}")
    finally:
        session.close()
