"""独立定时任务调度器 — 守护进程，独立于 Flask 运行

启动和停止是脚本化操作，留空即前台运行：

    后台启动：  python web_app/run_scheduler.py --daemon
    停止：      python web_app/run_scheduler.py --stop
    查看状态：  python web_app/run_scheduler.py --status
    前台运行：  python web_app/run_scheduler.py

在 init_scheduler() 为所有每日 cron 任务设置了 misfire_grace_time，
因此调度器重启后漏过的任务会自动补跑。
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from datetime import date, datetime
from pathlib import Path

# 确保项目路径在 sys.path 中
_proj_root = str(Path(__file__).parent.parent)
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from web_app.scheduler_tasks import (
    init_scheduler,
    recalc_dirty_strategies,
    recover_stuck_strategies,
    run_daily_candidate_screening,
    run_daily_etf,
    run_daily_factor_update,
    run_portfolio_recommendation,
    scheduler,
    _MISSED_GRACE_SECONDS,
)

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

PID_FILE = Path(os.path.expanduser("~/.vnpy_scheduler.pid"))
LOG_DIR = Path(_proj_root) / "logs"

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------


def _setup_logging():
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / "scheduler.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger("run_scheduler")


# ---------------------------------------------------------------------------
# 启动补跑：错过窗口的每日任务按顺序执行一次
# ---------------------------------------------------------------------------


def _catch_up_missed_tasks():
    """检查今日的每日任务是否已经执行过，未执行则按顺序补跑"""
    logger = logging.getLogger("run_scheduler")
    today = date.today()
    is_weekday = today.weekday() < 5  # 0=Mon … 4=Fri

    if not is_weekday:
        logger.info("非交易日，跳过每日任务补跑")
        return

    now = datetime.now()
    from web_app.models import (
        CandidateStock,
        EtfCandidate,
        PortfolioRecommendation,
        get_db_session,
    )

    session = get_db_session()
    try:
        # ── 检查今日是否已跑过候选股筛选 ──
        has_screening = (
            session.query(CandidateStock)
            .filter(CandidateStock.screening_date == today)
            .first()
            is not None
        )
        if not has_screening and now.hour >= 15 and now.minute >= 30:
            logger.info("补跑: 今日候选股筛选")
            run_daily_candidate_screening()
        else:
            logger.info(
                "跳过候选股筛选补跑: %s",
                "数据已存在" if has_screening else "未到预定时间",
            )

        # ── 检查今日是否已跑过因子更新 ──
        from vnpy.alpha.factors.stock_pool import StockPoolManager

        pool_manager = StockPoolManager()
        pool = pool_manager.get_full_pool()
        trade_date_str = today.strftime("%Y%m%d")

        has_factor = False
        try:
            from vnpy.alpha.factors.fundamental import FundamentalStorage

            fs = FundamentalStorage()
            data = fs.load(trade_date_str, [s["symbol"] for s in pool[:1]])
            if not data.empty:
                has_factor = True
        except Exception:
            pass

        if not has_factor and now.hour >= 15 and now.minute >= 35:
            logger.info("补跑: 日终因子更新")
            run_daily_factor_update()
        else:
            logger.info(
                "跳过因子更新补跑: %s", "数据已存在" if has_factor else "未到预定时间"
            )

        # ── 检查今日是否已跑过组合推荐 ──
        has_rec = (
            session.query(PortfolioRecommendation)
            .filter(PortfolioRecommendation.recommendation_date == today)
            .first()
            is not None
        )
        if not has_rec and now.hour >= 15 and now.minute >= 36:
            logger.info("补跑: 每日投资组合推荐")
            run_portfolio_recommendation()
        else:
            logger.info(
                "跳过组合推荐补跑: %s", "数据已存在" if has_rec else "未到预定时间"
            )

        # ── 检查今日是否已跑过 ETF 筛选推荐 ──
        has_etf = (
            session.query(EtfCandidate)
            .filter(EtfCandidate.screening_date == today)
            .first()
            is not None
        )
        if not has_etf and now.hour >= 15 and now.minute >= 40:
            logger.info("补跑: 每日 ETF 筛选推荐")
            run_daily_etf()
        else:
            logger.info(
                "跳过 ETF 筛选推荐补跑: %s", "数据已存在" if has_etf else "未到预定时间"
            )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 信号处理
# ---------------------------------------------------------------------------

_shutdown_requested = False


def _signal_handler(signum, frame):
    global _shutdown_requested
    if _shutdown_requested:
        return
    _shutdown_requested = True
    logger = logging.getLogger("run_scheduler")
    logger.info("收到信号 %s，正在关闭调度器...", signum)
    from web_app.scheduler_tasks import shutdown_scheduler

    shutdown_scheduler()
    _remove_pid()
    logger.info("调度器已关闭")


# ---------------------------------------------------------------------------
# PID 管理
# ---------------------------------------------------------------------------


def _write_pid():
    PID_FILE.write_text(str(os.getpid()))


def _remove_pid():
    if PID_FILE.exists():
        PID_FILE.unlink()


def _read_pid() -> int | None:
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except (ValueError, OSError):
            return None
    return None


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# 今日时间覆盖：将每日任务安排到指定时间
# ---------------------------------------------------------------------------


def _skip_if_done(task_name, check_fn, run_fn):
    """包装函数：如果 check_fn 返回 True（数据已存在），跳过执行"""

    def wrapper():
        if check_fn():
            logger = logging.getLogger("run_scheduler")
            logger.info("跳过 %s: 数据已存在", task_name)
            return
        run_fn()

    wrapper.__name__ = run_fn.__name__
    return wrapper


def _init_scheduler_with_override(today_at: str, logger: logging.Logger):
    """初始化调度器，今日每日任务安排在指定时间，正常 cron 从明天生效"""
    from datetime import date, timedelta, time as dt_time

    from web_app.models import (
        CandidateStock,
        PortfolioRecommendation,
        get_db_session,
    )

    hour, minute = map(int, today_at.split(":"))
    run_base = datetime.combine(date.today(), dt_time(hour, minute))
    tomorrow = date.today() + timedelta(days=1)

    # 间隔任务
    scheduler.add_job(
        recalc_dirty_strategies,
        IntervalTrigger(minutes=5),
        id="recalc_dirty_strategies",
        name="重算dirty策略",
        replace_existing=True,
    )
    scheduler.add_job(
        recover_stuck_strategies,
        IntervalTrigger(minutes=10),
        id="recover_stuck_strategies",
        name="恢复卡死策略",
        replace_existing=True,
    )

    # ── 今日一次性任务（顺序：筛选 → 因子 → 推荐，间隔 2 分钟）──
    today = date.today()

    def has_screening():
        session = get_db_session()
        try:
            return (
                session.query(CandidateStock)
                .filter(CandidateStock.screening_date == today)
                .first()
                is not None
            )
        finally:
            session.close()

    def has_recommendation():
        session = get_db_session()
        try:
            return (
                session.query(PortfolioRecommendation)
                .filter(PortfolioRecommendation.recommendation_date == today)
                .first()
                is not None
            )
        finally:
            session.close()

    scheduler.add_job(
        _skip_if_done("候选股筛选", has_screening, run_daily_candidate_screening),
        DateTrigger(run_date=run_base),
        id="today_screening",
        name="今日候选股筛选",
        replace_existing=True,
    )
    scheduler.add_job(
        _skip_if_done("日终因子更新", lambda: False, run_daily_factor_update),
        DateTrigger(run_date=run_base + timedelta(minutes=2)),
        id="today_factor_update",
        name="今日日终因子更新",
        replace_existing=True,
    )
    scheduler.add_job(
        _skip_if_done("投资组合推荐", has_recommendation, run_portfolio_recommendation),
        DateTrigger(run_date=run_base + timedelta(minutes=4)),
        id="today_portfolio_recommendation",
        name="今日投资组合推荐",
        replace_existing=True,
    )
    scheduler.add_job(
        run_daily_etf,
        DateTrigger(run_date=run_base + timedelta(minutes=10)),
        id="today_etf",
        name="今日ETF筛选推荐",
        replace_existing=True,
    )

    # 正常 cron 从明天开始（misfire_grace_time 防止多跑）
    from apscheduler.triggers.cron import CronTrigger

    scheduler.add_job(
        run_daily_candidate_screening,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=30, start_date=tomorrow),
        id="daily_candidate_screening",
        name="每日候选股筛选",
        misfire_grace_time=_MISSED_GRACE_SECONDS,
        replace_existing=True,
    )
    scheduler.add_job(
        run_daily_factor_update,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=35, start_date=tomorrow),
        id="daily_factor_update",
        name="日终前瞻因子更新",
        misfire_grace_time=_MISSED_GRACE_SECONDS,
        replace_existing=True,
    )
    scheduler.add_job(
        run_portfolio_recommendation,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=36, start_date=tomorrow),
        id="daily_portfolio_recommendation",
        name="每日投资组合推荐",
        misfire_grace_time=_MISSED_GRACE_SECONDS,
        replace_existing=True,
    )
    scheduler.add_job(
        run_daily_etf,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=40, start_date=tomorrow),
        id="daily_etf",
        name="每日ETF筛选推荐",
        misfire_grace_time=_MISSED_GRACE_SECONDS,
        replace_existing=True,
    )

    scheduler.start()
    logger.info("定时任务已启动（今日任务安排在 %s 执行）", today_at)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main():
    logger = _setup_logging()
    parser = argparse.ArgumentParser(description="vn.py 独立定时任务调度器")
    parser.add_argument("--daemon", action="store_true", help="后台守护进程模式")
    parser.add_argument("--stop", action="store_true", help="停止运行中的调度器")
    parser.add_argument("--status", action="store_true", help="查看调度器状态")
    parser.add_argument(
        "--run-today-at",
        metavar="HH:MM",
        help="今日每日任务统一安排在指定时间执行（格式 16:00），"
        "已执行的自动跳过，正常 cron 从明天生效",
    )
    args = parser.parse_args()

    # ── 状态查询 ──
    if args.status:
        pid = _read_pid()
        if pid and _is_running(pid):
            print(f"调度器运行中 (PID: {pid})")
            sys.exit(0)
        else:
            if pid:
                _remove_pid()
            print("调度器未运行")
            sys.exit(1)

    # ── 停止 ──
    if args.stop:
        pid = _read_pid()
        if pid and _is_running(pid):
            print(f"正在停止调度器 (PID: {pid})...")
            os.kill(pid, signal.SIGTERM)
            # 等待进程退出
            for _ in range(10):
                if not _is_running(pid):
                    break
                time.sleep(0.5)
            _remove_pid()
            print("调度器已停止")
        else:
            _remove_pid()
            print("调度器未在运行")
        sys.exit(0)

    # ── 后台模式 ──
    if args.daemon:
        pid = os.fork()
        if pid > 0:
            print(f"调度器已后台启动 (PID: {pid})")
            sys.exit(0)
        # 子进程：写入子进程的 PID
        _write_pid()

    # ── 前台运行（包括 daemon 的子进程） ──
    if not args.daemon:
        _write_pid()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    logger.info("=" * 50)
    logger.info("vn.py 独立定时任务调度器启动 (PID: %s)", os.getpid())
    logger.info("日志文件: %s", LOG_DIR / "scheduler.log")
    logger.info("=" * 50)

    if args.run_today_at:
        _init_scheduler_with_override(args.run_today_at, logger)
    else:
        init_scheduler()
        _catch_up_missed_tasks()

    try:
        while not _shutdown_requested:
            time.sleep(5)
    except KeyboardInterrupt:
        _signal_handler(signal.SIGINT, None)

    _remove_pid()


if __name__ == "__main__":
    main()
