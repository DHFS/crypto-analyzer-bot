# 🚀 腾讯云部署指南

本文档介绍如何将 Crypto Analyzer Bot 部署到腾讯云服务器。

## 📋 前置要求

- 腾讯云账号
- 已购买轻量应用服务器或 CVM（推荐配置：2核4G，Ubuntu 22.04）
- 已配置安全组，开放必要端口（Bot 只需要出站访问）
- 本地已安装 SSH 客户端

## 🛒 服务器选购建议

### 轻量应用服务器（推荐新手）
- **配置**: 2核4G，60GB SSD
- **带宽**: 4Mbps
- **系统**: Ubuntu 22.04 LTS
- **价格**: 约 60-100元/月
- **适用**: 个人使用，10-20个 Discord 服务器

### 云服务器 CVM
- **配置**: 2核4G，50GB 云硬盘
- **带宽**: 按流量计费（1-5Mbps）
- **系统**: Ubuntu 22.04 LTS
- **适用**: 高并发，商业用途

## 🔐 安全配置

### 1. 创建 SSH 密钥对

在腾讯云控制台创建 SSH 密钥对，下载私钥到本地：
```bash
# 设置私钥权限（本地执行）
chmod 600 /path/to/your-key.pem
```

### 2. 配置安全组

| 类型 | 来源 | 端口 | 说明 |
|------|------|------|------|
| 入站 | 0.0.0.0/0 | 22 | SSH (可限制为本地 IP) |
| 出站 | 0.0.0.0/0 | ALL | 允许所有出站 (Discord/Binance API) |

**注意**: Bot 只需要出站访问 Discord 和 Binance API，不需要开放入站端口（SSH 除外）。

## 📦 部署步骤

### 方式一：自动部署（推荐）

#### 1. 连接服务器

```bash
ssh -i /path/to/your-key.pem ubuntu@your-server-ip
```

#### 2. 下载并运行部署脚本

```bash
# 下载部署脚本
curl -fsSL https://raw.githubusercontent.com/DHFS/crypto-analyzer-bot/main/deploy/install.sh -o install.sh

# 运行部署脚本
sudo bash install.sh
```

#### 3. 配置环境变量

```bash
# 编辑环境变量文件
sudo vim /opt/crypto-analyzer-bot/.env
```

填入以下必需配置：
```env
DISCORD_BOT_TOKEN=your_discord_bot_token
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret
MOONSHOT_API_KEY=your_moonshot_api_key
```

#### 4. 启动服务

```bash
sudo systemctl start crypto-bot
sudo systemctl enable crypto-bot  # 设置开机自启
```

#### 5. 查看日志

```bash
sudo tail -f /opt/crypto-analyzer-bot/logs/bot.log
```

### 方式二：手动部署

如果你希望更细致地控制部署过程，可以按以下步骤手动部署：

#### 1. 系统更新

```bash
sudo apt-get update && sudo apt-get upgrade -y
```

#### 2. 安装 Python 3.10

```bash
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt-get update
sudo apt-get install -y python3.10 python3.10-venv python3.10-pip
```

#### 3. 克隆项目

```bash
sudo mkdir -p /opt
sudo git clone https://github.com/DHFS/crypto-analyzer-bot.git /opt/crypto-analyzer-bot
```

#### 4. 安装依赖

```bash
cd /opt/crypto-analyzer-bot
sudo python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 5. 配置环境变量

```bash
sudo cp deploy/.env.example .env
sudo vim .env  # 填入配置
```

#### 6. 设置权限

```bash
sudo chown -R ubuntu:ubuntu /opt/crypto-analyzer-bot
sudo chmod 775 /opt/crypto-analyzer-bot/data
sudo chmod 775 /opt/crypto-analyzer-bot/logs
```

#### 7. 配置 systemd 服务

创建 `/etc/systemd/system/crypto-bot.service`：

```ini
[Unit]
Description=Crypto Analyzer Bot
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/crypto-analyzer-bot
Environment=PATH=/opt/crypto-analyzer-bot/venv/bin
ExecStart=/opt/crypto-analyzer-bot/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=append:/opt/crypto-analyzer-bot/logs/bot.log
StandardError=append:/opt/crypto-analyzer-bot/logs/bot_error.log

[Install]
WantedBy=multi-user.target
```

#### 8. 启动服务

```bash
sudo systemctl daemon-reload
sudo systemctl start crypto-bot
sudo systemctl enable crypto-bot
```

## 🔄 自动部署（GitHub Actions）

配置 GitHub Actions 实现推代码自动部署：

### 1. 配置 GitHub Secrets

在 GitHub 仓库 Settings -> Secrets and variables -> Actions 中添加：

| Secret 名称 | 说明 |
|------------|------|
| `TENCENT_CLOUD_HOST` | 腾讯云服务器 IP |
| `TENCENT_CLOUD_USER` | SSH 用户名 (如 ubuntu) |
| `TENCENT_CLOUD_SSH_KEY` | SSH 私钥完整内容 |

### 2. 部署密钥配置

将本地公钥添加到服务器的 `~/.ssh/authorized_keys`：

```bash
# 本地生成密钥对（如果没有）
ssh-keygen -t rsa -b 4096 -C "github-actions"

