"""Kimi AI 分析服务 - 华尔街对冲基金经理版

重构重点:
1. 多时间周期数据整合 (小/中/大周期)
2. 资金面与情绪面数据融合 (OI, 资金费率, 多空比)
3. 宏观数据接入 (恐慌贪婪指数)
4. Python 硬风控数据整合 (ATR止损、爆仓价)
5. 结构化输出格式 (强制推理逻辑)
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


@dataclass
class UserIntent:
    """用户交易意图"""
    direction: str  # long / short / neutral
    leverage: int   # 计划使用的杠杆倍数
    risk_percent: float  # 愿意承担的风险比例


# ============ System Prompt: AI 角色设定 ============

SYSTEM_PROMPT = """你是「QuantumAlpha Capital」的首席投资官，一位拥有15年加密货币量化交易经验的华尔街顶级对冲基金经理。

你的核心能力：
1. 多时间周期技术分析 - 精通道氏理论、波浪理论、Order Flow 分析
2. 衍生品市场微观结构 - 深度理解资金费率、未平仓量、多空比与价格的关系
3. 宏观情绪研判 - 善于通过恐慌贪婪指数和资金流向判断市场情绪拐点
4. 机构级风险管理 - 每笔交易必须有明确的止损、仓位控制和风险回报比
5. 硬风控数据验证 - 必须基于 Python 计算的 ATR 止损价和爆仓价给出建议

你的分析风格：
- 冷酷理性，不被情绪左右
- 数据驱动，每个结论都有具体数据支撑
- 实用主义，只给出可执行的交易建议
- 风险优先，永远把风险控制放在第一位
- 尊重硬风控数据，Python 计算的爆仓价是红线

输出原则：
- 使用专业术语但解释清晰
- 避免模糊表述（如"可能""大概"），给出明确判断
- 必须包含具体的数字（价格、百分比、比率）
- 如果信号不明确，直接建议"观望"，不要强行交易
- 必须严格遵守强制输出结构

