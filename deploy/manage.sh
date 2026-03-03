#!/bin/bash
# Crypto Analyzer Bot - 管理脚本
# 简化常用操作

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SERVICE_NAME="crypto-bot"
PROJECT_DIR="/opt/crypto-analyzer-bot"

# 显示帮助
show_help() {
    echo -e "${GREEN}Crypto Analyzer Bot 管理脚本${NC}"
    echo ""
    echo "用法: ./manage.sh [命令]"
    echo ""
    echo "命令:"
    echo "  start       启动 Bot"
    echo "  stop        停止 Bot"
    echo "  restart     重启 Bot"
    echo "  status      查看状态"
    echo "  logs        查看日志"
    echo "  logs-error  查看错误日志"
    echo "  update      更新代码并重启"
    echo "  backup      备份数据库"
    echo "  shell       进入项目虚拟环境"
    echo "  edit-env    编辑环境变量"
    echo ""
}

# 检查权限
check_sudo() {
    if [ "$EUID" -ne 0 ]; then 
        echo -e "${RED}请使用 sudo 运行此命令${NC}"
        exit 1
    fi
}

# 启动
start_bot() {
    check_sudo
    echo -e "${YELLOW}启动 Bot...${NC}"
    systemctl start ${SERVICE_NAME}
    sleep 2
    systemctl status ${SERVICE_NAME} --no-pager
}

# 停止
stop_bot() {
    check_sudo
    echo -e "${YELLOW}停止 Bot...${NC}"
    systemctl stop ${SERVICE_NAME}
    echo -e "${GREEN}已停止${NC}"
}

# 重启
restart_bot() {
    check_sudo
    echo -e "${YELLOW}重启 Bot...${NC}"
    systemctl restart ${SERVICE_NAME}
    sleep 2
    systemctl status ${SERVICE_NAME} --no-pager
}

# 查看状态
show_status() {
    check_sudo
    systemctl status ${SERVICE_NAME} --no-pager
}

# 查看日志
show_logs() {
    check_sudo
    echo -e "${YELLOW}按 Ctrl+C 退出日志查看${NC}"
    tail -f ${PROJECT_DIR}/logs/bot.log
}

# 查看错误日志
show_error_logs() {
    check_sudo
    echo -e "${YELLOW}按 Ctrl+C 退出日志查看${NC}"
    tail -f ${PROJECT_DIR}/logs/bot_error.log
}

# 更新代码
update_bot() {
    check_sudo
    echo -e "${YELLOW}更新代码...${NC}"
    
    cd ${PROJECT_DIR}
    
    # 保存当前版本
    OLD_VERSION=$(git rev-parse --short HEAD)
    
    # 拉取最新代码
    git fetch origin
    git reset --hard origin/main
    
    NEW_VERSION=$(git rev-parse --short HEAD)
    
    if [ "$OLD_VERSION" = "$NEW_VERSION" ]; then
        echo -e "${GREEN}已经是最新版本 (${NEW_VERSION})${NC}"
    else
        echo -e "${GREEN}代码已更新: ${OLD_VERSION} -> ${NEW_VERSION}${NC}"
        
        # 更新依赖
        echo -e "${YELLOW}更新依赖...${NC}"
        source venv/bin/activate
        pip install -r requirements.txt
        
        # 重启服务
        echo -e "${YELLOW}重启服务...${NC}"
        systemctl restart ${SERVICE_NAME}
        
        echo -e "${GREEN}更新完成!${NC}"
    fi
}

# 备份数据库
backup_db() {
    check_sudo
    BACKUP_DIR="${PROJECT_DIR}/backups"
    mkdir -p ${BACKUP_DIR}
    
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="${BACKUP_DIR}/trades_${TIMESTAMP}.db"
    
    echo -e "${YELLOW}备份数据库...${NC}"
    cp ${PROJECT_DIR}/data/trades.db ${BACKUP_FILE}
    
    echo -e "${GREEN}备份完成: ${BACKUP_FILE}${NC}"
    
    # 清理旧备份（保留最近10个）
    ls -t ${BACKUP_DIR}/trades_*.db | tail -n +11 | xargs -r rm
    echo -e "${YELLOW}已清理旧备份${NC}"
}

# 进入虚拟环境
enter_shell() {
    check_sudo
    cd ${PROJECT_DIR}
    echo -e "${YELLOW}进入虚拟环境...${NC}"
    echo -e "${BLUE}提示: 输入 'exit' 退出${NC}"
    sudo -u $(stat -c '%U' ${PROJECT_DIR}) bash -c "source venv/bin/activate && bash"
}

# 编辑环境变量
edit_env() {
    check_sudo
    if command -v vim &> /dev/null; then
        vim ${PROJECT_DIR}/.env
    elif command -v nano &> /dev/null; then
        nano ${PROJECT_DIR}/.env
    else
        echo -e "${RED}未找到编辑器，请手动编辑: ${PROJECT_DIR}/.env${NC}"
    fi
    
    echo -e "${YELLOW}环境变量已修改，建议重启服务: ./manage.sh restart${NC}"
}

# 主逻辑
case "${1:-help}" in
    start)
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    restart)
        restart_bot
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    logs-error)
        show_error_logs
        ;;
    update)
        update_bot
        ;;
    backup)
        backup_db
        ;;
    shell)
        enter_shell
        ;;
    edit-env)
        edit_env
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}未知命令: $1${NC}"
        show_help
        exit 1
        ;;
esac
