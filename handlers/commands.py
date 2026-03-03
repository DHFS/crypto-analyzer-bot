"""Discord Bot 命令处理器 - 升级版本

新增功能：
- 异步数据获取
- 多时间周期分析
- 资金面数据展示
- 预警管理命令
- Model Arena (多模型竞技场)
- 交易历史与回测 Dashboard
"""
import asyncio
from typing import Optional
import discord
from discord import app_commands
import io
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # 非交互式后端

from config import config
from services import BinanceService, IndicatorService, AIAnalyzer, MacroService
from services.alert import alert_service, AlertCondition
from services.database import get_database_service
from services.tracker import get_trade_tracker


# 服务实例（模块级别只实例化一次）
binance_service = BinanceService()
indicator_service = IndicatorService()
ai_analyzer = AIAnalyzer()
macro_service = MacroService()
db_service = get_database_service()
trade_tracker = get_trade_tracker(binance_service, db_service)

# 模型选项
MODEL_CHOICES = [
    app_commands.Choice(name="🌙 Kimi 2.5 (默认)", value="kimi"),
    app_commands.Choice(name="🔮 Gemini Pro", value="gemini"),
    app_commands.Choice(name="🤖 GPT-4", value="gpt"),
    app_commands.Choice(name="🧠 Claude 3", value="claude"),
]


