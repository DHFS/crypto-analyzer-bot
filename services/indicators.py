"""技术指标计算服务 - 支持多时间周期共振分析"""
from typing import Dict, Optional
import pandas as pd
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange


class IndicatorService:
    """技术指标计算服务 - 支持多周期分析"""

    def calculate_all(self, df: pd.DataFrame) -> dict:
        """
        计算所有技术指标 (单周期版本)

        Args:
            df: K线数据 DataFrame (需要 open, high, low, close, volume 列)

        Returns:
            dict with all indicator values
        """
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # 均线 MA
        ma5 = SMAIndicator(close, window=5).sma_indicator()
        ma10 = SMAIndicator(close, window=10).sma_indicator()
        ma20 = SMAIndicator(close, window=20).sma_indicator()
        ma60 = SMAIndicator(close, window=60).sma_indicator()
        ma120 = SMAIndicator(close, window=120).sma_indicator()

        # 指数均线 EMA
        ema7 = EMAIndicator(close, window=7).ema_indicator()
        ema25 = EMAIndicator(close, window=25).ema_indicator()
        ema99 = EMAIndicator(close, window=99).ema_indicator()

        # MACD
        macd_indicator = MACD(close, window_slow=26, window_fast=12, window_sign=9)
        macd_line = macd_indicator.macd()
        macd_signal = macd_indicator.macd_signal()
        macd_hist = macd_indicator.macd_diff()

        # RSI
        rsi = RSIIndicator(close, window=14).rsi()

        # 布林带
        bb = BollingerBands(close, window=20, window_dev=2)
        bb_upper = bb.bollinger_hband()
        bb_middle = bb.bollinger_mavg()
        bb_lower = bb.bollinger_lband()

        # ATR (平均真实波幅)
        atr = AverageTrueRange(high, low, close, window=14).average_true_range()

        # 成交量均线
        vol_ma5 = SMAIndicator(volume, window=5).sma_indicator()
        vol_ma20 = SMAIndicator(volume, window=20).sma_indicator()

        # 获取最新值
        current_price = close.iloc[-1]

        return {
            "current_price": current_price,
            # 均线
            "ma": {
                "ma5": self._safe_last(ma5),
                "ma10": self._safe_last(ma10),
                "ma20": self._safe_last(ma20),
                "ma60": self._safe_last(ma60),
                "ma120": self._safe_last(ma120),
            },
            # EMA
            "ema": {
                "ema7": self._safe_last(ema7),
                "ema25": self._safe_last(ema25),
                "ema99": self._safe_last(ema99),
            },
            # MACD
            "macd": {
                "macd": self._safe_last(macd_line),
                "signal": self._safe_last(macd_signal),
                "histogram": self._safe_last(macd_hist),
                "trend": self._macd_trend(macd_line, macd_signal),
            },
            # RSI
            "rsi": self._safe_last(rsi),
            "rsi_status": self._rsi_status(self._safe_last(rsi)),
            # 布林带
            "bollinger": {
                "upper": self._safe_last(bb_upper),
                "middle": self._safe_last(bb_middle),
                "lower": self._safe_last(bb_lower),
                "bandwidth": self._bollinger_bandwidth(
                    self._safe_last(bb_upper), 
                    self._safe_last(bb_lower), 
                    current_price
                ),
                "position": self._bollinger_position(
                    current_price,
                    self._safe_last(bb_upper),
                    self._safe_last(bb_lower)
                ),
            },
            # ATR
            "atr": self._safe_last(atr),
            "atr_percent": (self._safe_last(atr) / current_price * 100) if current_price else 0,
            # 成交量
            "volume": {
                "current": volume.iloc[-1],
                "ma5": self._safe_last(vol_ma5),
                "ma20": self._safe_last(vol_ma20),
                "trend": "放量" if volume.iloc[-1] > self._safe_last(vol_ma5) else "缩量",
            },
            # 近期高低点
            "recent": {
                "high_20": high.tail(20).max(),
                "low_20": low.tail(20).min(),
                "range_20": high.tail(20).max() - low.tail(20).min(),
            },
            # K线形态
            "candle": {
                "body_size": abs(close.iloc[-1] - df["open"].iloc[-1]),
                "upper_shadow": high.iloc[-1] - max(close.iloc[-1], df["open"].iloc[-1]),
                "lower_shadow": min(close.iloc[-1], df["open"].iloc[-1]) - low.iloc[-1],
            }
        }

    def calculate_multi_timeframe(
        self, 
        multi_tf_data: dict
    ) -> dict:
        """
        计算多时间周期技术指标 (步骤2核心功能)

        Args:
            multi_tf_data: get_multi_timeframe_data() 返回的数据结构

        Returns:
            dict: {
                "symbol": str,
                "primary_timeframe": str,
                "timeframes": {
                    "small": {"name": str, "indicators": dict},
                    "primary": {"name": str, "indicators": dict},
                    "large": {"name": str, "indicators": dict}
                },
                "resonance_analysis": dict  # 共振分析结果
            }
        """
        timeframes_data = multi_tf_data["timeframes"]
        
        # 分别计算三个周期的指标
        small_indicators = self.calculate_all(timeframes_data["small"]["klines"])
        primary_indicators = self.calculate_all(timeframes_data["primary"]["klines"])
        large_indicators = self.calculate_all(timeframes_data["large"]["klines"])

        result = {
            "symbol": multi_tf_data["symbol"],
            "primary_timeframe": multi_tf_data["primary"],
            "timeframes": {
                "small": {
                    "name": timeframes_data["small"]["name"],
                    "description": timeframes_data["small"]["description"],
                    "indicators": small_indicators
                },
                "primary": {
                    "name": timeframes_data["primary"]["name"],
                    "description": timeframes_data["primary"]["description"],
                    "indicators": primary_indicators
                },
                "large": {
                    "name": timeframes_data["large"]["name"],
                    "description": timeframes_data["large"]["description"],
                    "indicators": large_indicators
                }
            },
            "resonance_analysis": self._analyze_resonance(
                small_indicators,
                primary_indicators,
                large_indicators,
                timeframes_data["small"]["name"],
                timeframes_data["primary"]["name"],
                timeframes_data["large"]["name"]
            )
        }

        return result

    def _analyze_resonance(
        self,
        small: dict,
        primary: dict,
        large: dict,
        small_name: str,
        primary_name: str,
        large_name: str
    ) -> dict:
        """
        分析多周期共振情况

        Returns:
            dict with trend alignment, strength, and conflict warnings
        """
        # 趋势判断逻辑
        def get_trend(indicators: dict) -> str:
            rsi = indicators.get("rsi", 50)
            macd_hist = indicators["macd"].get("histogram", 0)
            price = indicators.get("current_price", 0)
            ema25 = indicators["ema"].get("ema25", price)
            
            bullish_signals = 0
            if rsi > 55:
                bullish_signals += 1
            if macd_hist > 0:
                bullish_signals += 1
            if price > ema25:
                bullish_signals += 1
            
            if bullish_signals >= 2:
                return "bullish"
            elif bullish_signals == 1:
                return "neutral"
            else:
                return "bearish"

        small_trend = get_trend(small)
        primary_trend = get_trend(primary)
        large_trend = get_trend(large)

        # 判断共振/冲突
        trends = [small_trend, primary_trend, large_trend]
        bullish_count = trends.count("bullish")
        bearish_count = trends.count("bearish")
        neutral_count = trends.count("neutral")

        # 共振强度
        if bullish_count == 3:
            resonance = "强烈看涨共振"
            strength = 5
        elif bearish_count == 3:
            resonance = "强烈看跌共振"
            strength = -5
        elif bullish_count == 2 and bearish_count == 0:
            resonance = "偏多共振"
            strength = 3
        elif bearish_count == 2 and bullish_count == 0:
            resonance = "偏空共振"
            strength = -3
        elif bullish_count == 2 and bearish_count == 1:
            resonance = "多周期冲突(大趋势分歧)"
            strength = 1
        elif bearish_count == 2 and bullish_count == 1:
            resonance = "多周期冲突(大趋势分歧)"
            strength = -1
        else:
            resonance = "震荡/无明显趋势"
            strength = 0

        return {
            "trends": {
                small_name: small_trend,
                primary_name: primary_trend,
                large_name: large_trend,
            },
            "resonance": resonance,
            "strength": strength,
            "recommendation": self._resonance_recommendation(strength, small_trend, primary_trend, large_trend),
            "conflicts": self._identify_conflicts(small_trend, primary_trend, large_trend, small_name, primary_name, large_name)
        }

    def _resonance_recommendation(self, strength: int, small: str, primary: str, large: str) -> str:
        """基于共振强度给出交易建议"""
        if strength >= 4:
            return "顺势追涨/杀跌，可重仓"
        elif strength >= 2:
            return "顺大势交易，标准仓位"
        elif strength <= -4:
            return "反手做空/做多，可重仓"
        elif strength <= -2:
            return "顺大势做空，标准仓位"
        elif abs(strength) <= 1:
            if large == "bullish":
                return "大周期看涨，等待小周期回调做多"
            elif large == "bearish":
                return "大周期看跌，等待小周期反弹做空"
            else:
                return "区间震荡，观望或轻仓高抛低吸"
        return "建议观望"

    def _identify_conflicts(self, small: str, primary: str, large: str, s_name: str, p_name: str, l_name: str) -> list:
        """识别周期冲突"""
        conflicts = []
        if small != primary:
            conflicts.append(f"{s_name}与{p_name}趋势不一致")
        if primary != large:
            conflicts.append(f"{p_name}与{l_name}趋势分歧")
        if small != large:
            conflicts.append(f"短周期与长周期背离")
        return conflicts if conflicts else ["无显著冲突"]

    # ============ 辅助方法 ============

    def _safe_last(self, series: pd.Series):
        """安全获取序列最后一个值"""
        if series is None or series.empty:
            return None
        val = series.iloc[-1]
        if pd.isna(val):
            return None
        return float(val)

    def _macd_trend(self, macd_line: pd.Series, signal_line: pd.Series) -> str:
        """判断 MACD 趋势"""
        if len(macd_line) < 2 or len(signal_line) < 2:
            return "unknown"
        
        curr_diff = macd_line.iloc[-1] - signal_line.iloc[-1]
        prev_diff = macd_line.iloc[-2] - signal_line.iloc[-2]
        
        if curr_diff > 0 and prev_diff <= 0:
            return "golden_cross"  # 金叉
        elif curr_diff < 0 and prev_diff >= 0:
            return "dead_cross"  # 死叉
        elif curr_diff > 0:
            return "bullish"
        else:
            return "bearish"

    def _rsi_status(self, rsi: Optional[float]) -> str:
        """RSI 状态判断"""
        if rsi is None:
            return "数据不足"
        if rsi >= 70:
            return "overbought"  # 超买
        if rsi <= 30:
            return "oversold"  # 超卖
        if rsi >= 60:
            return "bullish"
        if rsi <= 40:
            return "bearish"
        return "neutral"

    def _bollinger_bandwidth(
        self, 
        upper: Optional[float], 
        lower: Optional[float], 
        price: float
    ) -> dict:
        """计算布林带带宽和状态"""
        if upper is None or lower is None or price == 0:
            return {"value": 0, "status": "unknown"}
        
        bandwidth = (upper - lower) / price * 100
        
        if bandwidth < 2:
            status = "squeeze"  # 极度收窄，即将爆发
        elif bandwidth < 5:
            status = "narrow"  # 窄幅
        elif bandwidth < 10:
            status = "normal"
        else:
            status = "wide"  # 宽幅波动
            
        return {"value": bandwidth, "status": status}

    def _bollinger_position(
        self, 
        price: float, 
        upper: Optional[float], 
        lower: Optional[float]
    ) -> str:
        """判断价格在布林带中的位置"""
        if upper is None or lower is None:
            return "unknown"
        
        if price >= upper:
            return "upper_band"  # 触及上轨
        elif price <= lower:
            return "lower_band"  # 触及下轨
        mid = (upper + lower) / 2
        if price > mid:
            return "upper_half"
        else:
            return "lower_half"

    # ============ 格式化输出 ============

    def format_summary(self, indicators: dict, ticker: dict) -> str:
        """格式化指标摘要为可读文本"""
        price = indicators["current_price"]
        ma = indicators["ma"]
        ema = indicators["ema"]
        macd = indicators["macd"]
        rsi = indicators["rsi"]
        bb = indicators["bollinger"]
        atr = indicators["atr"]
        vol = indicators["volume"]
        recent = indicators["recent"]

        lines = [
            f"📊 {ticker['symbol']} 技术指标摘要",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"",
            f"💰 当前价格: {price:.4f}",
            f"📈 24h涨跌: {ticker['price_change_percent']:+.2f}%",
            f"📊 24h高/低: {ticker['high_24h']:.4f} / {ticker['low_24h']:.4f}",
            f"",
            f"📉 均线 (MA):",
            f"   MA5: {self._fmt(ma['ma5'])} | MA10: {self._fmt(ma['ma10'])}",
            f"   MA20: {self._fmt(ma['ma20'])} | MA60: {self._fmt(ma['ma60'])}",
            f"",
            f"📈 指数均线 (EMA):",
            f"   EMA7: {self._fmt(ema['ema7'])} | EMA25: {self._fmt(ema['ema25'])}",
            f"   EMA99: {self._fmt(ema['ema99'])}",
            f"",
            f"📈 MACD:",
            f"   DIF: {self._fmt(macd['macd'], 4)}",
            f"   DEA: {self._fmt(macd['signal'], 4)}",
            f"   柱状: {self._fmt(macd['histogram'], 4)}",
            f"",
            f"📊 RSI(14): {self._fmt(rsi, 2)}",
            self._rsi_text_status(rsi),
            f"",
            f"📏 布林带:",
            f"   上轨: {self._fmt(bb['upper'])}",
            f"   中轨: {self._fmt(bb['middle'])}",
            f"   下轨: {self._fmt(bb['lower'])}",
            f"",
            f"📐 ATR(14): {self._fmt(atr, 4)}",
            f"",
            f"📦 成交量:",
            f"   当前: {self._fmt_vol(vol['current'])}",
            f"   MA5: {self._fmt_vol(vol['ma5'])}",
            f"   MA20: {self._fmt_vol(vol['ma20'])}",
            f"",
            f"🎯 近20根K线:",
            f"   最高: {recent['high_20']:.4f}",
            f"   最低: {recent['low_20']:.4f}",
        ]

        return "\n".join(lines)

    def format_multi_timeframe_summary(self, multi_indicators: dict) -> str:
        """格式化多周期指标摘要"""
        tf_data = multi_indicators["timeframes"]
        resonance = multi_indicators["resonance_analysis"]
        
        lines = [
            f"📊 {multi_indicators['symbol']} 多周期共振分析",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"",
            f"🔄 周期配置: {tf_data['small']['name']} → {tf_data['primary']['name']} → {tf_data['large']['name']}",
            f"",
            f"📈 各周期趋势:",
        ]
        
        for key in ["small", "primary", "large"]:
            tf = tf_data[key]
            ind = tf["indicators"]
            trend = resonance["trends"][tf["name"]]
            trend_icon = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}.get(trend, "⚪")
            lines.append(f"   {tf['name']} ({tf['description']}): {trend_icon} {trend}")
            lines.append(f"      价格: {ind['current_price']:.4f} | RSI: {ind['rsi']:.2f} | MACD: {ind['macd']['trend']}")
        
        lines.extend([
            f"",
            f"🎯 共振分析: {resonance['resonance']}",
            f"💪 共振强度: {resonance['strength']}/5",
            f"📋 交易建议: {resonance['recommendation']}",
        ])
        
        if resonance["conflicts"] and resonance["conflicts"][0] != "无显著冲突":
            lines.append(f"⚠️ 周期冲突:")
            for conflict in resonance["conflicts"]:
                lines.append(f"   • {conflict}")
        
        return "\n".join(lines)

    def _fmt(self, val, decimals: int = 4) -> str:
        """格式化数值"""
        if val is None:
            return "N/A"
        return f"{val:.{decimals}f}"

    def _fmt_vol(self, val) -> str:
        """格式化成交量"""
        if val is None:
            return "N/A"
        if val >= 1_000_000:
            return f"{val/1_000_000:.2f}M"
        if val >= 1_000:
            return f"{val/1_000:.2f}K"
        return f"{val:.2f}"

    def _rsi_text_status(self, rsi) -> str:
        """RSI文本状态判断"""
        if rsi is None:
            return "   状态: 数据不足"
        if rsi >= 70:
            return "   ⚠️ 超买区域 (>70)"
        if rsi <= 30:
            return "   ⚠️ 超卖区域 (<30)"
        if rsi >= 60:
            return "   📈 偏强势 (60-70)"
        if rsi <= 40:
            return "   📉 偏弱势 (30-40)"
        return "   ➖ 中性区域 (40-60)"
