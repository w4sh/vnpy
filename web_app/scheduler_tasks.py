"""后台定时任务

实现：
- 定时重算dirty策略（每5分钟）
- 恢复卡死的recomputing状态（每10分钟）
- 每日候选股筛选（交易日 15:30）
- 日终前瞻因子增量更新（交易日 15:35，仅基本面日频数据）

季度因子更新因涉及全量A股逐只拉取（耗时 80+ 分钟），不适合日终定时执行，
改为单独的 Monthly 任务或手动执行 `run_quarterly_factor_update()`。
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from datetime import date, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# 每日任务补跑窗口：重启后 4 小时内仍会执行
_MISSED_GRACE_SECONDS = 14_400

from web_app.models import Strategy, get_db_session
from web_app.recalc_service import RecalculationService, handle_recalc_failure

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
_scheduler_initialized = False


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


def run_daily_candidate_screening(trade_date: str | None = None):
    """每日候选股筛选（交易日 15:30）

    参数:
        trade_date: 筛选基准日期 str/date，默认今天
    """
    try:
        from datetime import date as dt_date

        from web_app.candidate.screening_engine import run_screening
        from web_app.candidate.scoring import save_results_to_db
        from web_app.candidate.candidate_types import CandidateResult

        if trade_date is None:
            target_date = dt_date.today()
        elif isinstance(trade_date, str):
            target_date = dt_date.fromisoformat(trade_date)
        else:
            target_date = trade_date

        logger.info("开始每日候选股筛选...")
        results, pool_size, elapsed = run_screening(mode="full")

        candidates = [
            CandidateResult(
                symbol=r["symbol"],
                name=r["name"],
                momentum_score=r["momentum_score"],
                trend_score=r["trend_score"],
                volume_score=r["volume_score"],
                volatility_score=r["volatility_score"],
                technical_score=r["technical_score"],
                performance_score=r.get("performance_score", 0.0),
                combined_score=r["combined_score"],
                rank=r["rank"],
                current_price=r["current_price"],
                total_return=r["total_return"],
                max_drawdown=r["max_drawdown"],
                sharpe_ratio=r["sharpe_ratio"],
            )
            for r in results
        ]
        save_results_to_db(candidates, target_date)
        logger.info(
            "每日候选股筛选完成: pool=%d, top=%d, elapsed=%.1fs",
            pool_size,
            len(results),
            elapsed,
        )
    except Exception as e:
        logger.error("每日候选股筛选失败: %s", e)


def init_scheduler():
    """初始化定时任务（幂等，可安全多次调用）"""
    global _scheduler_initialized

    if _scheduler_initialized:
        logger.warning(
            "init_scheduler 被重复调用，跳过（调用堆栈：%s）",
            "".join(traceback.format_stack()[-6:-1]),
        )
        return

    _scheduler_initialized = True

    # 重算dirty策略：每5分钟执行一次
    scheduler.add_job(
        func=recalc_dirty_strategies,
        trigger=IntervalTrigger(minutes=5),
        id="recalc_dirty_strategies",
        name="重算dirty策略",
        replace_existing=True,
    )

    # 恢复卡死状态：每10分钟执行一次
    scheduler.add_job(
        func=recover_stuck_strategies,
        trigger=IntervalTrigger(minutes=10),
        id="recover_stuck_strategies",
        name="恢复卡死策略",
        replace_existing=True,
    )

    # 每日候选股筛选：交易日 15:30
    scheduler.add_job(
        func=run_daily_candidate_screening,
        trigger=CronTrigger(day_of_week="mon-fri", hour=15, minute=30),
        id="daily_candidate_screening",
        name="每日候选股筛选",
        misfire_grace_time=_MISSED_GRACE_SECONDS,
        replace_existing=True,
    )

    # 日终前瞻因子更新：交易日 15:35
    scheduler.add_job(
        func=run_daily_factor_update,
        trigger=CronTrigger(day_of_week="mon-fri", hour=15, minute=35),
        id="daily_factor_update",
        name="日终前瞻因子更新",
        misfire_grace_time=_MISSED_GRACE_SECONDS,
        replace_existing=True,
    )

    # 每日投资组合推荐：交易日 15:36（确保筛选和因子更新都已完成）
    scheduler.add_job(
        func=run_portfolio_recommendation,
        trigger=CronTrigger(day_of_week="mon-fri", hour=15, minute=36),
        id="daily_portfolio_recommendation",
        name="每日投资组合推荐",
        misfire_grace_time=_MISSED_GRACE_SECONDS,
        replace_existing=True,
    )

    # 每日 ETF 筛选推荐：交易日 15:40
    scheduler.add_job(
        func=run_daily_etf,
        trigger=CronTrigger(day_of_week="mon-fri", hour=15, minute=40),
        id="daily_etf",
        name="每日ETF筛选推荐",
        misfire_grace_time=_MISSED_GRACE_SECONDS,
        replace_existing=True,
    )

    if not scheduler.running:
        scheduler.start()
        logger.info("定时任务已启动")
    else:
        logger.info("定时任务已在运行中")


def run_daily_factor_update(trade_date: str | None = None):
    """日终增量更新前瞻因子（仅日频数据：daily_basic）

    参数:
        trade_date: 交易日 YYYYMMDD，默认今天
    """
    if trade_date is None:
        trade_date = date.today().strftime("%Y%m%d")

    sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    try:
        from vnpy.alpha.factors import FactorEngine
        from vnpy.alpha.factors.fundamental import (
            FundamentalComputer,
            FundamentalFetcher,
            FundamentalStorage,
        )
        from vnpy.alpha.factors.stock_pool import StockPoolManager

        pool_manager = StockPoolManager()
        full_pool = pool_manager.get_full_pool()
        logger.info("日频因子更新: pool=%d, trade_date=%s", len(full_pool), trade_date)

        engine = FactorEngine()
        engine.register(
            "fundamental",
            "both",
            FundamentalFetcher(),
            FundamentalComputer(),
            FundamentalStorage(),
        )

        daily_result = engine.run_daily(full_pool, trade_date)
        logger.info("日频因子更新完成: %s", daily_result)

    except Exception as e:
        logger.error("因子更新任务失败: %s", e)


def run_quarterly_factor_update(
    end_date: str | None = None,
    batch_size: int = 50,
):
    """季频财务数据全量更新（耗时 80+ 分钟，建议独立执行）

    仅应在以下情况触发：
    - 每月/每季度手动执行
    - 财报季结束后一次性增量补全
    - 首次初始化时全量拉取

    参数:
        end_date: 报告截止日 YYYYMMDD，默认使用最近的财报截止期
        batch_size: 每批股票数量
    """
    if end_date is None:
        # 默认使用最近一个财报截止期
        today = date.today()
        # 财报截止期：4/30, 8/31, 10/31, 次年 4/30
        if today.month >= 11 or today.month <= 4:
            end_date = f"{today.year - 1}1231" if today.month <= 4 else "2026Q1"
        elif today.month <= 8:
            end_date = f"{today.year}0331"  # Q1
        elif today.month <= 10:
            end_date = f"{today.year}0630"  # Q2
        else:
            end_date = f"{today.year}0930"  # Q3

        end_date = end_date.replace("Q", "") if "Q" in end_date else end_date

    sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    try:
        from vnpy.alpha.factors import FactorEngine
        from vnpy.alpha.factors.fundamental import (
            FundamentalComputer,
            FundamentalFetcher,
            FundamentalStorage,
        )
        from vnpy.alpha.factors.stock_pool import StockPoolManager

        pool_manager = StockPoolManager()
        full_pool = pool_manager.get_full_pool()
        logger.info(
            "季频因子更新: pool=%d, end_date=%s, batch=%d",
            len(full_pool),
            end_date,
            batch_size,
        )

        engine = FactorEngine()
        engine.register(
            "fundamental",
            "both",
            FundamentalFetcher(),
            FundamentalComputer(),
            FundamentalStorage(),
        )
        engine.init_stock_pool()

        quarterly_result = engine.run_quarterly_batch(full_pool, end_date, batch_size)
        logger.info("季频因子更新完成: %s", quarterly_result)

    except Exception as e:
        logger.error("季频因子更新失败: %s", e)


def run_portfolio_recommendation(trade_date: str | None = None):
    """每日投资组合推荐（交易日 15:36，在候选股筛选和因子更新之后执行）

    参数:
        trade_date: 交易日 YYYY-MM-DD，默认今天
    """
    try:
        from datetime import date as dt_date

        from web_app.models import Position, Strategy, get_db_session
        from web_app.recommendation_api import _save_recommendations_to_db
        from web_app.recommendation_engine import generate_recommendations

        if trade_date:
            rec_date = dt_date.fromisoformat(trade_date)
        else:
            rec_date = dt_date.today()

        logger.info("开始每日投资组合推荐 (date=%s)...", rec_date)

        session = get_db_session()
        try:
            results = generate_recommendations(session, rec_date)
            strategies = (
                session.query(Strategy).filter(Strategy.status == "active").all()
            )
            total_capital = (
                sum(float(s.current_capital or s.initial_capital) for s in strategies)
                if strategies
                else 1_000_000
            )
            held_positions = (
                session.query(Position).filter(Position.status == "holding").all()
            )
            total_market_value = sum(float(p.market_value or 0) for p in held_positions)

            _save_recommendations_to_db(
                results, rec_date, total_capital, total_market_value
            )

            logger.info(
                "投资组合推荐完成: held=%d, buy=%d",
                sum(1 for r in results if r.is_held),
                sum(
                    1 for r in results if r.recommendation_type in ("STRONG_BUY", "BUY")
                ),
            )
        finally:
            session.close()
    except Exception as e:
        logger.error("投资组合推荐失败: %s", e)


def run_daily_etf():
    """每日 ETF 筛选推荐（交易日 15:40，个股任务全部完成后）"""
    try:
        from web_app.etf.etf_screening_engine import run_daily_etf_screening

        run_daily_etf_screening()
        logger.info("每日 ETF 筛选推荐完成")
    except Exception as e:
        logger.error("每日 ETF 筛选推荐失败: %s", e)


def shutdown_scheduler():
    """关闭定时任务"""
    global _scheduler_initialized

    if not _scheduler_initialized:
        logger.warning("Scheduler 未初始化，跳过关闭")
        return

    if scheduler.running:
        scheduler.shutdown()
        _scheduler_initialized = False
        logger.info("定时任务已关闭")
    else:
        logger.info("定时任务未在运行中")
