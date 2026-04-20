"""后台定时任务

实现：
- 定时重算dirty策略（每5分钟）
- 恢复卡死的recomputing状态（每10分钟）
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
from web_app.models import Strategy, get_db_session
from web_app.recalc_service import RecalculationService, handle_recalc_failure
import logging

logger = logging.getLogger(__name__)

# 创建scheduler
scheduler = BackgroundScheduler()


def recalc_dirty_strategies():
    """定时重算dirty策略（每5分钟）"""
    session = None
    try:
        session = get_db_session()
        recalc_service = RecalculationService(session)

        # 获取所有dirty策略，排除已删除的策略
        dirty_strategies = (
            session.query(Strategy)
            .filter_by(recalc_status="dirty", status="active")
            .all()
        )

        logger.info(f"找到{len(dirty_strategies)}个dirty策略")

        for strategy in dirty_strategies:
            # 尝试获取执行权（乐观锁）
            if recalc_service.acquire_execution_lock(strategy.id):
                try:
                    # 执行重算
                    recalc_service.recalc_strategy(strategy.id)
                    logger.info(f"策略{strategy.id}重算成功")
                except Exception as e:
                    # 独立事务处理失败
                    handle_recalc_failure(strategy.id, str(e))
                    logger.error(f"策略{strategy.id}重算失败: {e}")

    except Exception as e:
        logger.error(f"定时任务执行失败: {e}")
    finally:
        if session:
            session.close()


def recover_stuck_strategies():
    """恢复卡死的recomputing状态（每10分钟）

    检测超过30分钟的recomputing状态，自动重置为dirty
    """
    session = None
    try:
        session = get_db_session()

        # 查找超时的recomputing策略（30分钟未更新），排除已删除的策略
        timeout_threshold = datetime.now() - timedelta(minutes=30)
        stuck_strategies = (
            session.query(Strategy)
            .filter_by(recalc_status="recomputing", status="active")
            .filter(Strategy.updated_at < timeout_threshold)
            .all()
        )

        logger.warning(f"找到{len(stuck_strategies)}个卡死的策略")

        for strategy in stuck_strategies:
            # 重置为dirty
            strategy.recalc_status = "dirty"
            strategy.last_error = "重算超时，已自动重置"
            strategy.updated_at = datetime.now()

        session.commit()
        logger.info(f"已重置{len(stuck_strategies)}个卡死策略")

    except Exception as e:
        logger.error(f"恢复任务执行失败: {e}")
        if session:
            session.rollback()
    finally:
        if session:
            session.close()


def init_scheduler():
    """初始化定时任务"""
    # 重算dirty策略：每5分钟执行一次
    scheduler.add_job(
        func=recalc_dirty_strategies,
        trigger=IntervalTrigger(minutes=5),
        id="recalc_dirty_strategies",
        name="重算dirty策略",
    )

    # 恢复卡死状态：每10分钟执行一次
    scheduler.add_job(
        func=recover_stuck_strategies,
        trigger=IntervalTrigger(minutes=10),
        id="recover_stuck_strategies",
        name="恢复卡死策略",
    )

    scheduler.start()
    logger.info("定时任务已启动")


def shutdown_scheduler():
    """关闭定时任务"""
    scheduler.shutdown()
    logger.info("定时任务已关闭")
