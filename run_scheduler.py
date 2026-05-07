#!/usr/bin/env python3
"""独立运行的后台定时任务调度器

用法:
  python run_scheduler.py                      # 前台运行（日志输出到控制台）
  python run_scheduler.py --daemon             # 后台守护进程模式
  python run_scheduler.py --status             # 检查运行状态
  python run_scheduler.py --stop               # 停止后台进程
  python run_scheduler.py --install            # 安装 macOS launchd 开机自启
  python run_scheduler.py --run-today-at 16:30 # 今日每日任务统一按指定时间执行
  python run_scheduler.py --no-catch-up        # 启动但不补跑漏掉的任务

架构:
  - 独立于 Flask 运行，互不干扰
  - 启动时检测今日每日任务是否已完成，未完成则按序补跑
  - 补跑无时间门控，仅看数据是否已存在
  - 单实例保护：同一 PID 文件防止重复启动
"""

import argparse
import atexit
import logging
import os
import signal
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# 路径
LOG_DIR = PROJECT_ROOT / "logs"
PID_FILE = PROJECT_ROOT / ".scheduler.pid"

# 日志
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "scheduler.log"


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        ],
    )
    return logging.getLogger("Scheduler")


logger = _setup_logging()

# ---------------------------------------------------------------------------
# PID 管理
# ---------------------------------------------------------------------------


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return None


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# 信号处理
# ---------------------------------------------------------------------------

_shutdown_requested = False


def _signal_handler(signum, _frame):
    global _shutdown_requested
    if _shutdown_requested:
        return
    _shutdown_requested = True
    logger.info("收到信号 %s，正在关闭调度器...", signum)
    from web_app.scheduler_tasks import shutdown_scheduler

    shutdown_scheduler()
    _remove_pid()
    logger.info("调度器已关闭")
    sys.exit(0)


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


def _write_pid():
    PID_FILE.write_text(str(os.getpid()))


def _remove_pid():
    PID_FILE.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 启动补跑
# ---------------------------------------------------------------------------


def _run_catch_up():
    """启动时补跑今日漏掉的每日任务"""
    from web_app.scheduler_tasks import run_startup_catch_up

    logger.info("检查今日每日任务执行状态...")
    try:
        run_startup_catch_up()
    except Exception as e:
        logger.error("启动补跑异常: %s", e)


# ---------------------------------------------------------------------------
# 今日时间覆盖
# ---------------------------------------------------------------------------


