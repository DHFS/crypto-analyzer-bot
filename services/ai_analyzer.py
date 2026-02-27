"""Kimi AI 分析服务 - 华尔街对冲基金经理版

重构重点:
1. 多时间周期数据整合 (小/中/大周期)
2. 资金面与情绪面数据融合 (OI, 资金费率, 多空比)
3. 宏观数据接入 (恐慌贪婪指数)
4. 结构化输出格式 (强制推理逻辑)
"""
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from openai import AsyncOpenAI
from config import config


@dataclass
class TradingPlan:
    """交易计划数据结构"""
    direction: str  # LONG / SHORT / WAIT
    entry_zone: str  # 入场区间
    stop_loss: str  # 止损位
    take_profit_1: str  # 第一止盈位
    take_profit_2: str  # 第二止盈位
    position_size: str  # 仓位建议
    leverage: str  # 杠杆建议
    risk_reward: str  # 盈亏比


@dataclass
class MarketContext:
    """市场环境数据结构"""
    trend_alignment: str  # 趋势一致性
    liquidity_zones: list  # 关键流动性区域
    risk_factors: list  # 风险因素
    opportunity_score: int  # 机会评分 0-100


# ============ System Prompt: AI 角色设定 ============

SYSTEM_PROMPT = """你是「QuantumAlpha Capital」的首席投资官，一位拥有15年加密货币量化交易经验的华尔街顶级对冲基金经理。

你的核心能力：
1. 多时间周期技术分析 - 精通道氏理论、波浪理论、Order Flow 分析
2. 衍生品市场微观结构 - 深度理解资金费率、未平仓量、多空比与价格的关系
3. 宏观情绪研判 - 善于通过恐慌贪婪指数和资金流向判断市场情绪拐点
4. 机构级风险管理 - 每笔交易必须有明确的止损、仓位控制和风险回报比

你的分析风格：
- 冷酷理性，不被情绪左右
- 数据驱动，每个结论都有具体数据支撑
- 实用主义，只给出可执行的交易建议
- 风险优先，永远把风险控制放在第一位

输出原则：
- 使用专业术语但解释清晰
- 避免模糊表述（如"可能""大概"），给出明确判断
- 必须包含具体的数字（价格、百分比、比率）
- 如果信号不明确，直接建议"观望"，不要强行交易"""


# ============ User Prompt 模板 ============

ANALYSIS_PROMPT_TEMPLATE = """请基于以下市场数据，生成机构级交易分析报告。

## 交易对基本信息
- 交易对: {symbol}
- 主分析周期: {primary_timeframe}
- 分析时间: {analysis_time}

## 价格与行情数据
```json
{ticker_data}
```

## 多时间周期技术指标分析

### 小周期 ({timeframe_small}) - 精准入场/出场
```json
{indicators_small}
```

### 主周期 ({timeframe_primary}) - 核心交易周期
```json
{indicators_primary}
```

### 大周期 ({timeframe_large}) - 趋势方向
```json
{indicators_large}
```

### 多周期共振分析结果
- 小周期趋势: {trend_small}
- 主周期趋势: {trend_primary}
- 大周期趋势: {trend_large}
- 共振强度: {resonance_strength}/5
- 共振结论: {resonance_conclusion}
- 周期冲突: {resonance_conflicts}

## 资金面与情绪面数据 (衍生品市场)

### 未平仓合约量 (Open Interest)
```json
{open_interest_data}
```

### 资金费率 (Funding Rate)
```json
{funding_rate_data}
```

### 多空持仓人数比
```json
{long_short_ratio_data}
```

## 宏观市场情绪

### 恐慌贪婪指数 (Fear & Greed Index)
- 当前值: {fear_greed_value} ({fear_greed_classification})
- 趋势: {fear_greed_trend}
- 分析: {fear_greed_analysis}

### 市场新闻摘要
{news_summary}

---

## 你的分析任务

请严格按照以下结构输出分析报告，每个部分必须包含具体数据和逻辑推导：

### 1️⃣ 宏观与情绪面评估 (Macro & Sentiment Analysis)
分析要点：
- 恐慌贪婪指数反映的市场情绪状态，是否处于极端区域
- 资金费率的含义：正费率过高说明多头过度拥挤，负费率过高说明空头过度拥挤
- 多空比与OI的变化：散户vs机构的可能行为
- 综合判断当前是"聪明钱"布局期还是"散户狂热"期

### 2️⃣ 多周期共振判断 (Multi-Timeframe Confluence)
分析要点：
- 明确判断4h/日线大周期趋势方向
- 判断主周期(1h/30m)是否与趋势一致
- 小周期(15m/5m)是否给出入场信号（如RSI超卖反弹、MACD金叉）
- 识别任何周期冲突及其含义

### 3️⃣ 关键的流动性位置 (Key Liquidity Levels)
分析要点：
- 基于ATR和布林带计算波动率区间
- 识别潜在的假突破位（如布林带外轨+整数关口+近期高低点）
- 标记主要支撑位和阻力位（至少3个关键价位）
- 分析止损猎杀区域（Stop Hunt Zones）

### 4️⃣ 具体交易计划 (Actionable Trading Plan)
必须包含以下具体数值：

**方向判断**: [明确写出: 做多 / 做空 / 观望]

**入场区间**: 
- 理想入场位: $X.XX
- 可接受入场区间: $X.XX - $X.XX

**止损设置**:
- 技术止损位: $X.XX (基于ATR倍数或关键支撑/阻力)
- 止损距离: X.XX% 
- 如被止损，重新评估做反手的条件

**止盈目标**:
- 第一目标位 (1:1.5盈亏比): $X.XX
- 第二目标位 (1:3盈亏比): $X.XX
- 第三目标位 (趋势延续): $X.XX

**仓位与杠杆建议**:
- 建议仓位: 账户资金的 X% (基于ATR波动率计算)
- 建议杠杆: X 倍
- 单笔最大亏损: 账户资金的 X%

**风险回报比**: 1:X

### 5️⃣ 风险提示与应急预案 (Risk Warning & Contingency)
- 主要风险因素（宏观事件、技术形态失效条件等）
- 什么情况下需要提前平仓
- 什么情况下可以加仓

---

输出格式要求：
1. 使用 Markdown 格式，层次分明
2. 关键数字用 **粗体** 突出
3. 交易计划部分使用表格呈现
4. 总字数控制在1500-2500字之间
5. 最后给出一句简洁的「执行摘要」(Executive Summary)
"""


