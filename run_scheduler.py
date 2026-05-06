#!/usr/bin/env python3
"""独立运行的后台定时任务

用法:
  python run_scheduler.py                     # 前台运行
  nohup python run_scheduler.py &             # 后台运行（简单模式）
  python run_scheduler.py --daemon            # 以后台守护进程模式运行
  python run_scheduler.py --status            # 检查运行状态
  python run_scheduler.py --stop              # 停止后台进程
"""

import os
import sys
import time
import signal
import logging
import argparse
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# 日志配置
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "scheduler.log"
PID_FILE = Path("/tmp/vnpy_scheduler.pid")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
    ],
)
logger = logging.getLogger("Scheduler")


def check_already_running():
    """检查是否已有 scheduler 实例在运行"""
    if not PID_FILE.exists():
        return False

    pid_str = PID_FILE.read_text().strip()
    if not pid_str:
        return False

    try:
        pid = int(pid_str)
        os.kill(pid, 0)  # 信号 0 只检测进程存在性
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        return False


def run_foreground():
    """前台运行 scheduler"""
    if check_already_running():
        existing_pid = PID_FILE.read_text().strip()
        logger.error("Scheduler 已在运行 (PID=%s)，请先停止旧进程再启动", existing_pid)
        print(f"错误：Scheduler 已在运行 (PID={existing_pid})")
        print(f"运行 '{sys.argv[0]} --status' 查看状态")
        print(f"运行 '{sys.argv[0]} --stop' 停止旧进程")
        sys.exit(1)

    from web_app.scheduler_tasks import init_scheduler
    from web_app.scheduler_tasks import scheduler

    init_scheduler()
    logger.info("Scheduler 已启动，PID=%d", os.getpid())

    # 写 PID 文件
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    try:
        # 保持进程存活
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭...")
        scheduler.shutdown()
        logger.info("Scheduler 已关闭")


def write_launchd_plist():
    """生成并写入 launchd plist 文件（macOS 开机自启）"""
    plist_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.vnpy.scheduler</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{script}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{cwd}</string>
    <key>StandardOutPath</key>
    <string>{log}</string>
    <key>StandardErrorPath</key>
    <string>{log}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
""".format(
        python=sys.executable,
        script=str(PROJECT_ROOT / "run_scheduler.py"),
        cwd=str(PROJECT_ROOT),
        log=str(LOG_FILE),
    )

    plist_path = Path.home() / "Library/LaunchAgents/com.vnpy.scheduler.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist_content, encoding="utf-8")
    print(f"launchd plist 已写入: {plist_path}")
    print("运行以下命令加载：")
    print(f"  launchctl load {plist_path}")
    print("  launchctl start com.vnpy.scheduler")


def check_status():
    """检查运行状态"""
    if PID_FILE.exists():
        pid = PID_FILE.read_text().strip()
        if os.path.exists(f"/proc/{pid}") or not os.path.exists("/proc"):
            # 尝试通过 kill 检查进程是否存在
            try:
                os.kill(int(pid), 0)
                print(f"Scheduler 正在运行 (PID={pid})")
                print(f"日志文件: {LOG_FILE}")
                return
            except (OSError, ProcessLookupError):
                pass
    print("Scheduler 未运行")
    print(f"日志文件: {LOG_FILE}")


def stop_scheduler():
    """停止后台 scheduler"""
    if not PID_FILE.exists():
        print("PID 文件不存在，scheduler 可能未运行")
        return

    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"已发送停止信号到进程 {pid}")
        PID_FILE.unlink(missing_ok=True)
    except ProcessLookupError:
        print(f"进程 {pid} 不存在")
        PID_FILE.unlink(missing_ok=True)
    except Exception as e:
        print(f"停止失败: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="vnpy 后台定时任务调度器")
    parser.add_argument("--daemon", action="store_true", help="后台守护进程模式")
    parser.add_argument("--status", action="store_true", help="检查运行状态")
    parser.add_argument("--stop", action="store_true", help="停止后台进程")
    parser.add_argument(
        "--install", action="store_true", help="安装 macOS launchd 开机自启"
    )
    args = parser.parse_args()

    if args.status:
        check_status()
    elif args.stop:
        stop_scheduler()
    elif args.install:
        write_launchd_plist()
    else:
        run_foreground()
