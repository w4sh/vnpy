#!/bin/bash
# Tushare下载监控脚本

LOG_FILE="download_tushare.log"
PROGRESS_FILE="download_progress_tushare.json"

echo "========================================"
echo "Tushare下载监控"
echo "========================================"

# 检查进程
PID=$(cat download_tushare.pid 2>/dev/null)
if ps -p $PID > /dev/null 2>&1; then
    echo "✓ 进程运行中 (PID: $PID)"
else
    echo "✗ 进程未运行"
    exit 1
fi

# 最新进度
echo ""
echo "最新进度："
tail -20 "$LOG_FILE" | grep -E "批次完成|总进度" | tail -3

# 检查成功/失败比例
SUCCESS=$(tail -100 "$LOG_FILE" | grep "✓" | wc -l | tr -d ' ')
FAILED=$(tail -100 "$LOG_FILE" | grep "✗" | wc -l | tr -d ' ')
TOTAL=$((SUCCESS + FAILED))

if [ $TOTAL -gt 0 ]; then
    RATE=$((SUCCESS * 100 / TOTAL))
    echo ""
    echo "最近成功率: $SUCCESS/$TOTAL ($RATE%)"
fi

# 估算剩余时间
if [ $SUCCESS -gt 0 ]; then
    ELAPSED=$(ps -p $PID -o etime= | tr -d ' ')
    echo "运行时间: $ELAPSED"
fi

echo ""
echo "========================================"
echo "实时日志（最后10行）："
echo "========================================"
tail -10 "$LOG_FILE"

echo ""
echo "提示：使用 'tail -f download_tushare.log' 查看实时日志"