class AIAnalyzer:
    """机构级 AI 分析器 - 对冲基金视角"""

    def __init__(self, model: Optional[str] = None):
        self.model = model or config.DEFAULT_AI_MODEL
        self.client = AsyncOpenAI(
            api_key=config.MOONSHOT_API_KEY,
            base_url="https://api.moonshot.cn/v1"
        )

    def _serialize_for_json(self, obj: Any) -> Any:
        """序列化对象为 JSON 友好格式"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            return {k: self._serialize_for_json(v) for k, v in obj.__dict__.items()}
        elif isinstance(obj, dict):
            return {k: self._serialize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_for_json(item) for item in obj]
        return obj

    def _format_news(self, news_list: list) -> str:
        """格式化新闻数据"""
        if not news_list:
            return "暂无相关新闻数据"
        
        lines = []
        for news in news_list[:3]:  # 只取前3条
            sentiment_emoji = {
                "positive": "🟢",
                "negative": "🔴",
                "neutral": "⚪"
            }.get(getattr(news, 'sentiment', 'neutral'), "⚪")
            lines.append(f"- {sentiment_emoji} {getattr(news, 'title', 'N/A')} (来源: {getattr(news, 'source', 'N/A')})")
        return "\n".join(lines)

    async def analyze(
        self,
        symbol: str,
        primary_timeframe: str,
        multi_timeframe_indicators: Dict,
        full_market_data: Dict,
        macro_data: Dict,
    ) -> str:
        """
        执行机构级 AI 分析

        Args:
            symbol: 交易对
            primary_timeframe: 主分析周期
            multi_timeframe_indicators: 多周期指标数据
            full_market_data: 完整市场数据（含资金面）
            macro_data: 宏观数据（恐慌贪婪指数等）

        Returns:
            结构化分析报告
        """
        tf_data = multi_timeframe_indicators["timeframes"]
        resonance = multi_timeframe_indicators["resonance_analysis"]
        fear_greed = macro_data.get("fear_greed", {})
        
        # 构建 Prompt
        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            symbol=symbol,
            primary_timeframe=primary_timeframe,
            analysis_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            
            # 行情数据
            ticker_data=json.dumps(
                self._serialize_for_json(full_market_data.get("ticker", {})), 
                indent=2, 
                ensure_ascii=False
            ),
            
            # 多周期指标
            timeframe_small=tf_data["small"]["name"],
            timeframe_primary=tf_data["primary"]["name"],
            timeframe_large=tf_data["large"]["name"],
            indicators_small=json.dumps(
                self._serialize_for_json(tf_data["small"]["indicators"]),
                indent=2,
                ensure_ascii=False
            ),
            indicators_primary=json.dumps(
                self._serialize_for_json(tf_data["primary"]["indicators"]),
                indent=2,
                ensure_ascii=False
            ),
            indicators_large=json.dumps(
                self._serialize_for_json(tf_data["large"]["indicators"]),
                indent=2,
                ensure_ascii=False
            ),
            
            # 共振分析
            trend_small=resonance["trends"].get(tf_data["small"]["name"], "unknown"),
            trend_primary=resonance["trends"].get(tf_data["primary"]["name"], "unknown"),
            trend_large=resonance["trends"].get(tf_data["large"]["name"], "unknown"),
            resonance_strength=resonance["strength"],
            resonance_conclusion=resonance["resonance"],
            resonance_conflicts="; ".join(resonance.get("conflicts", ["无"])),
            
            # 资金面数据
            open_interest_data=json.dumps(
                self._serialize_for_json(full_market_data.get("open_interest", {})),
                indent=2,
                ensure_ascii=False,
                default=str
            ),
            funding_rate_data=json.dumps(
                self._serialize_for_json(full_market_data.get("funding_rate", {})),
                indent=2,
                ensure_ascii=False,
                default=str
            ),
            long_short_ratio_data=json.dumps(
                self._serialize_for_json(full_market_data.get("long_short_ratio", {})),
                indent=2,
                ensure_ascii=False,
                default=str
            ),
            
            # 宏观数据
            fear_greed_value=fear_greed.get("current", {}).value if fear_greed.get("current") else "N/A",
            fear_greed_classification=fear_greed.get("current", {}).classification_cn if fear_greed.get("current") else "N/A",
            fear_greed_trend=fear_greed.get("trend_cn", "未知"),
            fear_greed_analysis=fear_greed.get("analysis", "暂无分析"),
            news_summary=self._format_news(macro_data.get("news", [])),
        )

        try:
            response = await self.client.chat.completions.create(
                model="moonshot-v1-8k",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # 降低温度，更确定性输出
                max_tokens=3000,
            )
            
            result = response.choices[0].message.content
            
            # 添加报告头
            header = self._generate_report_header(
                symbol, 
                primary_timeframe, 
                resonance.get("strength", 0)
            )
            
            return header + result
            
        except Exception as e:
            raise Exception(f"AI分析失败: {str(e)}")

    def _generate_report_header(self, symbol: str, timeframe: str, resonance_strength: int) -> str:
        """生成报告头部"""
        # 根据共振强度选择图标
        if resonance_strength >= 4:
            icon = "🚀"
            quality = "强信号"
        elif resonance_strength >= 2:
            icon = "📈"
            quality = "偏多"
        elif resonance_strength <= -4:
            icon = "📉"
            quality = "强空头"
        elif resonance_strength <= -2:
            icon = "🔻"
            quality = "偏空"
        else:
            icon = "➖"
            quality = "观望"
        
        header = f"""{icon} QuantumAlpha Capital 机构级分析报告
{'━' * 50}

