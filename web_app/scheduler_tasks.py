"""后台定时任务

实现：
- 定时重算dirty策略（每5分钟）
- 恢复卡死的recomputing状态（每10分钟）
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
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


def run_daily_candidate_screening():
    """每日候选股筛选（交易日 15:30）"""
    try:
        from web_app.candidate.screening_engine import run_screening, save_results_to_db
        from datetime import date

        logger.info("开始每日候选股筛选...")
        results, pool_size, elapsed = run_screening(mode="full")
        save_results_to_db(results, date.today())
        logger.info(
            f"每日候选股筛选完成：股票池 {pool_size}，"
            f"推荐 {len(results)} 只，耗时 {elapsed}s"
        )
    except Exception as e:
        logger.error(f"每日候选股筛选失败: {e}")


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

    # 每日候选股筛选：交易日 15:30
    scheduler.add_job(
        func=run_daily_candidate_screening,
        trigger=CronTrigger(day_of_week="mon-fri", hour=15, minute=30),
        id="daily_candidate_screening",
        name="每日候选股筛选",
    )

    # 日终前瞻因子更新：交易日 15:35
    scheduler.add_job(
        func=run_daily_factor_update,
        trigger=CronTrigger(day_of_week="mon-fri", hour=15, minute=35),
        id="daily_factor_update",
        name="日终前瞻因子更新",
    )

    scheduler.start()
    logger.info("定时任务已启动")


def run_daily_factor_update():
    """日终增量更新前瞻因子（交易日 15:30 之后）"""
    try:
        from web_app.candidate.screening_engine import STOCK_POOL
        from datetime import date

        today = date.today().strftime("%Y%m%d")

        from vnpy.alpha.factors import FactorEngine
        from vnpy.alpha.factors.fundamental import (
            FundamentalFetcher,
            FundamentalComputer,
            FundamentalStorage,
        )
        from vnpy.alpha.factors.fundamental.fetcher import FundamentalFetcher as FF

        engine = FactorEngine()
        engine.register(
            "fundamental",
            FundamentalFetcher(),
            FundamentalComputer(),
            FundamentalStorage(),
        )

        # 日频估值数据更新（每次必跑）
        daily_result = engine.run_daily(STOCK_POOL, today)
        logger.info(f"日频因子更新完成: {daily_result}")

        # 季频财务数据仅在财报旺季窗口更新
        from datetime import datetime as dt

        now = dt.now()
        if FF.is_earnings_window(now):
            logger.info("进入财报旺季窗口，执行季频因子更新")
            quarterly_result = engine.run_quarterly(STOCK_POOL, today)
            logger.info(f"季频因子更新完成: {quarterly_result}")
        else:
            logger.info("非财报旺季窗口，跳过季频因子更新")

    except Exception as e:
        logger.error(f"因子更新任务失败: {e}")


def shutdown_scheduler():
    """关闭定时任务"""
    scheduler.shutdown()
    logger.info("定时任务已关闭")
