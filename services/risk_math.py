"""风控计算服务 - 止损点位、爆仓价、仓位管理"""
import pandas as pd
from typing import Optional, Dict, Literal, Tuple
from dataclasses import dataclass


@dataclass
class PositionRisk:
    """仓位风险计算结果"""
    position_size: float          # 仓位数量 (币)
    position_value: float         # 仓位价值 (USDT)
    margin_used: float            # 占用保证金
    leverage: int                 # 杠杆倍数
    entry_price: float            # 入场价格
    
    # 止损相关
    stop_loss_price: float        # 止损价格
    stop_loss_distance: float     # 止损距离 (%)
    stop_loss_amount: float       # 止损金额
    
    # 爆仓相关
    liquidation_price: float      # 爆仓价格
    liquidation_distance: float   # 爆仓距离 (%)
    
    # 风险指标
    risk_reward_ratio: float      # 盈亏比
    risk_percent: float           # 风险占本金比例 (%)
    margin_ratio: float           # 保证金率 (%)
    max_leverage: int             # 理论最大杠杆
    
    # 建议
    recommendation: str           # 风控建议
    risk_level: str               # 风险等级


class RiskMathService:
    """风控数学计算服务"""

    # 风险等级阈值
    RISK_LEVELS = {
        "conservative": {"max_risk": 1.0, "min_rr": 2.0},   # 保守
        "moderate": {"max_risk": 2.0, "min_rr": 1.5},       # 适中
        "aggressive": {"max_risk": 3.0, "min_rr": 1.0},     # 激进
    }

    def __init__(self):
        pass

    def calculate_stop_loss(
        self,
        df: pd.DataFrame,
        current_price: float,
        direction: Literal["long", "short"],
        method: Literal["atr", "fixed", "support_resistance"] = "atr",
        atr_multiplier: float = 2.0,
        fixed_percent: float = 2.0,
        support_resistance_level: Optional[float] = None
    ) -> Dict:
        """
        计算止损点位

        Args:
            df: K线数据 DataFrame
            current_price: 当前价格
            direction: 方向 (long/short)
            method: 止损计算方法
            atr_multiplier: ATR倍数 (ATR方法)
            fixed_percent: 固定百分比 (固定方法)
            support_resistance_level: 支撑/阻力位 (支撑阻力方法)

        Returns:
            dict: 止损计算结果
        """
        if method == "atr":
            return self._calculate_atr_stop(df, current_price, direction, atr_multiplier)
        elif method == "fixed":
            return self._calculate_fixed_stop(current_price, direction, fixed_percent)
        elif method == "support_resistance":
            return self._calculate_sr_stop(
                current_price, direction, support_resistance_level
            )
        else:
            raise ValueError(f"不支持的止损计算方法: {method}")

    def _calculate_atr_stop(
        self,
        df: pd.DataFrame,
        current_price: float,
        direction: Literal["long", "short"],
        atr_multiplier: float = 2.0
    ) -> Dict:
        """基于 ATR 的止损计算"""
        from ta.volatility import AverageTrueRange

        high = df["high"]
        low = df["low"]
        close = df["close"]

        # 计算 ATR(14)
        atr = AverageTrueRange(high, low, close, window=14).average_true_range()
        current_atr = atr.iloc[-1]

        # 计算止损价格
        if direction == "long":
            stop_price = current_price - (current_atr * atr_multiplier)
            # 考虑近期低点作为额外保护
            recent_low = low.tail(20).min()
            stop_price = min(stop_price, recent_low * 0.995)  # 略低于近期低点
        else:
            stop_price = current_price + (current_atr * atr_multiplier)
            # 考虑近期高点作为额外保护
            recent_high = high.tail(20).max()
            stop_price = max(stop_price, recent_high * 1.005)  # 略高于近期高点

        distance_percent = abs(stop_price - current_price) / current_price * 100

        return {
            "method": "ATR",
            "stop_price": stop_price,
            "atr_value": current_atr,
            "atr_multiplier": atr_multiplier,
            "distance": abs(stop_price - current_price),
            "distance_percent": distance_percent,
            "direction": direction,
            "recent_high_20": high.tail(20).max(),
            "recent_low_20": low.tail(20).min(),
        }

    def _calculate_fixed_stop(
        self,
        current_price: float,
        direction: Literal["long", "short"],
        fixed_percent: float = 2.0
    ) -> Dict:
        """基于固定百分比的止损计算"""
        if direction == "long":
            stop_price = current_price * (1 - fixed_percent / 100)
        else:
            stop_price = current_price * (1 + fixed_percent / 100)

        return {
            "method": "Fixed",
            "stop_price": stop_price,
            "fixed_percent": fixed_percent,
            "distance": abs(stop_price - current_price),
            "distance_percent": fixed_percent,
            "direction": direction,
        }

    def _calculate_sr_stop(
        self,
        current_price: float,
        direction: Literal["long", "short"],
        support_resistance_level: Optional[float]
    ) -> Dict:
        """基于支撑/阻力位的止损计算"""
        if support_resistance_level is None:
            raise ValueError("支撑阻力方法需要提供支撑/阻力位价格")

        # 在关键位外侧设置缓冲
        buffer_percent = 0.5  # 0.5% 缓冲

        if direction == "long":
            stop_price = support_resistance_level * (1 - buffer_percent / 100)
        else:
            stop_price = support_resistance_level * (1 + buffer_percent / 100)

        distance_percent = abs(stop_price - current_price) / current_price * 100

        return {
            "method": "Support/Resistance",
            "stop_price": stop_price,
            "sr_level": support_resistance_level,
            "buffer_percent": buffer_percent,
            "distance": abs(stop_price - current_price),
            "distance_percent": distance_percent,
            "direction": direction,
        }

    def calculate_liquidation_price(
        self,
        entry_price: float,
        direction: Literal["long", "short"],
        leverage: int,
        margin_type: Literal["isolated", "cross"] = "isolated",
        maintenance_margin_rate: float = 0.004,  # Binance 默认维持保证金率
        maintenance_amount: float = 0
    ) -> Dict:
        """
        计算爆仓价格

        Args:
            entry_price: 入场价格
            direction: 方向 (long/short)
            leverage: 杠杆倍数
            margin_type: 保证金模式 (isolated/cross)
            maintenance_margin_rate: 维持保证金率
            maintenance_amount: 维持保证金额调整

        Returns:
            dict: 爆仓计算结果
        """
        # 初始保证金率 = 1 / 杠杆
        initial_margin_rate = 1 / leverage

        if margin_type == "isolated":
            # 逐仓爆仓公式
            if direction == "long":
                liq_price = entry_price * (
                    1 - initial_margin_rate + maintenance_margin_rate
                ) / (1 + maintenance_amount / (entry_price * leverage))
            else:
                liq_price = entry_price * (
                    1 + initial_margin_rate - maintenance_margin_rate
                ) / (1 - maintenance_amount / (entry_price * leverage))
        else:
            # 全仓爆仓计算更复杂，需要可用余额
            # 这里提供简化版本
            liq_price = entry_price * (
                1 - (initial_margin_rate * 0.9) if direction == "long" 
                else 1 + (initial_margin_rate * 0.9)
            )

        # 计算爆仓距离
        distance = abs(liq_price - entry_price)
        distance_percent = distance / entry_price * 100

        # 计算安全杠杆 (爆仓距离 > 止损距离的2倍)
        safe_leverage = self._calculate_safe_leverage(
            entry_price, direction, distance_percent / 2
        )

        # 爆仓风险评级
        if distance_percent >= 20:
            risk_rating = "安全 🟢"
        elif distance_percent >= 10:
            risk_rating = "中等 🟡"
        elif distance_percent >= 5:
            risk_rating = "高危 🟠"
        else:
            risk_rating = "极高危 🔴"

        return {
            "liquidation_price": liq_price,
            "distance": distance,
            "distance_percent": distance_percent,
            "direction": direction,
            "leverage": leverage,
            "margin_type": margin_type,
            "maintenance_margin_rate": maintenance_margin_rate,
            "safe_leverage": safe_leverage,
            "risk_rating": risk_rating,
            "warning": distance_percent < 10,  # 爆仓距离小于10%发出警告
        }

    def _calculate_safe_leverage(
        self,
        entry_price: float,
        direction: Literal["long", "short"],
        min_distance_percent: float
    ) -> int:
        """计算安全杠杆倍数"""
        # 简化计算: 杠杆 = 1 / (距离%/100 * 0.9)
        safe_lev = int(1 / (min_distance_percent / 100 * 0.9))
        return min(safe_lev, 125)  # Binance 最大125倍

    def calculate_position_risk(
        self,
        capital: float,
        entry_price: float,
        stop_loss_price: float,
        target_price: Optional[float] = None,
        risk_percent: float = 2.0,
        leverage: int = 1,
        direction: Literal["long", "short"] = "long"
    ) -> PositionRisk:
        """
        完整仓位风险计算

        Args:
            capital: 总本金 (USDT)
            entry_price: 入场价格
            stop_loss_price: 止损价格
            target_price: 目标价格 (用于计算盈亏比)
            risk_percent: 愿意承担的本金风险比例 (%)
            leverage: 杠杆倍数
            direction: 交易方向

        Returns:
            PositionRisk: 仓位风险计算结果
        """
        # 计算止损距离
        stop_distance = abs(entry_price - stop_loss_price)
        stop_distance_percent = stop_distance / entry_price * 100

        # 计算止损金额 (本金 * 风险比例)
        stop_loss_amount = capital * risk_percent / 100

        # 计算仓位规模
        # 止损金额 = 仓位价值 * 止损距离%
        # 仓位价值 = 止损金额 / 止损距离%
        position_value = stop_loss_amount / (stop_distance_percent / 100)
        position_size = position_value / entry_price  # 币的数量

        # 占用保证金
        margin_used = position_value / leverage

        # 计算爆仓价
        liq_calc = self.calculate_liquidation_price(
            entry_price, direction, leverage
        )
        liquidation_price = liq_calc["liquidation_price"]
        liquidation_distance = liq_calc["distance_percent"]

        # 计算盈亏比
        if target_price:
            reward = abs(target_price - entry_price)
            risk_reward_ratio = reward / stop_distance if stop_distance > 0 else 0
        else:
            # 使用 R:R = 1:2 的默认值
            risk_reward_ratio = 2.0

        # 保证金率 (保证金 / 仓位价值)
        margin_ratio = (margin_used / position_value) * 100 if position_value > 0 else 0

        # 理论最大杠杆 (爆仓距离 > 止损距离 * 1.5)
        max_leverage = self._calculate_safe_leverage(
            entry_price, direction, stop_distance_percent * 1.5
        )

        # 风险评估
        risk_level = self._assess_risk_level(
            risk_percent, risk_reward_ratio, liquidation_distance
        )

        # 生成建议
        recommendation = self._generate_recommendation(
            leverage, max_leverage, liquidation_distance, 
            risk_reward_ratio, risk_level
        )

        return PositionRisk(
            position_size=position_size,
            position_value=position_value,
            margin_used=margin_used,
            leverage=leverage,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            stop_loss_distance=stop_distance_percent,
            stop_loss_amount=stop_loss_amount,
            liquidation_price=liquidation_price,
            liquidation_distance=liquidation_distance,
            risk_reward_ratio=risk_reward_ratio,
            risk_percent=risk_percent,
            margin_ratio=margin_ratio,
            max_leverage=max_leverage,
            recommendation=recommendation,
            risk_level=risk_level
        )

    def calculate_position_size(
        self,
        capital: float,
        entry_price: float,
        stop_loss_price: float,
        risk_percent: float = 2.0
    ) -> Dict:
        """
        简化的仓位规模计算

        Args:
            capital: 总本金
            entry_price: 入场价格
            stop_loss_price: 止损价格
            risk_percent: 风险比例

        Returns:
            dict: 仓位规模建议
        """
        stop_distance = abs(entry_price - stop_loss_price)
        stop_distance_percent = stop_distance / entry_price * 100
        
        risk_amount = capital * risk_percent / 100
        position_value = risk_amount / (stop_distance_percent / 100)
        position_size = position_value / entry_price

        return {
            "capital": capital,
            "risk_percent": risk_percent,
            "risk_amount": risk_amount,
            "position_value": position_value,
            "position_size": position_size,
            "stop_distance_percent": stop_distance_percent,
            "max_leverage_2x": int(position_value / (capital * 0.5)),
            "max_leverage_5x": int(position_value / (capital * 0.2)),
            "max_leverage_10x": int(position_value / (capital * 0.1)),
        }

    def calculate_leverage_suggestion(
        self,
        entry_price: float,
        stop_loss_price: float,
        direction: Literal["long", "short"],
        risk_tolerance: Literal["conservative", "moderate", "aggressive"] = "moderate"
    ) -> Dict:
        """
        杠杆倍数建议

        Args:
            entry_price: 入场价格
            stop_loss_price: 止损价格
            direction: 交易方向
            risk_tolerance: 风险承受度

        Returns:
            dict: 杠杆建议
        """
        stop_distance = abs(entry_price - stop_loss_price)
        stop_distance_percent = stop_distance / entry_price * 100

        # 根据风险承受度设置安全缓冲
        buffer_map = {
            "conservative": 3.0,   # 保守: 爆仓距离 > 3倍止损距离
            "moderate": 2.0,       # 适中: 爆仓距离 > 2倍止损距离
            "aggressive": 1.5,     # 激进: 爆仓距离 > 1.5倍止损距离
        }
        buffer = buffer_map.get(risk_tolerance, 2.0)

        # 计算建议杠杆
        # 爆仓距离 ≈ 100 / 杠杆% (简化公式)
        # 目标: 爆仓距离 > 止损距离 * buffer
        # 100 / 杠杆 > 止损距离% * buffer
        # 杠杆 < 100 / (止损距离% * buffer)
        max_safe_leverage = int(100 / (stop_distance_percent * buffer))
        max_safe_leverage = min(max_safe_leverage, 125)  # 限制最大125倍

        # 根据风险承受度给出具体建议
        if risk_tolerance == "conservative":
            suggested = min(max_safe_leverage, 3)
        elif risk_tolerance == "moderate":
            suggested = min(max_safe_leverage, 10)
        else:
            suggested = min(max_safe_leverage, 20)

        return {
            "risk_tolerance": risk_tolerance,
            "stop_distance_percent": stop_distance_percent,
            "safety_buffer": buffer,
            "max_safe_leverage": max_safe_leverage,
            "suggested_leverage": suggested,
            "warning": max_safe_leverage < 2,
        }

    def calculate_risk_reward(
        self,
        entry_price: float,
        stop_loss_price: float,
        target_price: float
    ) -> Dict:
        """
        计算盈亏比

        Args:
            entry_price: 入场价格
            stop_loss_price: 止损价格
            target_price: 目标价格

        Returns:
            dict: 盈亏比分析
        """
        risk = abs(entry_price - stop_loss_price)
        reward = abs(target_price - entry_price)
        
        rr_ratio = reward / risk if risk > 0 else 0
        
        risk_percent = risk / entry_price * 100
        reward_percent = reward / entry_price * 100

        # 评估盈亏比质量
        if rr_ratio >= 3:
            quality = "优秀 (>= 1:3)"
        elif rr_ratio >= 2:
            quality = "良好 (>= 1:2)"
        elif rr_ratio >= 1.5:
            quality = "可接受 (>= 1:1.5)"
        elif rr_ratio >= 1:
            quality = "一般 (>= 1:1)"
        else:
            quality = "差 (< 1:1)，不建议入场"

        # 计算胜率要求 (凯利公式简化)
        # f* = (bp - q) / b, 其中 b = 盈亏比, p = 胜率, q = 败率
        # 假设 f* = 0 (不亏不赚), 则 p = 1 / (b + 1)
        required_winrate = 1 / (rr_ratio + 1) * 100 if rr_ratio > 0 else 50

        return {
            "entry_price": entry_price,
            "stop_loss_price": stop_loss_price,
            "target_price": target_price,
            "risk": risk,
            "reward": reward,
            "risk_percent": risk_percent,
            "reward_percent": reward_percent,
            "risk_reward_ratio": rr_ratio,
            "quality": quality,
            "required_winrate": required_winrate,
            "suggested": "建议盈亏比 >= 1:2" if rr_ratio < 2 else "盈亏比合理"
        }

    # ============ AI 分析专用方法 ============

    def prepare_ai_risk_data(
        self,
        df: pd.DataFrame,
        symbol: str,
        current_price: float,
        direction: Literal["long", "short"],
        leverage: int = 1,
        risk_percent: float = 2.0,
        capital: float = 10000,
        target_price: Optional[float] = None,
    ) -> Dict:
        """
        为 AI 分析准备完整的风控数据包

        Args:
            df: K线数据 DataFrame
            symbol: 交易对
            current_price: 当前价格
            direction: 交易方向
            leverage: 杠杆倍数
            risk_percent: 风险比例
            capital: 本金
            target_price: 目标价格

        Returns:
            dict: AI 分析所需的风控数据
        """
        # 1. 计算 ATR 止损
        stop_loss_data = self.calculate_stop_loss(
            df=df,
            current_price=current_price,
            direction=direction,
            method="atr",
            atr_multiplier=2.0
        )

        # 2. 计算爆仓价格
        liquidation_data = self.calculate_liquidation_price(
            entry_price=current_price,
            direction=direction,
            leverage=leverage
        )

        # 3. 计算完整仓位风险
        position_risk = self.calculate_position_risk(
            capital=capital,
            entry_price=current_price,
            stop_loss_price=stop_loss_data["stop_price"],
            target_price=target_price,
            risk_percent=risk_percent,
            leverage=leverage,
            direction=direction
        )

        # 4. 计算杠杆建议
        leverage_suggestion = self.calculate_leverage_suggestion(
            entry_price=current_price,
            stop_loss_price=stop_loss_data["stop_price"],
            direction=direction,
            risk_tolerance="moderate"
        )

        # 5. 计算盈亏比 (如果有目标价)
        rr_data = None
        if target_price:
            rr_data = self.calculate_risk_reward(
                entry_price=current_price,
                stop_loss_price=stop_loss_data["stop_price"],
                target_price=target_price
            )

        # 6. 整合风险参数
        risk_params = {
            "capital": capital,
            "planned_leverage": leverage,
            "suggested_leverage": leverage_suggestion["suggested_leverage"],
            "max_safe_leverage": leverage_suggestion["max_safe_leverage"],
            "risk_percent": risk_percent,
            "direction": direction,
            "symbol": symbol,
        }

        return {
            "stop_loss": stop_loss_data,
            "liquidation": liquidation_data,
            "position_risk": {
                "position_size": position_risk.position_size,
                "position_value": position_risk.position_value,
                "margin_used": position_risk.margin_used,
                "stop_loss_amount": position_risk.stop_loss_amount,
                "risk_reward_ratio": position_risk.risk_reward_ratio,
                "risk_level": position_risk.risk_level,
            },
            "leverage_suggestion": leverage_suggestion,
            "risk_reward": rr_data,
            "risk_params": risk_params,
        }

    def calculate_risk_for_analysis(
        self,
        multi_tf_data: Dict,
        direction: Literal["long", "short"],
        leverage: int = 1,
        risk_percent: float = 2.0,
        capital: float = 10000,
    ) -> Dict:
        """
        为多时间周期分析计算风控数据

        Args:
            multi_tf_data: 多时间周期数据 (包含 small, primary, large)
            direction: 交易方向
            leverage: 杠杆倍数
            risk_percent: 风险比例
            capital: 本金

        Returns:
            dict: 各周期的风控数据
        """
        primary_df = multi_tf_data["timeframes"]["primary"]["klines"]
        current_price = primary_df["close"].iloc[-1]

        # 为主周期计算风控数据
        risk_data = self.prepare_ai_risk_data(
            df=primary_df,
            symbol=multi_tf_data.get("symbol", ""),
            current_price=current_price,
            direction=direction,
            leverage=leverage,
            risk_percent=risk_percent,
            capital=capital,
        )

        return risk_data

    def assess_go_no_go(
        self,
        risk_data: Dict,
        min_rr_ratio: float = 1.5,
        max_risk_level: str = "中等风险 🟡"
    ) -> Dict:
        """
        GO / NO-GO 决策评估

        Args:
            risk_data: 风控数据
            min_rr_ratio: 最低盈亏比要求
            max_risk_level: 最高可接受风险等级

        Returns:
            dict: 决策结果
        """
        position_risk = risk_data.get("position_risk", {})
        liquidation = risk_data.get("liquidation", {})
        leverage_suggestion = risk_data.get("leverage_suggestion", {})
        
        rr_ratio = position_risk.get("risk_reward_ratio", 0)
        liq_distance = liquidation.get("distance_percent", 0)
        risk_level = position_risk.get("risk_level", "")
        planned_leverage = risk_data.get("risk_params", {}).get("planned_leverage", 1)
        suggested_leverage = leverage_suggestion.get("suggested_leverage", 1)

        # 决策条件检查
        conditions = []
        
        # 1. 盈亏比检查
        rr_pass = rr_ratio >= min_rr_ratio
        conditions.append({
            "name": "盈亏比",
            "passed": rr_pass,
            "value": f"1:{rr_ratio:.2f}",
            "requirement": f">= 1:{min_rr_ratio}"
        })

        # 2. 爆仓距离检查
        liq_pass = liq_distance >= 10  # 爆仓距离至少10%
        conditions.append({
            "name": "爆仓距离",
            "passed": liq_pass,
            "value": f"{liq_distance:.2f}%",
            "requirement": ">= 10%"
        })

        # 3. 杠杆检查
        leverage_pass = planned_leverage <= suggested_leverage
        conditions.append({
            "name": "杠杆倍数",
            "passed": leverage_pass,
            "value": f"{planned_leverage}x",
            "requirement": f"<= {suggested_leverage}x"
        })

        # 4. 风险等级检查
        high_risk_levels = ["高风险 🟠", "极高风险 🔴"]
        risk_pass = risk_level not in high_risk_levels
        conditions.append({
            "name": "风险等级",
            "passed": risk_pass,
            "value": risk_level,
            "requirement": f"非高危"
        })

        # 综合决策
        all_passed = all(c["passed"] for c in conditions)
        
        if all_passed:
            decision = "GO"
            confidence = "高"
        elif sum(c["passed"] for c in conditions) >= 3:
            decision = "CONDITIONAL"
            confidence = "中"
        else:
            decision = "NO-GO"
            confidence = "低"

        return {
            "decision": decision,
            "confidence": confidence,
            "conditions": conditions,
            "summary": self._generate_go_summary(decision, conditions)
        }

    def _generate_go_summary(self, decision: str, conditions: list) -> str:
        """生成 GO/NO-GO 决策摘要"""
        passed_count = sum(c["passed"] for c in conditions)
        total_count = len(conditions)
        
        if decision == "GO":
            return f"✅ 所有条件满足 ({passed_count}/{total_count})，可以执行交易"
        elif decision == "CONDITIONAL":
            failed = [c["name"] for c in conditions if not c["passed"]]
            return f"⚠️ 部分条件满足 ({passed_count}/{total_count})，需注意: {', '.join(failed)}"
        else:
            failed = [c["name"] for c in conditions if not c["passed"]]
            return f"❌ 条件不满足 ({passed_count}/{total_count})，建议放弃: {', '.join(failed)}"

    def _assess_risk_level(
        self,
        risk_percent: float,
        rr_ratio: float,
        liquidation_distance: float
    ) -> str:
        """评估风险等级"""
        score = 0
        
        # 风险比例评分
        if risk_percent <= 1:
            score += 3
        elif risk_percent <= 2:
            score += 2
        elif risk_percent <= 3:
            score += 1
        else:
            score -= 1

        # 盈亏比评分
        if rr_ratio >= 3:
            score += 3
        elif rr_ratio >= 2:
            score += 2
        elif rr_ratio >= 1.5:
            score += 1
        else:
            score -= 2

        # 爆仓距离评分
        if liquidation_distance >= 20:
            score += 3
        elif liquidation_distance >= 10:
            score += 2
        elif liquidation_distance >= 5:
            score += 1
        else:
            score -= 3

        if score >= 7:
            return "低风险 🟢"
        elif score >= 4:
            return "中等风险 🟡"
        elif score >= 2:
            return "高风险 🟠"
        else:
            return "极高风险 🔴"

    def _generate_recommendation(
        self,
        leverage: int,
        max_leverage: int,
        liquidation_distance: float,
        rr_ratio: float,
        risk_level: str
    ) -> str:
        """生成风控建议"""
        recommendations = []

        # 杠杆建议
        if leverage > max_leverage:
            recommendations.append(
                f"⚠️ 当前杠杆 {leverage}x 过高，建议降至 {max_leverage}x 以下"
            )

        # 爆仓距离警告
        if liquidation_distance < 10:
            recommendations.append(
                f"🚨 爆仓距离仅 {liquidation_distance:.2f}%，建议降低杠杆或调整止损"
            )
        elif liquidation_distance < 20:
            recommendations.append(
                f"⚠️ 爆仓距离 {liquidation_distance:.2f}%，注意风险控制"
            )

        # 盈亏比建议
        if rr_ratio < 1.5:
            recommendations.append(
                f"📉 盈亏比 {rr_ratio:.2f} 偏低，建议寻找更好入场点或调整目标位"
            )
        elif rr_ratio >= 2:
            recommendations.append(
                f"📈 盈亏比 {rr_ratio:.2f} 良好"
            )

        # 综合建议
        if not recommendations:
            return "✅ 风控参数合理，可以执行交易"
        
        return " | ".join(recommendations)

    def format_risk_report(self, risk: PositionRisk, symbol: str = "") -> str:
        """格式化风险报告"""
        lines = [
            f"📊 {symbol} 风控分析报告" if symbol else "📊 风控分析报告",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"",
            f"💰 本金: {risk.entry_price * risk.position_size / risk.leverage:.2f} USDT",
            f"📈 入场价: {risk.entry_price:.4f}",
            f"📉 止损价: {risk.stop_loss_price:.4f} ({risk.stop_loss_distance:+.2f}%)",
            f"💥 爆仓价: {risk.liquidation_price:.4f} ({risk.liquidation_distance:+.2f}%)",
            f"",
            f"📦 仓位信息:",
            f"   数量: {risk.position_size:.6f}",
            f"   价值: {risk.position_value:.2f} USDT",
            f"   保证金: {risk.margin_used:.2f} USDT",
            f"   杠杆: {risk.leverage}x (建议最高 {risk.max_leverage}x)",
            f"",
            f"⚠️ 风险指标:",
            f"   止损金额: {risk.stop_loss_amount:.2f} USDT ({risk.risk_percent}%)",
            f"   盈亏比: 1:{risk.risk_reward_ratio:.2f}",
            f"   风险等级: {risk.risk_level}",
            f"",
            f"📋 建议: {risk.recommendation}",
        ]
        return "\n".join(lines)

    def format_stop_loss_summary(
        self, 
        stop_result: Dict, 
        symbol: str = ""
    ) -> str:
        """格式化止损分析摘要"""
        lines = [
            f"🛡️ {symbol} 止损分析" if symbol else "🛡️ 止损分析",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"",
            f"📍 止损价格: {stop_result['stop_price']:.4f}",
            f"📏 止损距离: {stop_result['distance_percent']:.2f}%",
            f"🔧 计算方法: {stop_result['method']}",
        ]

        if stop_result.get('atr_value'):
            lines.extend([
                f"",
                f"📊 ATR 详情:",
                f"   ATR(14): {stop_result['atr_value']:.4f}",
                f"   ATR倍数: {stop_result['atr_multiplier']}x",
                f"   近20日高: {stop_result['recent_high_20']:.4f}",
                f"   近20日低: {stop_result['recent_low_20']:.4f}",
            ])

        return "\n".join(lines)

    def format_liquidation_summary(
        self,
        liq_result: Dict,
        symbol: str = ""
    ) -> str:
        """格式化爆仓分析摘要"""
        warning_emoji = "🚨" if liq_result.get('warning') else "✅"
        
        lines = [
            f"💥 {symbol} 爆仓分析" if symbol else "💥 爆仓分析",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"",
            f"📍 爆仓价格: {liq_result['liquidation_price']:.4f}",
            f"📏 爆仓距离: {liq_result['distance_percent']:.2f}%",
            f"🔧 杠杆倍数: {liq_result['leverage']}x ({liq_result['margin_type']})",
            f"🛡️ 安全杠杆: {liq_result['safe_leverage']}x",
            f"📊 风险评级: {liq_result.get('risk_rating', 'N/A')}",
            f"",
            f"{warning_emoji} 状态: {'警告 - 爆仓风险较高' if liq_result.get('warning') else '安全'}",
        ]
        return "\n".join(lines)

    def format_ai_risk_summary(self, risk_data: Dict, symbol: str = "") -> str:
        """格式化 AI 风控数据摘要"""
        stop_loss = risk_data.get("stop_loss", {})
        liquidation = risk_data.get("liquidation", {})
        position_risk = risk_data.get("position_risk", {})
        leverage_suggestion = risk_data.get("leverage_suggestion", {})
        go_assessment = risk_data.get("go_assessment", {})
        
        lines = [
            f"🤖 {symbol} AI风控数据包" if symbol else "🤖 AI风控数据包",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"",
            f"🛡️ ATR 止损:",
            f"   价格: {stop_loss.get('stop_price', 0):.4f}",
            f"   距离: {stop_loss.get('distance_percent', 0):.2f}%",
            f"",
            f"💥 爆仓风险:",
            f"   价格: {liquidation.get('liquidation_price', 0):.4f}",
            f"   距离: {liquidation.get('distance_percent', 0):.2f}%",
            f"   评级: {liquidation.get('risk_rating', 'N/A')}",
            f"",
            f"⚖️ 盈亏比: 1:{position_risk.get('risk_reward_ratio', 0):.2f}",
            f"📊 风险等级: {position_risk.get('risk_level', 'N/A')}",
            f"🔧 杠杆建议: {leverage_suggestion.get('suggested_leverage', 'N/A')}x (最高{leverage_suggestion.get('max_safe_leverage', 'N/A')}x)",
        ]
        
        if go_assessment:
            lines.extend([
                f"",
                f"🎯 GO/NO-GO 决策: {go_assessment.get('decision', 'N/A')} (置信度: {go_assessment.get('confidence', 'N')})",
                f"📋 {go_assessment.get('summary', '')}",
            ])
        
        return "\n".join(lines)
