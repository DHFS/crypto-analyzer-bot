"""配置管理模块"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Discord
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

    # Binance
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

    # AI Models
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    MOONSHOT_API_KEY = os.getenv("MOONSHOT_API_KEY", "")

    # 默认设置
    DEFAULT_AI_MODEL = os.getenv("DEFAULT_AI_MODEL", "gpt")

    # 代理设置
    HTTP_PROXY = os.getenv("HTTP_PROXY", "")

    # 支持的时间周期
    VALID_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

    # 支持的AI模型
    VALID_MODELS = ["gpt", "claude", "gemini", "kimi"]


config = Config()