def _init_with_override(run_at: str):
    """每日任务按指定时间执行（--run-today-at），正常 cron 从明天生效"""
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    from web_app.scheduler_tasks import (
        _MISSED_GRACE_SECONDS,
        recalc_dirty_strategies,
        recover_stuck_strategies,
        run_daily_candidate_screening,
        run_daily_etf,
        run_daily_factor_update,
        run_portfolio_recommendation,
        scheduler,
    )

    hour, minute = map(int, run_at.split(":"))
    run_base = datetime.combine(date.today(), datetime.strptime(run_at, "%H:%M").time())
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

    # 今日一次性任务（顺序间隔执行）
    scheduler.add_job(
        run_daily_candidate_screening,
        DateTrigger(run_date=run_base),
        id="today_screening",
        name="今日候选股筛选",
        replace_existing=True,
    )
    scheduler.add_job(
        run_daily_factor_update,
        DateTrigger(run_date=run_base + timedelta(minutes=2)),
        id="today_factor_update",
        name="今日日终因子更新",
        replace_existing=True,
    )
    scheduler.add_job(
        run_portfolio_recommendation,
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

    # 正常 cron 从明天开始
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

    if not scheduler.running:
        scheduler.start()
    logger.info("定时任务已启动（今日任务安排在 %s 执行）", run_at)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def run_foreground(no_catch_up: bool = False):
    """前台运行 scheduler"""
    # 单实例保护
    existing_pid = _read_pid()
    if existing_pid and _is_running(existing_pid):
        logger.error("Scheduler 已在运行 (PID=%d)，拒绝重复启动", existing_pid)
        print(f"错误：Scheduler 已在运行 (PID={existing_pid})")
        print("运行 'python run_scheduler.py --status' 查看状态")
        print("运行 'python run_scheduler.py --stop' 停止旧进程")
        sys.exit(1)

    from web_app.scheduler_tasks import init_scheduler

    init_scheduler()
    logger.info("Scheduler 已启动，PID=%d", os.getpid())
    _write_pid()

    # 注册退出清理
    atexit.register(_remove_pid)

    # 启动补跑（可选）
    if not no_catch_up:
        _run_catch_up()

    # 保持进程存活
    try:
        while not _shutdown_requested:
            time.sleep(10)
    except KeyboardInterrupt:
        _signal_handler(signal.SIGINT, None)


# ---------------------------------------------------------------------------
# launchd 管理
# ---------------------------------------------------------------------------


def write_launchd_plist():
    """生成 launchd plist 文件（macOS 开机自启）"""
    import plistlib

    plist = {
        "Label": "com.vnpy.scheduler",
        "ProgramArguments": [sys.executable, str(PROJECT_ROOT / "run_scheduler.py")],
        "WorkingDirectory": str(PROJECT_ROOT),
        "StandardOutPath": str(LOG_FILE),
        "StandardErrorPath": str(LOG_FILE),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
    }

    plist_path = Path.home() / "Library/LaunchAgents/com.vnpy.scheduler.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(plistlib.dumps(plist))
    print(f"launchd plist 已写入: {plist_path}")
    print()
    print("加载并启动：")
    print(f"  launchctl load {plist_path}")
    print("  launchctl start com.vnpy.scheduler")
    print()
    print("停止并卸载：")
    print("  launchctl stop com.vnpy.scheduler")
    print(f"  launchctl unload {plist_path}")


def check_status():
    """检查运行状态"""
    pid = _read_pid()
    if pid and _is_running(pid):
        print(f"Scheduler 正在运行 (PID={pid})")
        print(f"日志文件: {LOG_FILE}")
    else:
        if pid:
            _remove_pid()
        print("Scheduler 未运行")
        print(f"日志文件: {LOG_FILE}")


def stop_scheduler():
    """停止后台 scheduler"""
    pid = _read_pid()
    if pid and _is_running(pid):
        print(f"正在停止 Scheduler (PID={pid})...")
        os.kill(pid, signal.SIGTERM)
        for _ in range(20):
            if not _is_running(pid):
                break
            time.sleep(0.5)
        _remove_pid()
        print("Scheduler 已停止")
    else:
        _remove_pid()
        print("Scheduler 未在运行")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="vnpy 独立定时任务调度器")
    parser.add_argument("--daemon", action="store_true", help="后台守护进程模式")
    parser.add_argument("--status", action="store_true", help="检查运行状态")
    parser.add_argument("--stop", action="store_true", help="停止运行中的调度器")
    parser.add_argument(
        "--install", action="store_true", help="安装 macOS launchd 开机自启"
    )
    parser.add_argument(
        "--run-today-at",
        metavar="HH:MM",
        help="今日每日任务统一安排在指定时间执行（如 16:30），已执行则跳过",
    )
    parser.add_argument(
        "--no-catch-up",
        action="store_true",
        help="启动时不补跑漏掉的任务（仅启动 cron 调度）",
    )
    args = parser.parse_args()

    if args.status:
        check_status()
    elif args.stop:
        stop_scheduler()
    elif args.install:
        write_launchd_plist()
    elif args.daemon:
        pid = os.fork()
        if pid > 0:
            print(f"调度器已后台启动 (PID: {pid})")
            sys.exit(0)
        # 子进程：初始化 + 运行
        if args.run_today_at:
            _init_with_override(args.run_today_at)
        else:
            run_foreground(no_catch_up=args.no_catch_up)
        # 写子进程 PID（在 fork 后，确保是实际运行进程的 PID）
    elif args.run_today_at:
        _init_with_override(args.run_today_at)
        try:
            while not _shutdown_requested:
                time.sleep(10)
        except KeyboardInterrupt:
            _signal_handler(signal.SIGINT, None)
    else:
        run_foreground(no_catch_up=args.no_catch_up)