# 复制公钥到服务器
ssh-copy-id -i ~/.ssh/id_rsa.pub ubuntu@your-server-ip

# 将私钥内容添加到 GitHub Secrets
# Settings -> Secrets -> New repository secret
# Name: TENCENT_CLOUD_SSH_KEY
# Value: cat ~/.ssh/id_rsa 的内容
```

### 3. 自动部署

配置完成后，每次推送到 `main` 分支都会自动触发部署。

手动触发：
- 进入 GitHub 仓库 -> Actions -> Deploy to Tencent Cloud -> Run workflow

## 📊 日常运维

### 使用管理脚本

```bash
# 下载管理脚本
sudo curl -fsSL https://raw.githubusercontent.com/DHFS/crypto-analyzer-bot/main/deploy/manage.sh -o /usr/local/bin/bot-manage
sudo chmod +x /usr/local/bin/bot-manage

# 常用命令
sudo bot-manage start       # 启动
sudo bot-manage stop        # 停止
sudo bot-manage restart     # 重启
sudo bot-manage status      # 查看状态
sudo bot-manage logs        # 查看日志
sudo bot-manage update      # 更新代码
sudo bot-manage backup      # 备份数据库
```

### 手动管理

```bash
# 启动
sudo systemctl start crypto-bot

# 停止
sudo systemctl stop crypto-bot

# 重启
sudo systemctl restart crypto-bot

# 查看状态
sudo systemctl status crypto-bot

# 查看日志
sudo journalctl -u crypto-bot -f
sudo tail -f /opt/crypto-analyzer-bot/logs/bot.log
```

### 数据库备份

```bash
# 手动备份
sudo cp /opt/crypto-analyzer-bot/data/trades.db /opt/crypto-analyzer-bot/backups/trades_$(date +%Y%m%d_%H%M%S).db

# 或使用管理脚本
sudo bot-manage backup
```

建议设置定时自动备份：

```bash
# 编辑 crontab
sudo crontab -e

# 添加每日备份任务
0 2 * * * /usr/local/bin/bot-manage backup
```

## 🔍 故障排查

### 查看日志

```bash
# Bot 日志
sudo tail -f /opt/crypto-analyzer-bot/logs/bot.log

# 系统日志
sudo journalctl -u crypto-bot -f

# 错误日志
sudo tail -f /opt/crypto-analyzer-bot/logs/bot_error.log
```

### 常见问题

#### 1. Bot 无法启动

```bash
# 检查环境变量
sudo cat /opt/crypto-analyzer-bot/.env | grep -E "TOKEN|KEY"

# 检查权限
ls -la /opt/crypto-analyzer-bot/

# 手动运行查看错误
sudo -u ubuntu bash -c "cd /opt/crypto-analyzer-bot && source venv/bin/activate && python main.py"
```

#### 2. 数据库权限错误

```bash
sudo chown -R ubuntu:ubuntu /opt/crypto-analyzer-bot/data
sudo chmod 775 /opt/crypto-analyzer-bot/data
```

#### 3. 网络连接问题

```bash
# 测试 Discord 连接
curl -I https://discord.com

# 测试 Binance 连接
curl -I https://fapi.binance.com

# 检查系统时间（时间不同步会导致 API 错误）
date
timedatectl status
```

#### 4. 服务崩溃自动重启

服务已配置 `Restart=always`，如果 Bot 崩溃会自动重启。

查看重启历史：
```bash
sudo systemctl status crypto-bot --no-pager
```

## 🛡️ 安全建议

1. **定期更新系统**
   ```bash
   sudo apt-get update && sudo apt-get upgrade -y
   ```

2. **限制 SSH 访问**
   - 使用密钥登录，禁用密码登录
   - 修改默认 SSH 端口（可选）
   - 配置 fail2ban 防止暴力破解

3. **API Key 安全**
   - 定期轮换 API Keys
   - 使用最小权限原则
   - 不要将 .env 文件提交到 Git

4. **防火墙配置**
   ```bash
   sudo ufw enable
   sudo ufw default deny incoming
   sudo ufw default allow outgoing
   sudo ufw allow 22/tcp
   ```

## 📞 获取帮助

如果遇到问题：

1. 查看日志：`sudo bot-manage logs`
2. 检查服务状态：`sudo bot-manage status`
3. 提交 Issue：https://github.com/DHFS/crypto-analyzer-bot/issues

## 📝 更新记录

- 2024-03: 初始部署指南
