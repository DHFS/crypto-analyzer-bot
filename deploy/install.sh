#!/bin/bash
# Crypto Analyzer Bot - 腾讯云部署脚本
# 适用于 Ubuntu 22.04 LTS

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 配置变量
PROJECT_NAME="crypto-analyzer-bot"
PROJECT_DIR="/opt/${PROJECT_NAME}"
SERVICE_NAME="crypto-bot"
PYTHON_VERSION="3.10"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Crypto Analyzer Bot 部署脚本${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查是否以 root 运行
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}请使用 sudo 运行此脚本${NC}"
    exit 1
fi

# 获取当前用户名（用于设置权限）
CURRENT_USER=${SUDO_USER:-$USER}
echo -e "${YELLOW}当前用户: $CURRENT_USER${NC}"

# 1. 系统更新
echo -e "${YELLOW}[1/8] 更新系统包...${NC}"
apt-get update -y
apt-get upgrade -y

# 2. 安装基础依赖
echo -e "${YELLOW}[2/8] 安装基础依赖...${NC}"
apt-get install -y \
    git \
    curl \
    wget \
    vim \
    htop \
    sqlite3 \
    build-essential \
    libssl-dev \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    llvm \
    libncurses5-dev \
    libncursesw5-dev \
    xz-utils \
    tk-dev \
    libffi-dev \
    liblzma-dev

# 3. 安装 Python 3.10
echo -e "${YELLOW}[3/8] 安装 Python ${PYTHON_VERSION}...${NC}"
if ! command -v python${PYTHON_VERSION} &> /dev/null; then
    add-apt-repository ppa:deadsnakes/ppa -y
    apt-get update
    apt-get install -y python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-pip
fi

python${PYTHON_VERSION} --version

# 4. 创建项目目录
echo -e "${YELLOW}[4/8] 创建项目目录...${NC}"
mkdir -p ${PROJECT_DIR}
mkdir -p ${PROJECT_DIR}/data
mkdir -p ${PROJECT_DIR}/logs

# 5. 克隆代码（如果从GitHub部署）
if [ ! -f "${PROJECT_DIR}/main.py" ]; then
    echo -e "${YELLOW}[5/8] 从 GitHub 克隆项目...${NC}"
    cd /opt
    if [ -d "${PROJECT_DIR}" ]; then
        rm -rf ${PROJECT_DIR}
    fi
    git clone https://github.com/DHFS/crypto-analyzer-bot.git ${PROJECT_NAME}
else
    echo -e "${YELLOW}[5/8] 项目已存在，跳过克隆${NC}"
fi

# 6. 创建虚拟环境并安装依赖
echo -e "${YELLOW}[6/8] 安装 Python 依赖...${NC}"
cd ${PROJECT_DIR}
python${PYTHON_VERSION} -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

# 7. 设置权限
echo -e "${YELLOW}[7/8] 设置目录权限...${NC}"
chown -R ${CURRENT_USER}:${CURRENT_USER} ${PROJECT_DIR}
chmod 755 ${PROJECT_DIR}
chmod 775 ${PROJECT_DIR}/data
chmod 775 ${PROJECT_DIR}/logs

# 8. 配置 systemd 服务
echo -e "${YELLOW}[8/8] 配置 systemd 服务...${NC}"
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=Crypto Analyzer Bot
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
Group=${CURRENT_USER}
WorkingDirectory=${PROJECT_DIR}
Environment=PATH=${PROJECT_DIR}/venv/bin
ExecStart=${PROJECT_DIR}/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=append:${PROJECT_DIR}/logs/bot.log
StandardError=append:${PROJECT_DIR}/logs/bot_error.log

# 安全配置
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=false
ReadWritePaths=${PROJECT_DIR}/data ${PROJECT_DIR}/logs

[Install]
WantedBy=multi-user.target
EOF

# 重新加载 systemd
systemctl daemon-reload

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "项目目录: ${PROJECT_DIR}"
echo -e "数据目录: ${PROJECT_DIR}/data"
echo -e "日志目录: ${PROJECT_DIR}/logs"
echo ""
echo -e "${YELLOW}下一步操作:${NC}"
echo -e "1. 配置环境变量: ${GREEN}sudo vim ${PROJECT_DIR}/.env${NC}"
echo -e "2. 启动服务: ${GREEN}sudo systemctl start ${SERVICE_NAME}${NC}"
echo -e "3. 查看日志: ${GREEN}sudo tail -f ${PROJECT_DIR}/logs/bot.log${NC}"
echo -e "4. 设置开机自启: ${GREEN}sudo systemctl enable ${SERVICE_NAME}${NC}"
echo ""
echo -e "常用命令:"
echo -e "  启动: ${GREEN}sudo systemctl start ${SERVICE_NAME}${NC}"
echo -e "  停止: ${GREEN}sudo systemctl stop ${SERVICEName}${NC}"
echo -e "  重启: ${GREEN}sudo systemctl restart ${SERVICE_NAME}${NC}"
echo -e "  状态: ${GREEN}sudo systemctl status ${SERVICE_NAME}${NC}"
echo -e "  日志: ${GREEN}sudo journalctl -u ${SERVICE_NAME} -f${NC}"