⚠️ 极其重要的要求 ⚠️
除了输出给用户看的 Markdown 文本分析外，你必须在回答的最后，单独附加一个严格格式化的 JSON 代码块（用 ```json 包裹），包含以下字段：
{
  "signal": "GO" | "NO-GO" | "CONDITIONAL",
  "direction": "LONG" | "SHORT" | "NEUTRAL",
  "entry": float,
  "tp": float,
  "sl": float,
  "leverage_suggested": int,
  "confidence": "high" | "medium" | "low",
  "reason": "一句话总结决策原因"
}
这个 JSON 将被程序自动解析用于回测统计，请务必确保格式正确且与正文分析一致！"""


# ============ User Prompt 模板 ============

ANALYSIS_PROMPT_TEMPLATE = """请基于以下市场数据，生成机构级交易分析报告。

## 用户交易意图
- 计划方向: {user_direction}
- 计划杠杆: {user_leverage}x
- 风险承受: 本金的 {user_risk_percent}%

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

## 硬风控数据 (Python 计算)

### ATR 推荐止损价位
```json
{risk_stop_loss_data}
```

### 预计爆仓价位
```json
{risk_liquidation_data}
```

### 风险参数计算
```json
{risk_params_data}
```

## 宏观市场情绪

### 恐慌贪婪指数 (Fear & Greed Index)
- 当前值: {fear_greed_value} ({fear_greed_classification})
- 趋势: {fear_greed_trend}
- 分析: {fear_greed_analysis}

### 市场新闻摘要
{news_summary}

---

## 强制输出结构要求

你必须严格按照以下结构输出分析报告，每个部分都必须包含，使用 markdown 格式：

### 1️⃣ 方向判断 (Direction)
基于多周期共振、资金面数据、用户意图，给出明确的方向判断：
- **判断结果**: [做多 / 做空 / 观望]
- **置信度**: [高/中/低]
- **核心依据**: [2-3句话说明为什么]
- **与用户意图一致性**: [一致/冲突/中性]

### 2️⃣ 关键点位计划 (Key Levels Plan)
必须基于技术指标和硬风控数据给出具体数字：

**进场区间**:
- 理想入场位: $X.XX (基于支撑/阻力/均线)
- 可接受入场区间: $X.XX - $X.XX
- 入场触发条件: [如"价格回踩EMA25且RSI>50"]

**止损位** (必须参考 Python 计算的 ATR 止损):
- 技术止损位: $X.XX
- ATR推荐止损: ${atr_stop_price} (距离 {atr_stop_distance}%)
- 最终止损位: $X.XX (说明为什么选这个)
- 止损触发后的反手条件: [如有]

**止盈位**:
- 第一目标位 (1:1.5盈亏比): $X.XX
- 第二目标位 (1:3盈亏比): $X.XX
- 第三目标位 (趋势延续): $X.XX
- 移动止盈策略: [如"破EMA20止盈一半"]

### 3️⃣ 风险数据评估 (Risk Assessment)
必须基于 Python 计算的硬风控数据：

**盈亏比 (RRR) 分析**:
- 入场价: $X.XX
- 止损价: $X.XX (风险 {risk_amount}$)
- 第一止盈: $X.XX (收益 {reward_1}$)
- 第二止盈: $X.XX (收益 {reward_2}$)
- **盈亏比 RRR**: 1:X (第一目标) / 1:Y (第二目标)
- RRR 评级: [优秀>=3 / 良好>=2 / 可接受>=1.5 / 差<1.5]

**爆仓风险评级**:
- 计划杠杆: {user_leverage}x
- 爆仓价格: ${liq_price} (距离 {liq_distance}%)
- Python计算的安全杠杆: {safe_leverage}x
- **爆仓风险评级**: [安全/中等/高危/极高危]
- 爆仓风险说明: [如"爆仓距离小于2倍止损距离，建议降杠杆"]

**仓位建议**:
- 建议仓位: 账户资金的 X%
- 单笔最大亏损: 账户资金的 X%
- 实际占用保证金: $XXX

### 4️⃣ 最终决策 (Final Decision)
必须是 GO / NO-GO / CONDITIONAL 之一：

**决策**: [GO / NO-GO / CONDITIONAL]

**决策依据**:
- 做多/做空条件是否满足: [是/否，说明]
- 风险收益比是否可接受: [是/否，说明]
- 爆仓风险是否在可控范围: [是/否，说明]

**执行条件** (如果是 CONDITIONAL):
- 什么条件下可以入场: [如"价格回调至$X.XX且RSI<50"]
- 什么条件下必须放弃: [如"跌破$X.XX则放弃"]

**执行摘要** (Executive Summary):
用一句话总结: [方向] [入场区间] [止损] [止盈] [杠杆] [决策]

---

输出格式要求：
1. 使用 Markdown 格式，层次分明
2. 关键数字用 **粗体** 突出
3. 交易计划部分使用表格呈现
4. 总字数控制在1500-2500字之间
5. 必须严格遵守上述 4 个部分的结构
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

    def _extract_trade_json(self, ai_response: str) -> Optional[Dict]:
        """
        从 AI 响应中提取结构化 JSON 数据
        
        Returns:
            Dict with signal, direction, entry, tp, sl, etc. or None if parsing fails
        """
        import re
        import json
        
        # 尝试提取 ```json 代码块
        json_pattern = r'```json\s*\n(.*?)\n```'
        match = re.search(json_pattern, ai_response, re.DOTALL)
        
        if match:
            json_str = match.group(1)
        else:
            # 尝试提取普通 ``` 代码块
            json_pattern = r'```\s*\n(.*?)\n```'
            match = re.search(json_pattern, ai_response, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                return None
        
        try:
            data = json.loads(json_str)
            
            # 验证必要字段
            required_fields = ["signal", "direction", "entry", "tp", "sl"]
            for field in required_fields:
                if field not in data:
                    print(f"⚠️ JSON 缺少必要字段: {field}")
                    return None
            
            # 标准化字段
            return {
                "signal": str(data.get("signal", "NO-GO")).upper(),
                "direction": str(data.get("direction", "NEUTRAL")).upper(),
                "entry": float(data.get("entry", 0)),
                "tp": float(data.get("tp", 0)),
                "sl": float(data.get("sl", 0)),
                "leverage_suggested": int(data.get("leverage_suggested", 1)),
                "confidence": str(data.get("confidence", "low")).lower(),
                "reason": str(data.get("reason", "")),
            }
        except (json.JSONDecodeError, ValueError) as e:
            print(f"⚠️ JSON 解析失败: {e}")
            return None

    def get_model_name(self) -> str:
        """获取当前模型名称标识"""
        model_mapping = {
            "kimi": "kimi-2.5",
            "gpt": "gpt-4",
            "gpt-4": "gpt-4",
            "gpt-3.5": "gpt-3.5",
            "claude": "claude-3",
            "gemini": "gemini-pro",
        }
        return model_mapping.get(self.model.lower(), self.model.lower())

    async def analyze(
        self,
        symbol: str,
        primary_timeframe: str,
        multi_timeframe_indicators: Dict,
        full_market_data: Dict,
        macro_data: Dict,
        risk_data: Dict,
        user_intent: Optional[UserIntent] = None,
    ) -> Dict[str, Any]:
        """
        执行机构级 AI 分析

        Args:
            symbol: 交易对
            primary_timeframe: 主分析周期
            multi_timeframe_indicators: 多周期指标数据
            full_market_data: 完整市场数据（含资金面）
            macro_data: 宏观数据（恐慌贪婪指数等）
            risk_data: 风控数据（ATR止损、爆仓价等）
            user_intent: 用户交易意图

        Returns:
            Dict with 'text' (分析报告文本) and 'trade_data' (结构化交易数据)
        """
        tf_data = multi_timeframe_indicators["timeframes"]
        resonance = multi_timeframe_indicators["resonance_analysis"]
        fear_greed = macro_data.get("fear_greed", {})
        
        # 用户意图默认值
        if user_intent is None:
            user_intent = UserIntent(direction="neutral", leverage=1, risk_percent=2.0)
        
        # 风控数据提取
        stop_loss_data = risk_data.get("stop_loss", {})
        liquidation_data = risk_data.get("liquidation", {})
        risk_params = risk_data.get("risk_params", {})
        
        # 构建 Prompt
        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            # 用户意图
            user_direction=user_intent.direction.upper(),
            user_leverage=user_intent.leverage,
            user_risk_percent=user_intent.risk_percent,
            
            # 基本信息
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
            
            # 硬风控数据
            risk_stop_loss_data=json.dumps(
                self._serialize_for_json(stop_loss_data),
                indent=2,
                ensure_ascii=False
            ),
            risk_liquidation_data=json.dumps(
                self._serialize_for_json(liquidation_data),
                indent=2,
                ensure_ascii=False
            ),
            risk_params_data=json.dumps(
                self._serialize_for_json(risk_params),
                indent=2,
                ensure_ascii=False
            ),
            
            # 风控数据占位符 (用于提示AI)
            atr_stop_price=stop_loss_data.get("stop_price", "N/A"),
            atr_stop_distance=f"{stop_loss_data.get('distance_percent', 0):.2f}",
            liq_price=f"{liquidation_data.get('liquidation_price', 'N/A')}",
            liq_distance=f"{liquidation_data.get('distance_percent', 0):.2f}",
            safe_leverage=liquidation_data.get("safe_leverage", "N/A"),
            risk_amount="XXX",
            reward_1="XXX",
            reward_2="XXX",
            
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
                resonance.get("strength", 0),
                user_intent
            )
            
            full_report = header + result
            
            # 提取结构化交易数据
            trade_data = self._extract_trade_json(result)
            
            return {
                "text": full_report,
                "trade_data": trade_data,
                "model_used": self.get_model_name(),
            }
            
        except Exception as e:
            raise Exception(f"AI分析失败: {str(e)}")

    def _generate_report_header(
        self, 
        symbol: str, 
        timeframe: str, 
        resonance_strength: int,
        user_intent: UserIntent
    ) -> str:
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
**用户意图**: {user_intent.direction.upper()} | {user_intent.leverage}x杠杆 | 风险{user_intent.risk_percent}%  
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