def setup_commands(bot: discord.Client, tree: app_commands.CommandTree):
    """注册所有斜杠命令"""

    # ============ /analyze 命令 (升级版 - 支持 Model Arena) ============
    @tree.command(name="analyze", description="AI综合分析交易对（多周期+资金面+宏观）")
    @app_commands.describe(
        symbol="交易对，如 ETHUSDT",
        timeframe="时间周期: 1m, 5m, 15m, 30m, 1h, 4h, 1d",
        model="选择AI模型 (可选，默认使用配置)"
    )
    @app_commands.choices(model=MODEL_CHOICES)
    async def analyze(
        interaction: discord.Interaction, 
        symbol: str, 
        timeframe: str,
        model: Optional[app_commands.Choice[str]] = None
    ):
        # 立即 defer 响应，避免 Discord 3秒超时
        await interaction.response.defer(thinking=True)
        
        symbol = symbol.upper().replace("/", "")
        timeframe = timeframe.lower()

        if timeframe not in config.VALID_TIMEFRAMES:
            await interaction.followup.send(
                f"❌ 不支持的周期: {timeframe}\n支持的周期: {', '.join(config.VALID_TIMEFRAMES)}"
            )
            return

        try:
            # 如果指定了模型，创建临时 AIAnalyzer 实例
            analyzer = ai_analyzer
            model_name = config.DEFAULT_AI_MODEL
            if model:
                model_name = model.value
                if model.value != config.DEFAULT_AI_MODEL:
                    analyzer = AIAnalyzer(model=model.value)

            # 获取完整市场数据（多周期K线 + 资金面数据）
            full_data = await binance_service.get_full_market_data(symbol, timeframe)
            
            # 计算多周期指标
            multi_indicators = indicator_service.calculate_multi_timeframe(full_data)
            
            # 获取宏观数据
            macro_data = await macro_service.get_macro_summary()
            
            # AI 分析 (返回 dict 包含 text 和 trade_data)
            result = await analyzer.analyze(
                symbol=symbol,
                primary_timeframe=timeframe,
                multi_timeframe_indicators=multi_indicators,
                full_market_data=full_data,
                macro_data=macro_data,
            )
            
            analysis_text = result["text"]
            trade_data = result.get("trade_data")
            model_used = result.get("model_used", model_name)

            # 如果 AI 建议 GO 且有有效交易数据，存入数据库
            if trade_data and trade_data.get("signal") == "GO":
                try:
                    trade_id = await db_service.create_trade(
                        symbol=symbol,
                        timeframe=timeframe,
                        direction=trade_data.get("direction", "LONG"),
                        leverage=trade_data.get("leverage_suggested", 1),
                        entry_price=trade_data.get("entry", 0),
                        tp_price=trade_data.get("tp", 0),
                        sl_price=trade_data.get("sl", 0),
                        ai_model=model_used,
                        ai_raw_response=analysis_text[:2000]  # 限制长度
                    )
                    # 在分析文本后附加记录信息
                    analysis_text += f"\n\n📊 **[Model Arena]** 交易建议已记录 (ID: #{trade_id}, 模型: {model_used})"
                except Exception as e:
                    print(f"⚠️ 记录交易失败: {e}")

            # Discord 消息限制 2000 字符，需要分段发送
            if len(analysis_text) <= 2000:
                await interaction.followup.send(analysis_text)
            else:
                chunks = [analysis_text[i:i+1990] for i in range(0, len(analysis_text), 1990)]
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await interaction.followup.send(chunk)
                    else:
                        await interaction.channel.send(chunk)

        except Exception as e:
            await interaction.followup.send(f"❌ 分析失败: {str(e)}")

    # ============ /indicators 命令 (升级版) ============
    @tree.command(name="indicators", description="查看技术指标数据（支持多周期共振分析）")
    @app_commands.describe(
        symbol="交易对，如 ETHUSDT",
        timeframe="时间周期: 1m, 5m, 15m, 30m, 1h, 4h, 1d"
    )
    async def indicators(interaction: discord.Interaction, symbol: str, timeframe: str):
        # 立即 defer 响应
        await interaction.response.defer(thinking=True)
        
        symbol = symbol.upper().replace("/", "")
        timeframe = timeframe.lower()

        if timeframe not in config.VALID_TIMEFRAMES:
            await interaction.followup.send(
                f"❌ 不支持的周期: {timeframe}\n支持的周期: {', '.join(config.VALID_TIMEFRAMES)}"
            )
            return

        try:
            # 获取多周期数据
            multi_tf_data = await binance_service.get_multi_timeframe_data(symbol, timeframe)
            
            # 计算多周期指标
            multi_indicators = indicator_service.calculate_multi_timeframe(multi_tf_data)
            
            # 格式化输出
            summary = indicator_service.format_multi_timeframe_summary(multi_indicators)
            
            await interaction.followup.send(f"```\n{summary}\n```")

        except Exception as e:
            await interaction.followup.send(f"❌ 获取指标失败: {str(e)}")

    # ============ /funding 命令 (新增) ============
    @tree.command(name="funding", description="查看合约资金面数据（资金费率、OI、多空比）")
    @app_commands.describe(symbol="交易对，如 ETHUSDT")
    async def funding(interaction: discord.Interaction, symbol: str):
        """查看资金面数据"""
        # 立即 defer 响应
        await interaction.response.defer(thinking=True)
        
        symbol = symbol.upper().replace("/", "")
        
        try:
            # 并发获取资金面数据
            funding_task = binance_service.get_funding_rate(symbol)
            oi_task = binance_service.get_open_interest(symbol)
            ratio_task = binance_service.get_long_short_ratio(symbol, period="15m")
            ticker_task = binance_service.get_ticker(symbol)
            
            funding_data, oi_data, ratio_data, ticker = await asyncio.gather(
                funding_task, oi_task, ratio_task, ticker_task,
                return_exceptions=True
            )
            
            # 检查异常
            for result in [funding_data, oi_data, ratio_data, ticker]:
                if isinstance(result, Exception):
                    raise result
            
            # 格式化输出
            embed = discord.Embed(
                title=f"📊 {symbol} 合约资金面分析",
                description="衍生品市场数据（资金费率、未平仓量、多空比）",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            # 资金费率
            fr = funding_data["funding_rate"]
            fr_emoji = "🟢" if fr > 0.01 else "🔴" if fr < -0.01 else "⚪"
            fr_status = "多头付费" if fr > 0 else "空头付费" if fr < 0 else "平衡"
            
            embed.add_field(
                name=f"💰 资金费率 {fr_emoji}",
                value=f"**{fr:+.4f}%**\n状态: {fr_status}\n下次结算: {funding_data['next_funding_time'].strftime('%H:%M')}",
                inline=True
            )
            
            # 未平仓量
            oi_usdt = oi_data["open_interest_usdt"] / 1_000_000  # 转换为百万
            embed.add_field(
                name="📦 未平仓量 (OI)",
                value=f"**{oi_usdt:.2f}M USDT**\n{oi_data['open_interest']:,.0f} 张合约",
                inline=True
            )
            
            # 多空比
            ls_ratio = ratio_data["long_short_ratio"]
            ls_emoji = "🐂" if ls_ratio > 1 else "🐻"
            dominant = "多头占优" if ls_ratio > 1 else "空头占优"
            
            embed.add_field(
                name=f"⚖️ 多空比 {ls_emoji}",
                value=f"**{ls_ratio:.2f}**\n{dominant}\n多:{ratio_data['long_account']:.1f}% 空:{ratio_data['short_account']:.1f}%",
                inline=True
            )
            
            # 当前价格
            embed.add_field(
                name="💵 当前价格",
                value=f"**{ticker['price']:.4f} USDT**\n24h涨跌: {ticker['price_change_percent']:+.2f}%",
                inline=False
            )
            
            # 分析建议
            analysis = []
            if abs(fr) > 0.05:
                analysis.append(f"⚠️ 资金费率过高({fr:+.4f}%)，注意反转风险")
            if ls_ratio > 2 or ls_ratio < 0.5:
                analysis.append(f"⚠️ 多空比失衡({ls_ratio:.2f})，散户情绪极端")
            if oi_usdt > 1000:
                analysis.append(f"📊 OI 较高({oi_usdt:.0f}M)，市场参与度高")
            
            if analysis:
                embed.add_field(
                    name="💡 分析提示",
                    value="\n".join(analysis),
                    inline=False
                )
            
            embed.set_footer(text="数据来自 Binance U本位合约 | 每5分钟更新")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 获取资金面数据失败: {str(e)}")

    # ============ /sentiment 命令 (新增) ============
    @tree.command(name="sentiment", description="查看市场情绪（恐慌贪婪指数）")
    async def sentiment(interaction: discord.Interaction):
        """查看宏观情绪指标"""
        await interaction.response.defer(thinking=True)
        
        try:
            fg_summary = await macro_service.get_fear_greed_summary()
            current = fg_summary["current"]
            
            # 创建颜色
            color_map = {
                "Extreme Fear": discord.Color.red(),
                "Fear": discord.Color.orange(),
                "Neutral": discord.Color.gold(),
                "Greed": discord.Color.green(),
                "Extreme Greed": discord.Color.dark_green()
            }
            
            embed = discord.Embed(
                title=f"{current.emoji} 加密货币市场情绪",
                description=f"恐慌贪婪指数: **{current.value}** - {current.classification_cn}",
                color=color_map.get(current.classification, discord.Color.default()),
                timestamp=discord.utils.utcnow()
            )
            
            # 指数值可视化（进度条）
            progress = int(current.value / 100 * 20)
            bar = "█" * progress + "░" * (20 - progress)
            embed.add_field(
                name="指数可视化",
                value=f"```\n极度恐慌 |{bar}| 极度贪婪\n         {current.value:>3}/100\n```",
                inline=False
            )
            
            # 趋势
            trend_emoji = {"rising": "📈", "falling": "📉", "stable": "➡️", "unknown": "❓"}
            embed.add_field(
                name="趋势",
                value=f"{trend_emoji.get(fg_summary['trend'], '❓')} {fg_summary['trend_cn']}",
                inline=True
            )
            
            # 更新时间
            embed.add_field(
                name="更新时间",
                value=current.timestamp.strftime("%Y-%m-%d %H:%M"),
                inline=True
            )
            
            # 分析
            embed.add_field(
                name="分析",
                value=fg_summary["analysis"],
                inline=False
            )
            
            # 近7天历史
            history_text = ""
            for fg in fg_summary["history"][:7]:
                history_text += f"{fg.timestamp.strftime('%m-%d')}: {fg.value:>3} {fg.emoji}\n"
            
            embed.add_field(
                name="近7天历史",
                value=f"```\n{history_text}\n```",
                inline=False
            )
            
            embed.set_footer(text="数据来源: Alternative.me | 每日更新")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 获取情绪数据失败: {str(e)}")

    # ============ /price 命令 ============
    @tree.command(name="price", description="查看当前价格")
    @app_commands.describe(symbol="交易对，如 ETHUSDT")
    async def price(interaction: discord.Interaction, symbol: str):
        symbol = symbol.upper().replace("/", "")

        try:
            ticker = await binance_service.get_ticker(symbol)
            price_text = (
                f"💰 **{ticker['symbol']}** 实时行情\n\n"
                f"当前价格: `{ticker['price']:.4f}`\n"
                f"24h涨跌: `{ticker['price_change']:+.4f}` ({ticker['price_change_percent']:+.2f}%)\n"
                f"24h最高: `{ticker['high_24h']:.4f}`\n"
                f"24h最低: `{ticker['low_24h']:.4f}`\n"
                f"24h成交量: `{ticker['volume_24h']:,.2f}`"
            )
            await interaction.response.send_message(price_text)

        except Exception as e:
            await interaction.response.send_message(f"❌ 获取价格失败: {str(e)}", ephemeral=True)

    # ============ 预警管理命令 ============
    
    @tree.command(name="alert_add", description="添加价格/指标预警")
    @app_commands.describe(
        symbol="交易对，如 ETHUSDT",
        condition="预警条件",
        threshold="价格阈值（仅price_above/below条件需要）"
    )
    @app_commands.choices(condition=[
        app_commands.Choice(name="📉 RSI 超卖 (<30)", value="rsi_oversold"),
        app_commands.Choice(name="📈 RSI 超买 (>70)", value="rsi_overbought"),
        app_commands.Choice(name="🟢 MACD 金叉", value="macd_golden"),
        app_commands.Choice(name="🔴 MACD 死叉", value="macd_dead"),
        app_commands.Choice(name="⬆️ 触及布林带上轨", value="bb_upper"),
        app_commands.Choice(name="⬇️ 触及布林带下轨", value="bb_lower"),
        app_commands.Choice(name="🚀 价格上破", value="price_above"),
        app_commands.Choice(name="🔻 价格下破", value="price_below"),
    ])
    async def alert_add(
        interaction: discord.Interaction, 
        symbol: str, 
        condition: app_commands.Choice[str],
        threshold: Optional[str] = None
    ):
        """添加预警规则"""
        symbol = symbol.upper().replace("/", "")
        
        # 验证价格阈值
        params = {}
        if condition.value in ["price_above", "price_below"]:
            if not threshold:
                await interaction.response.send_message(
                    "❌ 价格预警需要提供 threshold 参数（目标价格）",
                    ephemeral=True
                )
                return
            try:
                params["threshold"] = float(threshold)
            except ValueError:
                await interaction.response.send_message(
                    "❌ threshold 必须是有效的数字",
                    ephemeral=True
                )
                return
        
        try:
            alert = alert_service.create_alert(
                user_id=interaction.user.id,
                channel_id=interaction.channel_id,
                symbol=symbol,
                condition_str=condition.value,
                params=params
            )
            
            # 格式化确认信息
            condition_display = {
                "rsi_oversold": "📉 RSI 超卖 (<30)",
                "rsi_overbought": "📈 RSI 超买 (>70)",
                "macd_golden": "🟢 MACD 金叉",
                "macd_dead": "🔴 MACD 死叉",
                "bb_upper": "⬆️ 触及布林带上轨",
                "bb_lower": "⬇️ 触及布林带下轨",
                "price_above": f"🚀 价格上破 {threshold}",
                "price_below": f"🔻 价格下破 {threshold}",
            }
            
            embed = discord.Embed(
                title="✅ 预警添加成功",
                color=discord.Color.green()
            )
            embed.add_field(name="交易对", value=alert.symbol, inline=True)
            embed.add_field(name="条件", value=condition_display.get(condition.value, condition.value), inline=True)
            embed.add_field(name="预警ID", value=f"`{alert.id[:16]}...`", inline=True)
            embed.add_field(
                name="说明", 
                value=f"当条件触发时，我会在这个频道提醒你\n冷却时间: {alert.cooldown_minutes}分钟",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed)
            
        except ValueError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 添加预警失败: {e}", ephemeral=True)

    @tree.command(name="alert_list", description="查看你的所有预警")
    async def alert_list(interaction: discord.Interaction):
        """列出用户的所有预警"""
        user_alerts = alert_service.get_user_alerts(interaction.user.id)
        
        if not user_alerts:
            await interaction.response.send_message(
                "📭 你当前没有设置任何预警\n使用 `/alert_add` 添加预警",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"🔔 你的预警列表 ({len(user_alerts)}个)",
            color=discord.Color.blue()
        )
        
        for alert in user_alerts[:10]:  # 最多显示10个
            status = "🟢" if alert.is_active else "🔴"
            
            condition_display = {
                AlertCondition.RSI_OVERSOLD: "RSI超卖",
                AlertCondition.RSI_OVERBOUGHT: "RSI超买",
                AlertCondition.MACD_GOLDEN_CROSS: "MACD金叉",
                AlertCondition.MACD_DEAD_CROSS: "MACD死叉",
                AlertCondition.BB_UPPER_TOUCH: "触及上轨",
                AlertCondition.BB_LOWER_TOUCH: "触及下轨",
                AlertCondition.PRICE_ABOVE: f"价格上破{alert.params.get('threshold', '')}",
                AlertCondition.PRICE_BELOW: f"价格下破{alert.params.get('threshold', '')}",
            }.get(alert.condition, alert.condition.value)
            
            # 冷却状态
            cooldown_info = ""
            if alert.is_in_cooldown():
                remaining = alert.get_cooldown_remaining()
                cooldown_info = f" (冷却中: {remaining}分)"
            
            trigger_info = f"触发{alert.trigger_count}次" if alert.trigger_count > 0 else "未触发"
            
            embed.add_field(
                name=f"{status} {alert.symbol} - {condition_display}",
                value=f"ID: `{alert.id[:12]}...` | {trigger_info}{cooldown_info}",
                inline=False
            )
        
        if len(user_alerts) > 10:
            embed.set_footer(text=f"还有 {len(user_alerts) - 10} 个预警未显示")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(name="alert_remove", description="删除指定的预警")
    @app_commands.describe(alert_id="要删除的预警ID（从 /alert_list 获取）")
    async def alert_remove(interaction: discord.Interaction, alert_id: str):
        """删除预警"""
        # 先查找用户拥有的匹配预警
        user_alerts = alert_service.get_user_alerts(interaction.user.id)
        target_alert = None
        
        for alert in user_alerts:
            if alert.id.startswith(alert_id) or alert.id == alert_id:
                target_alert = alert
                break
        
        if not target_alert:
            await interaction.response.send_message(
                "❌ 未找到匹配的预警，请检查ID是否正确\n提示: 可以使用 `/alert_list` 查看所有预警ID",
                ephemeral=True
            )
            return
        
        # 删除预警
        if alert_service.remove_alert(target_alert.id):
            await interaction.response.send_message(
                f"✅ 预警已删除\n交易对: {target_alert.symbol}\n条件: {target_alert.condition.value}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("❌ 删除失败", ephemeral=True)

    @tree.command(name="alert_clear", description="删除所有预警")
    async def alert_clear(interaction: discord.Interaction):
        """清空用户的所有预警"""
        user_alerts = alert_service.get_user_alerts(interaction.user.id)
        count = 0
        
        for alert in user_alerts:
            if alert_service.remove_alert(alert.id):
                count += 1
        
        await interaction.response.send_message(
            f"🗑️ 已删除 {count} 个预警",
            ephemeral=True
        )

    # ============ /history 命令 (Model Arena - 交易历史) ============
    @tree.command(name="history", description="查看交易历史 (Model Arena)")
    @app_commands.describe(
        symbol="交易对过滤 (可选)",
        limit="显示数量 (默认10，最大20)"
    )
    async def history(
        interaction: discord.Interaction,
        symbol: Optional[str] = None,
        limit: Optional[int] = 10
    ):
        """查看最近的交易历史"""
        await interaction.response.defer(thinking=True)
        
        if symbol:
            symbol = symbol.upper().replace("/", "")
        
        limit = min(max(limit or 10, 1), 20)  # 限制 1-20
        
        try:
            # 获取历史记录
            trades = await db_service.get_trade_history(
                symbol=symbol,
                limit=limit
            )
            
            if not trades:
                await interaction.followup.send(
                    "📭 暂无交易记录\n使用 `/analyze` 命令生成交易建议。"
                )
                return
            
            # 创建 Embed
            embed = discord.Embed(
                title=f"📜 交易历史 {f'({symbol})' if symbol else ''}",
                description=f"最近 {len(trades)} 笔交易记录",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            for trade in trades:
                # 模型标识
                model_emoji = {
                    "kimi-2.5": "🌙",
                    "kimi": "🌙",
                    "gemini-pro": "🔮",
                    "gemini": "🔮",
                    "gpt-4": "🤖",
                    "gpt": "🤖",
                    "claude-3": "🧠",
                    "claude": "🧠",
                }.get(trade.ai_model.lower(), "🤖")
                
                # 状态标识
                status_emoji = {
                    "OPEN": "🟡",
                    "CLOSED_TP": "🟢",
                    "CLOSED_SL": "🔴",
                    "EXPIRED": "⚪",
                }.get(trade.status, "⚪")
                
                # 方向标识
                direction_emoji = "📈" if trade.direction == "LONG" else "📉"
                
                # PnL 显示
                pnl_text = "进行中"
                if trade.pnl_percentage is not None:
                    pnl_emoji = "🟢" if trade.pnl_percentage > 0 else "🔴"
                    pnl_text = f"{pnl_emoji} {trade.pnl_percentage:+.2f}%"
                
                # 结算原因
                close_info = ""
                if trade.close_reason:
                    close_info = f" | {trade.close_reason}"
                
                field_name = f"{status_emoji} [{model_emoji} {trade.ai_model.upper()}] {direction_emoji} {trade.direction} {trade.symbol}"
                field_value = f"进: {trade.entry_price:.4f} → 止: {trade.sl_price:.4f} / 盈: {trade.tp_price:.4f} | {pnl_text}{close_info}"
                
                embed.add_field(name=field_name, value=field_value, inline=False)
            
            embed.set_footer(text="🟡 进行中 | 🟢 止盈 | 🔴 止损 | ⚪ 过期")
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 获取历史记录失败: {str(e)}")

    # ============ /dashboard 命令 (Model Arena - 绩效面板) ============
    @tree.command(name="dashboard", description="查看 Model Arena 绩效面板")
    @app_commands.describe(
        symbol="交易对过滤 (可选，默认全部)",
        days="统计天数 (默认30天)"
    )
    async def dashboard(
        interaction: discord.Interaction,
        symbol: Optional[str] = None,
        days: Optional[int] = 30
    ):
        """查看 Model Arena 绩效统计"""
        await interaction.response.defer(thinking=True)
        
        if symbol:
            symbol = symbol.upper().replace("/", "")
        
        try:
            # 获取全局统计
            global_stats = await db_service.get_global_stats(symbol=symbol, days=days)
            
            # 获取各模型统计
            model_stats = await db_service.get_model_performance_stats(symbol=symbol, days=days)
            
            # 创建主 Embed
            embed = discord.Embed(
                title=f"📊 Model Arena 绩效面板 {f'({symbol})' if symbol else '(全部币种)'}",
                description=f"统计周期: 最近 {days} 天",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )
            
            # 全局统计
            if global_stats.total_trades > 0:
                win_rate_emoji = "🟢" if global_stats.win_rate >= 60 else "🟡" if global_stats.win_rate >= 40 else "🔴"
                pnl_emoji = "🟢" if global_stats.total_pnl > 0 else "🔴"
                
                embed.add_field(
                    name="📈 全局统计",
                    value=(
                        f"总开单: {global_stats.total_trades} 笔\n"
                        f"已结算: {global_stats.closed_trades} 笔\n"
                        f"{win_rate_emoji} 胜率: {global_stats.win_rate:.1f}%\n"
                        f"{pnl_emoji} 累计盈亏: {global_stats.total_pnl:+.2f}%\n"
                        f"平均盈亏: {global_stats.avg_pnl:+.2f}%"
                    ),
                    inline=False
                )
            else:
                embed.add_field(
                    name="📈 全局统计",
                    value="暂无交易数据\n使用 `/analyze` 生成交易建议",
                    inline=False
                )
            
            # 各模型统计
            if model_stats:
                embed.add_field(name="\n🏆 模型战报", value="各模型独立表现", inline=False)
                
                for model_name, stats in sorted(model_stats.items(), key=lambda x: x[1].total_pnl, reverse=True):
                    model_emoji = {
                        "kimi-2.5": "🌙",
                        "kimi": "🌙",
                        "gemini-pro": "🔮",
                        "gemini": "🔮",
                        "gpt-4": "🤖",
                        "gpt": "🤖",
                        "claude-3": "🧠",
                        "claude": "🧠",
                    }.get(model_name.lower(), "🤖")
                    
                    pnl_emoji = "🟢" if stats.total_pnl > 0 else "🔴" if stats.total_pnl < 0 else "⚪"
                    
                    field_name = f"{model_emoji} {model_name.upper()}"
                    field_value = (
                        f"开单: {stats.total_trades} | 胜: {stats.win_count} | 负: {stats.loss_count}\n"
                        f"胜率: {stats.win_rate:.1f}% | {pnl_emoji} 累计: {stats.total_pnl:+.2f}%\n"
                        f"平均盈: {stats.avg_win:+.2f}% | 平均亏: {stats.avg_loss:+.2f}%"
                    )
                    embed.add_field(name=field_name, value=field_value, inline=False)
            
            await interaction.followup.send(embed=embed)
            
            # 生成并发送资金曲线图
            if global_stats.closed_trades > 0:
                try:
                    curve_data = await db_service.get_equity_curve_data(symbol=symbol, days=days)
                    if len(curve_data) >= 2:
                        img_buffer = await generate_equity_chart(curve_data, symbol or "ALL", days)
                        file = discord.File(img_buffer, filename="equity_curve.png")
                        await interaction.followup.send("📈 累计盈亏曲线:", file=file)
                except Exception as e:
                    print(f"⚠️ 生成资金曲线失败: {e}")
            
        except Exception as e:
            await interaction.followup.send(f"❌ 获取绩效面板失败: {str(e)}")

    async def generate_equity_chart(curve_data, symbol: str, days: int) -> io.BytesIO:
        """生成资金曲线图"""
        # 准备数据
        timestamps = [d["timestamp"] for d in curve_data]
        pnl_values = [d["cumulative_pnl"] for d in curve_data]
        
        # 创建图表
        fig, ax = plt.subplots(figsize=(10, 5))
        
        # 绘制曲线
        color = 'green' if pnl_values[-1] >= 0 else 'red'
        ax.plot(range(len(timestamps)), pnl_values, color=color, linewidth=2)
        
        # 填充区域
        ax.fill_between(range(len(timestamps)), 0, pnl_values, alpha=0.3, color=color)
        
        # 添加零线
        ax.axhline(y=0, color='black', linestyle='--', linewidth=0.8)
        
        # 设置标签
        ax.set_xlabel('Trade Number', fontsize=10)
        ax.set_ylabel('Cumulative PnL (%)', fontsize=10)
        ax.set_title(f'Model Arena Equity Curve - {symbol} ({days}d)', fontsize=12, fontweight='bold')
        
        # 网格
        ax.grid(True, alpha=0.3)
        
        # 保存到内存
        buffer = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        plt.close(fig)
        
        return buffer

    # ============ /help 命令 (升级版) ============
    @tree.command(name="help", description="查看帮助信息")
    async def help_cmd(interaction: discord.Interaction):
        help_text = """
**📖 Crypto Analyzer Bot 使用帮助**

**市场分析命令:**
• `/analyze <交易对> <周期> [模型]` - AI综合分析（多周期+资金面+宏观）
• `/indicators <交易对> <周期>` - 查看技术指标（含共振分析）
• `/price <交易对>` - 查看当前价格
• `/funding <交易对>` - 查看合约资金面数据
• `/sentiment` - 查看市场情绪（恐慌贪婪指数）

**Model Arena (回测系统):**
• `/history [交易对] [数量]` - 查看交易历史记录
• `/dashboard [交易对] [天数]` - 查看模型绩效面板

**预警监控命令:**
• `/alert_add <交易对> <条件>` - 添加预警
  条件选项: RSI超卖/超买、MACD金叉/死叉、布林带触及、价格突破
• `/alert_list` - 查看你的所有预警
• `/alert_remove <预警ID>` - 删除指定预警
• `/alert_clear` - 清空所有预警

**示例:**
• `/analyze ETHUSDT 1h` - 用默认模型分析ETH
• `/analyze ETHUSDT 1h model:gemini` - 用Gemini分析并计入战绩
• `/dashboard` - 查看所有模型绩效
• `/dashboard BTCUSDT days:7` - 查看BTC近7天战绩
• `/alert_add ETHUSDT rsi_oversold` - RSI超卖预警

**支持的周期:** 1m, 5m, 15m, 30m, 1h, 4h, 1d
**AI模型:** 🌙Kimi | 🔮Gemini | 🤖GPT | 🧠Claude
        """
        await interaction.response.send_message(help_text.strip())
