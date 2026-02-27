"""主动监控预警服务

实现基于技术指标的市场监控和自动预警功能
"""
import asyncio
import json
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import discord
from discord.ext import tasks

from services.binance import BinanceService
from services.indicators import IndicatorService


class AlertCondition(Enum):
    """预警条件类型"""
    RSI_OVERSOLD = "rsi_oversold"          # RSI < 30
    RSI_OVERBOUGHT = "rsi_overbought"      # RSI > 70
    MACD_GOLDEN_CROSS = "macd_golden"      # MACD 金叉
    MACD_DEAD_CROSS = "macd_dead"          # MACD 死叉
    BB_UPPER_TOUCH = "bb_upper"            # 触及布林带上轨
    BB_LOWER_TOUCH = "bb_lower"            # 触及布林带下轨
    PRICE_ABOVE = "price_above"            # 价格上破
    PRICE_BELOW = "price_below"            # 价格下破
    ATR_SPIKE = "atr_spike"                # ATR 异常波动


@dataclass
class Alert:
    """预警规则数据结构"""
    id: str                          # 唯一标识
    user_id: int                     # 创建者 Discord ID
    channel_id: int                  # 推送频道 ID
    symbol: str                      # 交易对
    condition: AlertCondition        # 触发条件
    params: Dict                     # 额外参数
    created_at: datetime             # 创建时间
    last_triggered: Optional[datetime] = None  # 上次触发时间
    trigger_count: int = 0           # 触发次数
    is_active: bool = True           # 是否激活
    cooldown_minutes: int = 60       # 冷却时间（避免重复预警）
    
    def to_dict(self) -> Dict:
        """转换为字典（用于持久化）"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "channel_id": self.channel_id,
            "symbol": self.symbol,
            "condition": self.condition.value,
            "params": self.params,
            "created_at": self.created_at.isoformat(),
            "last_triggered": self.last_triggered.isoformat() if self.last_triggered else None,
            "trigger_count": self.trigger_count,
            "is_active": self.is_active,
            "cooldown_minutes": self.cooldown_minutes,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Alert":
        """从字典创建实例"""
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            channel_id=data["channel_id"],
            symbol=data["symbol"],
            condition=AlertCondition(data["condition"]),
            params=data.get("params", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_triggered=datetime.fromisoformat(data["last_triggered"]) if data.get("last_triggered") else None,
            trigger_count=data.get("trigger_count", 0),
            is_active=data.get("is_active", True),
            cooldown_minutes=data.get("cooldown_minutes", 60),
        )
    
    def is_in_cooldown(self) -> bool:
        """检查是否在冷却期"""
        if self.last_triggered is None:
            return False
        cooldown_end = self.last_triggered + timedelta(minutes=self.cooldown_minutes)
        return datetime.now() < cooldown_end
    
    def get_cooldown_remaining(self) -> Optional[int]:
        """获取剩余冷却时间（分钟）"""
        if not self.is_in_cooldown():
            return None
        cooldown_end = self.last_triggered + timedelta(minutes=self.cooldown_minutes)
        remaining = (cooldown_end - datetime.now()).total_seconds() / 60
        return int(remaining)


@dataclass
class AlertTrigger:
    """预警触发结果"""
    alert: Alert
    triggered_at: datetime
    price: float
    message: str
    indicators: Dict
    severity: str  # info, warning, critical


class AlertService:
    """预警服务核心类"""
    
    def __init__(self):
        self.alerts: Dict[str, Alert] = {}  # alert_id -> Alert
        self.binance_service = BinanceService()
        self.indicator_service = IndicatorService()
        self.bot: Optional[discord.Client] = None
        self.on_trigger_callbacks: List[Callable] = []
        
    def set_bot(self, bot: discord.Client):
        """设置 Discord Bot 实例（用于发送消息）"""
        self.bot = bot
    
    def add_callback(self, callback: Callable[[AlertTrigger], None]):
        """添加触发回调函数"""
        self.on_trigger_callbacks.append(callback)
    
    def create_alert(
        self,
        user_id: int,
        channel_id: int,
        symbol: str,
        condition_str: str,
        params: Optional[Dict] = None
    ) -> Alert:
        """
        创建新的预警规则
        
        Args:
            user_id: Discord 用户ID
            channel_id: Discord 频道ID
            symbol: 交易对
            condition_str: 条件字符串 (如 "rsi_oversold")
            params: 额外参数
            
        Returns:
            Alert: 创建的预警对象
        """
        try:
            condition = AlertCondition(condition_str.lower())
        except ValueError:
            valid_conditions = [c.value for c in AlertCondition]
            raise ValueError(f"无效的条件: {condition_str}。有效选项: {valid_conditions}")
        
        alert_id = f"{user_id}_{symbol}_{condition.value}_{int(datetime.now().timestamp())}"
        
        alert = Alert(
            id=alert_id,
            user_id=user_id,
            channel_id=channel_id,
            symbol=symbol.upper(),
            condition=condition,
            params=params or {},
            created_at=datetime.now()
        )
        
        self.alerts[alert_id] = alert
        return alert
    
    def remove_alert(self, alert_id: str) -> bool:
        """删除预警规则"""
        if alert_id in self.alerts:
            del self.alerts[alert_id]
            return True
        return False
    
    def get_user_alerts(self, user_id: int) -> List[Alert]:
        """获取用户的所有预警"""
        return [a for a in self.alerts.values() if a.user_id == user_id]
    
    def get_channel_alerts(self, channel_id: int) -> List[Alert]:
        """获取频道的所有预警"""
        return [a for a in self.alerts.values() if a.channel_id == channel_id]
    
    async def check_alert(self, alert: Alert) -> Optional[AlertTrigger]:
        """
        检查单个预警是否触发
        
        Args:
            alert: 预警规则
            
        Returns:
            AlertTrigger or None: 如果触发返回触发信息，否则返回None
        """
        # 检查是否在冷却期
        if alert.is_in_cooldown():
            return None
        
        # 检查是否激活
        if not alert.is_active:
            return None
        
        try:
            # 获取数据
            klines = await self.binance_service.get_klines(alert.symbol, "1h", limit=50)
            indicators = self.indicator_service.calculate_all(klines)
            price = indicators["current_price"]
            
            # 根据条件类型检查
            triggered = False
            message = ""
            severity = "info"
            
            condition = alert.condition
            
            if condition == AlertCondition.RSI_OVERSOLD:
                rsi = indicators.get("rsi")
                if rsi and rsi < 30:
                    triggered = True
                    message = f"RSI 超卖信号: **{rsi:.2f}** (< 30)"
                    severity = "warning"
                    
            elif condition == AlertCondition.RSI_OVERBOUGHT:
                rsi = indicators.get("rsi")
                if rsi and rsi > 70:
                    triggered = True
                    message = f"RSI 超买信号: **{rsi:.2f}** (> 70)"
                    severity = "warning"
                    
            elif condition == AlertCondition.MACD_GOLDEN_CROSS:
                macd_trend = indicators.get("macd", {}).get("trend")
                if macd_trend == "golden_cross":
                    triggered = True
                    message = "MACD 金叉信号出现"
                    severity = "info"
                    
            elif condition == AlertCondition.MACD_DEAD_CROSS:
                macd_trend = indicators.get("macd", {}).get("trend")
                if macd_trend == "dead_cross":
                    triggered = True
                    message = "MACD 死叉信号出现"
                    severity = "warning"
                    
            elif condition == AlertCondition.BB_UPPER_TOUCH:
                bb_position = indicators.get("bollinger", {}).get("position")
                if bb_position == "upper_band":
                    triggered = True
                    message = f"价格触及布林带上轨: **{price:.4f}**"
                    severity = "info"
                    
            elif condition == AlertCondition.BB_LOWER_TOUCH:
                bb_position = indicators.get("bollinger", {}).get("position")
                if bb_position == "lower_band":
                    triggered = True
                    message = f"价格触及布林带下轨: **{price:.4f}**"
                    severity = "info"
                    
            elif condition == AlertCondition.PRICE_ABOVE:
                threshold = alert.params.get("threshold")
                if threshold and price > float(threshold):
                    triggered = True
                    message = f"价格上破阈值: **{price:.4f}** > {threshold}"
                    severity = "critical"
                    
            elif condition == AlertCondition.PRICE_BELOW:
                threshold = alert.params.get("threshold")
                if threshold and price < float(threshold):
                    triggered = True
                    message = f"价格下破阈值: **{price:.4f}** < {threshold}"
                    severity = "critical"
                    
            elif condition == AlertCondition.ATR_SPIKE:
                atr_percent = indicators.get("atr_percent", 0)
                threshold = alert.params.get("threshold", 5.0)  # 默认5%
                if atr_percent > threshold:
                    triggered = True
                    message = f"ATR 异常波动: **{atr_percent:.2f}%** (>{threshold}%)"
                    severity = "warning"
            
            if triggered:
                # 更新预警状态
                alert.last_triggered = datetime.now()
                alert.trigger_count += 1
                
                return AlertTrigger(
                    alert=alert,
                    triggered_at=datetime.now(),
                    price=price,
                    message=message,
                    indicators=indicators,
                    severity=severity
                )
                
        except Exception as e:
            # 记录错误但不中断其他检查
            print(f"检查预警 {alert.id} 时出错: {e}")
            
        return None
    
    async def check_all_alerts(self) -> List[AlertTrigger]:
        """
        检查所有预警
        
        Returns:
            List[AlertTrigger]: 触发的预警列表
        """
        triggered = []
        
        # 按交易对分组，避免重复获取数据
        alerts_by_symbol: Dict[str, List[Alert]] = {}
        for alert in self.alerts.values():
            if not alert.is_active or alert.is_in_cooldown():
                continue
            if alert.symbol not in alerts_by_symbol:
                alerts_by_symbol[alert.symbol] = []
            alerts_by_symbol[alert.symbol].append(alert)
        
        # 并发检查所有预警
        tasks = []
        for symbol, alerts in alerts_by_symbol.items():
            for alert in alerts:
                tasks.append(self.check_alert(alert))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, AlertTrigger):
                triggered.append(result)
                # 执行回调
                for callback in self.on_trigger_callbacks:
                    try:
                        callback(result)
                    except Exception as e:
                        print(f"回调执行出错: {e}")
        
        return triggered
    
    def create_alert_embed(self, trigger: AlertTrigger) -> discord.Embed:
        """
        创建 Discord Embed 格式的预警消息
        
        Args:
            trigger: 触发信息
            
        Returns:
            discord.Embed: 格式化的嵌入消息
        """
        alert = trigger.alert
        indicators = trigger.indicators
        
        # 根据严重程度设置颜色
        color_map = {
            "info": discord.Color.blue(),
            "warning": discord.Color.orange(),
            "critical": discord.Color.red()
        }
        color = color_map.get(trigger.severity, discord.Color.default())
        
        # 条件显示名称
        condition_display = {
            AlertCondition.RSI_OVERSOLD: "📉 RSI 超卖",
            AlertCondition.RSI_OVERBOUGHT: "📈 RSI 超买",
            AlertCondition.MACD_GOLDEN_CROSS: "🟢 MACD 金叉",
            AlertCondition.MACD_DEAD_CROSS: "🔴 MACD 死叉",
            AlertCondition.BB_UPPER_TOUCH: "⬆️ 布林带触及上轨",
            AlertCondition.BB_LOWER_TOUCH: "⬇️ 布林带触及下轨",
            AlertCondition.PRICE_ABOVE: "🚀 价格上破",
            AlertCondition.PRICE_BELOW: "🔻 价格下破",
            AlertCondition.ATR_SPIKE: "⚠️ 波动率异常",
        }
        
        title = condition_display.get(alert.condition, alert.condition.value)
        
        embed = discord.Embed(
            title=f"🚨 {title}",
            description=trigger.message,
            color=color,
            timestamp=trigger.triggered_at
        )
        
        # 基础信息
        embed.add_field(
            name="💰 当前价格",
            value=f"**{trigger.price:.4f} USDT**",
            inline=True
        )
        
        embed.add_field(
            name="📊 交易对",
            value=alert.symbol,
            inline=True
        )
        
        embed.add_field(
            name="🔔 预警ID",
            value=f"`{alert.id[:20]}...`" if len(alert.id) > 20 else f"`{alert.id}`",
            inline=True
        )
        
        # 技术指标
        rsi = indicators.get("rsi")
        if rsi:
            rsi_emoji = "🔴" if rsi > 70 else "🟢" if rsi < 30 else "⚪"
            embed.add_field(
                name="📈 RSI(14)",
                value=f"{rsi_emoji} {rsi:.2f}",
                inline=True
            )
        
        macd = indicators.get("macd", {})
        if macd.get("histogram") is not None:
            macd_emoji = "🟢" if macd["histogram"] > 0 else "🔴"
            embed.add_field(
                name="📊 MACD",
                value=f"{macd_emoji} {macd['histogram']:+.4f}",
                inline=True
            )
        
        bb = indicators.get("bollinger", {})
        if bb.get("upper"):
            bb_width = ((bb["upper"] - bb["lower"]) / trigger.price * 100) if trigger.price else 0
            embed.add_field(
                name="📏 布林带宽度",
                value=f"{bb_width:.2f}%",
                inline=True
            )
        
        # ATR
        atr = indicators.get("atr")
        atr_percent = indicators.get("atr_percent")
        if atr and atr_percent:
            embed.add_field(
                name="📐 ATR(14)",
                value=f"{atr:.4f} ({atr_percent:.2f}%)",
                inline=True
            )
        
        # 建议操作
        suggestion = self._generate_suggestion(alert.condition, indicators)
        embed.add_field(
            name="💡 建议操作",
            value=suggestion,
            inline=False
        )
        
        # 页脚
        embed.set_footer(
            text=f"触发次数: {alert.trigger_count} | 冷却: {alert.cooldown_minutes}分钟",
            icon_url="https://cdn.discordapp.com/embed/avatars/0.png"
        )
        
        return embed
    
    def _generate_suggestion(self, condition: AlertCondition, indicators: Dict) -> str:
        """生成建议操作文本"""
        suggestions = {
            AlertCondition.RSI_OVERSOLD: "📥 考虑逢低做多，设置严格止损",
            AlertCondition.RSI_OVERBOUGHT: "📤 考虑逢高做空或获利了结",
            AlertCondition.MACD_GOLDEN_CROSS: "📈 多头信号，可关注回调入场机会",
            AlertCondition.MACD_DEAD_CROSS: "📉 空头信号，关注反弹做空机会",
            AlertCondition.BB_UPPER_TOUCH: "⬆️ 价格偏离过大，警惕回调风险",
            AlertCondition.BB_LOWER_TOUCH: "⬇️ 价格偏离过大，关注反弹机会",
            AlertCondition.PRICE_ABOVE: "🚨 价格突破关键阻力位，顺势操作",
            AlertCondition.PRICE_BELOW: "🚨 价格跌破关键支撑位，顺势操作",
            AlertCondition.ATR_SPIKE: "⚠️ 波动率激增，建议减仓或观望",
        }
        
        base_suggestion = suggestions.get(condition, "请结合其他指标综合判断")
        
        # 添加 RSI 具体建议
        rsi = indicators.get("rsi")
        if rsi:
            if rsi < 20:
                base_suggestion += "\n⚠️ RSI 极度超卖，可能出现技术性反弹"
            elif rsi > 80:
                base_suggestion += "\n⚠️ RSI 极度超买，回调风险较高"
        
        return base_suggestion
    
    async def send_alert(self, trigger: AlertTrigger):
        """发送预警消息到 Discord"""
        if not self.bot:
            print("Bot 未设置，无法发送预警")
            return
        
        try:
            channel = self.bot.get_channel(trigger.alert.channel_id)
            if not channel:
                # 尝试通过 fetch 获取
                try:
                    channel = await self.bot.fetch_channel(trigger.alert.channel_id)
                except:
                    print(f"无法获取频道: {trigger.alert.channel_id}")
                    return
            
            embed = self.create_alert_embed(trigger)
            await channel.send(embed=embed)
            
        except Exception as e:
            print(f"发送预警失败: {e}")
    
    # ============ 持久化（可选）============
    
    def save_to_file(self, filepath: str = "alerts.json"):
        """保存预警到文件"""
        data = {alert_id: alert.to_dict() for alert_id, alert in self.alerts.items()}
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load_from_file(self, filepath: str = "alerts.json"):
        """从文件加载预警"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            for alert_id, alert_data in data.items():
                self.alerts[alert_id] = Alert.from_dict(alert_data)
        except FileNotFoundError:
            pass  # 文件不存在，忽略
        except Exception as e:
            print(f"加载预警文件失败: {e}")


# 全局预警服务实例
alert_service = AlertService()


# ============ Discord 任务循环 ============

@tasks.loop(minutes=5)
async def alert_monitor_task():
    """
    预警监控后台任务
    每5分钟执行一次检查
    """
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 执行预警监控检查...")
    
    triggered = await alert_service.check_all_alerts()
    
    if triggered:
        print(f"  触发 {len(triggered)} 条预警")
        for trigger in triggered:
            await alert_service.send_alert(trigger)
    else:
        print(f"  未触发任何预警")


@alert_monitor_task.before_loop
async def before_alert_monitor():
    """任务启动前等待 Bot 就绪"""
    print("预警监控任务准备启动...")
    # 等待一小段时间确保 Bot 完全启动
    await asyncio.sleep(5)
