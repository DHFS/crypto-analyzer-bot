"""Crypto Analyzer Bot - Discord 加密货币行情分析机器人

使用方法:
1. 复制 .env.example 为 .env 并填写配置
2. pip install -r requirements.txt
3. python main.py
"""
import os
import sys
import logging
import asyncio
import signal
import time
import discord
from discord import app_commands

from config import config
from services.alert import alert_service, alert_monitor_task
from services.database import get_database_service
from services.tracker import get_trade_tracker

from handlers import setup_commands

# 数据库和追踪器服务实例
db_service = get_database_service()
trade_tracker = get_trade_tracker()

# 配置日志
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class CryptoAnalyzerBot(discord.Client):
    """加密货币分析机器人主类 - 增强连接稳定性"""
    
    def __init__(self):
        # 设置 intents
        intents = discord.Intents.default()
        intents.message_content = True

        # 使用代理（您的网络环境需要代理访问 Discord）
        proxy = config.HTTP_PROXY if config.HTTP_PROXY else None
        super().__init__(intents=intents, proxy=proxy)

        # 创建命令树
        self.tree = app_commands.CommandTree(self)
        
        # 服务状态跟踪
        self.services_ready = False
        self.reconnect_count = 0
        self.max_reconnects = 10

    async def setup_hook(self):
        """Bot 启动时的钩子，用于注册命令和启动后台任务"""
        logger.info("🔧 正在初始化 Bot...")
        
        # 1. 初始化数据库
        await db_service.init_db()
        logger.info("✅ 数据库已初始化")
        
        # 2. 注册斜杠命令
        setup_commands(self, self.tree)

        # 3. 同步命令到 Discord
        await self.tree.sync()
        logger.info("✅ 斜杠命令已同步")
        
        # 4. 设置预警服务的 Bot 实例
        alert_service.set_bot(self)
        
        # 5. 加载已保存的预警
        alert_service.load_from_file()
        
        # 6. 启动预警监控任务
        if not alert_monitor_task.is_running():
            alert_monitor_task.start()
            logger.info("🚨 预警监控任务已启动 (每5分钟检查一次)")
        
        # 7. 启动订单追踪器
        await trade_tracker.start(interval_minutes=5)
        
        self.services_ready = True
        self.reconnect_count = 0  # 重置重连计数
        logger.info("✅ 所有服务初始化完成")

    async def on_ready(self):
        """Bot 就绪时的回调"""
        logger.info(f"🚀 Bot 已登录: {self.user}")
        logger.info(f"📊 默认AI模型: {config.DEFAULT_AI_MODEL}")
        logger.info(f"🔔 当前活跃预警数: {len([a for a in alert_service.alerts.values() if a.is_active])}")
        logger.info(f"🔗 邀请链接: https://discord.com/api/oauth2/authorize?client_id={self.user.id}&permissions=2147483648&scope=bot%20applications.commands")

        # 设置状态
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="/help 查看帮助 | /alert_add 设置预警"
            )
        )

    async def on_disconnect(self):
        """断开连接时的回调"""
        self.reconnect_count += 1
        logger.warning(f"⚠️ Bot 连接断开 (第 {self.reconnect_count} 次)")
        
        if self.reconnect_count >= self.max_reconnects:
            logger.error(f"❌ 重连次数超过 {self.max_reconnects} 次，准备退出")
            await self.close()
    
    async def on_resumed(self):
        """连接恢复时的回调"""
        logger.info("✅ Bot 连接恢复")
        self.reconnect_count = 0  # 重置重连计数

    async def on_error(self, event_method, *args, **kwargs):
        """处理事件错误"""
        logger.error(f"❌ 事件错误 ({event_method}): {args}, {kwargs}", exc_info=True)

    async def close(self):
        """关闭 Bot 时的清理工作"""
        logger.info("🛑 正在关闭 Bot...")
        
        # 停止订单追踪器
        await trade_tracker.stop()
        
        # 停止预警任务
        if alert_monitor_task.is_running():
            alert_monitor_task.cancel()
            logger.info("🚨 预警监控任务已停止")
        
        # 保存预警到文件
        alert_service.save_to_file()
        logger.info("💾 预警数据已保存")
        
        # 关闭服务连接
        try:
            await alert_service.binance_service.close()
            logger.info("📊 Binance 服务已关闭")
        except Exception as e:
            logger.error(f"关闭服务时出错: {e}")
        
        await super().close()
        logger.info("👋 Bot 已安全关闭")


def run_bot():
    """运行 Bot（带自动重启）"""
    restart_count = 0
    max_restarts = 5
    
    while restart_count < max_restarts:
        try:
            # 检查必要配置
            if not config.DISCORD_BOT_TOKEN:
                logger.error("❌ 请在 .env 文件中配置 DISCORD_BOT_TOKEN")
                return 1
            
            if not config.BINANCE_API_KEY or not config.BINANCE_API_SECRET:
                logger.warning("⚠️ Binance API 未配置，部分功能可能无法使用")
            
            if not config.MOONSHOT_API_KEY:
                logger.warning("⚠️ Moonshot API 未配置，AI 分析功能将无法使用")

            bot = CryptoAnalyzerBot()
            logger.info(f"🚀 Crypto Analyzer Bot 启动中... (重启次数: {restart_count})")
            
            bot.run(config.DISCORD_BOT_TOKEN, reconnect=True)
            
            # 正常退出（非异常）
            logger.info("👋 Bot 正常退出")
            break
            
        except KeyboardInterrupt:
            logger.info("👋 收到中断信号，正在关闭...")
            break
            
        except Exception as e:
            restart_count += 1
            logger.error(f"❌ Bot 运行出错: {e}")
            
            if restart_count < max_restarts:
                wait_time = min(30 * restart_count, 300)  # 最多等待5分钟
                logger.info(f"⏳ {wait_time}秒后尝试第 {restart_count + 1} 次重启...")
                time.sleep(wait_time)
            else:
                logger.error(f"❌ 已达到最大重启次数 ({max_restarts})，退出")
                return 1
    
    return 0


def main():
    """主入口"""
    # 设置信号处理
    def signal_handler(sig, frame):
        logger.info(f"🛑 收到信号 {sig}，准备退出...")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # 运行 Bot
    exit_code = run_bot()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
