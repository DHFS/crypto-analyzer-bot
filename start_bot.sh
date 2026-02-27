#!/bin/bash
# Crypto Analyzer Bot 启动脚本
# 功能：启动 Bot 并监控状态，崩溃后自动重启

BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$BOT_DIR/bot.log"
PID_FILE="$BOT_DIR/bot.pid"
VENV_PYTHON="$BOT_DIR/venv/bin/python"

cd "$BOT_DIR"

# 检查虚拟环境
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ 虚拟环境未找到，请先运行: python -m venv venv"
    exit 1
fi

# 检查是否在运行
check_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0  # 正在运行
        fi
    fi
    return 1  # 未运行
}

# 启动 Bot
start_bot() {
    echo "🚀 启动 Crypto Analyzer Bot..."
    echo "日志文件: $LOG_FILE"
    
    # 清理旧日志（保留最后1000行）
    if [ -f "$LOG_FILE" ]; then
        tail -n 1000 "$LOG_FILE" > "$LOG_FILE.tmp"
        mv "$LOG_FILE.tmp" "$LOG_FILE"
    fi
    
    # 启动 Bot
    nohup "$VENV_PYTHON" main.py >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    
    sleep 3
    
    if check_running; then
        echo "✅ Bot 启动成功 (PID: $(cat $PID_FILE))"
        echo "查看日志: tail -f $LOG_FILE"
    else
        echo "❌ Bot 启动失败，查看日志: tail -20 $LOG_FILE"
        exit 1
    fi
}

# 停止 Bot
stop_bot() {
    if check_running; then
        PID=$(cat "$PID_FILE")
        echo "🛑 正在停止 Bot (PID: $PID)..."
        kill "$PID"
        sleep 2
        
        # 强制终止（如果需要）
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "⚠️ 强制终止..."
            kill -9 "$PID" 2>/dev/null
        fi
        
        rm -f "$PID_FILE"
        echo "✅ Bot 已停止"
    else
        echo "ℹ️ Bot 未在运行"
        rm -f "$PID_FILE"
    fi
}

# 查看状态
status_bot() {
    if check_running; then
        PID=$(cat "$PID_FILE")
        echo "✅ Bot 正在运行 (PID: $PID)"
        echo "日志最后5行:"
        tail -5 "$LOG_FILE" 2>/dev/null | grep -E "(Bot 已登录|ERROR|WARNING|已启动)" || tail -5 "$LOG_FILE"
    else
        echo "❌ Bot 未在运行"
        rm -f "$PID_FILE"
    fi
}

# 重启 Bot
restart_bot() {
    stop_bot
    sleep 1
    start_bot
}

# 主逻辑
case "${1:-start}" in
    start)
        if check_running; then
            echo "ℹ️ Bot 已经在运行 (PID: $(cat $PID_FILE))"
            exit 0
        fi
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    restart)
        restart_bot
        ;;
    status)
        status_bot
        ;;
    log)
        tail -f "$LOG_FILE"
        ;;
    *)
        echo "使用方法: $0 {start|stop|restart|status|log}"
        echo "  start   - 启动 Bot"
        echo "  stop    - 停止 Bot"
        echo "  restart - 重启 Bot"
        echo "  status  - 查看状态"
        echo "  log     - 查看实时日志"
        exit 1
        ;;
esac