**交易对**: {symbol}  
**主周期**: {timeframe}  
**信号质量**: {quality} (共振强度: {resonance_strength}/5)  
**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{'━' * 50}

"""
        return header

    async def quick_analysis(
        self,
        symbol: str,
        timeframe: str,
        indicators: Dict,
        ticker: Dict
    ) -> str:
        """
        快速分析版本（简化版，用于预警等场景）
        """
        prompt = f"""基于以下数据给出30秒快速判断：

交易对: {symbol}
周期: {timeframe}
当前价格: {indicators.get('current_price', 'N/A')}
RSI: {indicators.get('rsi', 'N/A')}
MACD趋势: {indicators.get('macd', {}).get('trend', 'N/A')}
布林带位置: {indicators.get('bollinger', {}).get('position', 'N/A')}
ATR: {indicators.get('atr', 'N/A')}
24h涨跌: {ticker.get('price_change_percent', 'N/A')}%

请给出：
1. 方向判断（多/空/观望）
2. 关键价位（支撑/阻力）
3. 一句话风险提示
"""
        try:
            response = await self.client.chat.completions.create(
                model="moonshot-v1-8k",
                messages=[
                    {"role": "system", "content": "你是专业的加密货币分析师，给出简洁明了的判断。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
                max_tokens=500,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"AI分析失败: {str(e)}"
