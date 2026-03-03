"""后台订单追踪与结算服务

功能:
1. 定时查询未结算订单
2. 调用 Binance API 获取价格数据
3. 判断 TP/SL 触发并结算
4. 更新数据库状态
"""
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from services.database import DatabaseService, TradeLog, get_database_service
from services.binance import BinanceService


@dataclass
class SettlementResult:
    """结算结果"""
    trade_id: int
    closed: bool
    close_reason: Optional[str]  # TP / SL / None
    close_price: Optional[float]
    pnl_percentage: Optional[float]
    message: str


class TradeTracker:
    """交易追踪与结算器"""

    def __init__(
        self,
        binance_service: Optional[BinanceService] = None,
        db_service: Optional[DatabaseService] = None
    ):
        self.binance = binance_service or BinanceService()
        self.db = db_service or get_database_service()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self, interval_minutes: int = 5):
        """启动后台追踪任务"""
        if self._running:
            print("⚠️ 追踪器已在运行")
            return
        
        self._running = True
        self._task = asyncio.create_task(
            self._tracking_loop(interval_minutes)
        )
        print(f"✅ 订单追踪器已启动 (检查间隔: {interval_minutes}分钟)")

    async def stop(self):
        """停止后台追踪任务"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.binance.close()
        print("🛑 订单追踪器已停止")

    async def _tracking_loop(self, interval_minutes: int):
        """后台追踪循环"""
        while self._running:
            try:
                print(f"\n🔍 [{datetime.now().strftime('%H:%M:%S')}] 开始检查未结算订单...")
                
                # 1. 处理过期订单
                expired_count = await self.db.expire_old_trades(max_age_hours=72)
                if expired_count > 0:
                    print(f"📌 已将 {expired_count} 笔超72小时订单标记为过期")
                
                # 2. 获取未结算订单
                open_trades = await self.db.get_open_trades(max_age_hours=72)
                
                if not open_trades:
                    print("📭 没有未结算订单")
                else:
                    print(f"📋 发现 {len(open_trades)} 笔未结算订单")
                    
                    # 3. 按交易对分组查询 (减少 API 调用)
                    symbol_trades = self._group_by_symbol(open_trades)
                    
                    for symbol, trades in symbol_trades.items():
                        try:
                            await self._check_and_settle_symbol_trades(symbol, trades)
                        except Exception as e:
                            print(f"❌ 检查 {symbol} 订单时出错: {e}")
                
                # 4. 等待下一次检查
                print(f"⏳ 下次检查: {interval_minutes}分钟后...")
                await asyncio.sleep(interval_minutes * 60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"❌ 追踪循环出错: {e}")
                await asyncio.sleep(60)  # 出错后1分钟重试

    def _group_by_symbol(self, trades: List[TradeLog]) -> Dict[str, List[TradeLog]]:
        """按交易对分组订单"""
        result = {}
        for trade in trades:
            if trade.symbol not in result:
                result[trade.symbol] = []
            result[trade.symbol].append(trade)
        return result

    async def _check_and_settle_symbol_trades(
        self,
        symbol: str,
        trades: List[TradeLog]
    ):
        """检查并结算某个交易对的所有未结订单"""
        # 获取最近24小时的数据用于判断最高/最低价
        try:
            # 使用 1小时K线获取最近24小时的高低价
            df = await self.binance.get_klines(symbol, "1h", limit=24)
            
            if df.empty:
                print(f"⚠️ 无法获取 {symbol} 的价格数据")
                return
            
            high_24h = df["high"].max()
            low_24h = df["low"].min()
            current_price = df["close"].iloc[-1]
            
            print(f"📊 {symbol} 24h价格范围: {low_24h:.4f} - {high_24h:.4f}, 当前: {current_price:.4f}")
            
            for trade in trades:
                result = self._check_trade_settlement(
                    trade, high_24h, low_24h, current_price
                )
                
                if result.closed:
                    # 执行结算
                    await self.db.close_trade(
                        trade_id=result.trade_id,
                        close_price=result.close_price,
                        close_reason=result.close_reason,
                        pnl_percentage=result.pnl_percentage
                    )
                    print(f"✅ 订单 #{trade.id} 已结算: {result.message}")
                else:
                    # 检查是否接近止损 (提醒)
                    self._check_near_liquidation(trade, current_price)
                    
        except Exception as e:
            print(f"❌ 获取 {symbol} 数据失败: {e}")

    def _check_trade_settlement(
        self,
        trade: TradeLog,
        high_24h: float,
        low_24h: float,
        current_price: float
    ) -> SettlementResult:
        """
        检查单个订单是否满足结算条件
        
        结算逻辑:
        - LONG: Low 触及 SL 则止损, High 触及 TP 则止盈
        - SHORT: High 触及 SL 则止损, Low 触及 TP 则止盈
        """
        if trade.direction == "LONG":
            # 检查是否触及止损
            if low_24h <= trade.sl_price:
                pnl = self._calculate_pnl(
                    trade.direction, trade.entry_price, trade.sl_price, trade.leverage
                )
                return SettlementResult(
                    trade_id=trade.id,
                    closed=True,
                    close_reason="SL",
                    close_price=trade.sl_price,
                    pnl_percentage=pnl,
                    message=f"LONG 止损 ({trade.sl_price:.4f}), PnL: {pnl:+.2f}%"
                )
            
            # 检查是否触及止盈
            if high_24h >= trade.tp_price:
                pnl = self._calculate_pnl(
                    trade.direction, trade.entry_price, trade.tp_price, trade.leverage
                )
                return SettlementResult(
                    trade_id=trade.id,
                    closed=True,
                    close_reason="TP",
                    close_price=trade.tp_price,
                    pnl_percentage=pnl,
                    message=f"LONG 止盈 ({trade.tp_price:.4f}), PnL: {pnl:+.2f}%"
                )
        
        else:  # SHORT
            # 检查是否触及止损
            if high_24h >= trade.sl_price:
                pnl = self._calculate_pnl(
                    trade.direction, trade.entry_price, trade.sl_price, trade.leverage
                )
                return SettlementResult(
                    trade_id=trade.id,
                    closed=True,
                    close_reason="SL",
                    close_price=trade.sl_price,
                    pnl_percentage=pnl,
                    message=f"SHORT 止损 ({trade.sl_price:.4f}), PnL: {pnl:+.2f}%"
                )
            
            # 检查是否触及止盈
            if low_24h <= trade.tp_price:
                pnl = self._calculate_pnl(
                    trade.direction, trade.entry_price, trade.tp_price, trade.leverage
                )
                return SettlementResult(
                    trade_id=trade.id,
                    closed=True,
                    close_reason="TP",
                    close_price=trade.tp_price,
                    pnl_percentage=pnl,
                    message=f"SHORT 止盈 ({trade.tp_price:.4f}), PnL: {pnl:+.2f}%"
                )
        
        # 未触发结算
        return SettlementResult(
            trade_id=trade.id,
            closed=False,
            close_reason=None,
            close_price=None,
            pnl_percentage=None,
            message="未触发结算条件"
        )

    def _calculate_pnl(
        self,
        direction: str,
        entry_price: float,
        exit_price: float,
        leverage: int
    ) -> float:
        """
        计算收益率 (已乘杠杆)
        
        Returns:
            收益率百分比 (如 10.5 表示 +10.5%, -5.2 表示 -5.2%)
        """
        if direction == "LONG":
            price_change = (exit_price - entry_price) / entry_price
        else:  # SHORT
            price_change = (entry_price - exit_price) / entry_price
        
        # 应用杠杆
        leveraged_pnl = price_change * leverage * 100  # 转换为百分比
        
        # 保留两位小数
        return round(leveraged_pnl, 2)

    def _check_near_liquidation(self, trade: TradeLog, current_price: float):
        """检查是否接近爆仓价，输出警告"""
        # 简化的警告逻辑: 价格距离止损 50% 以内
        if trade.direction == "LONG":
            distance_to_sl = (current_price - trade.sl_price) / trade.sl_price * 100
        else:
            distance_to_sl = (trade.sl_price - current_price) / trade.sl_price * 100
        
        if distance_to_sl < 0.5:  # 距离止损小于 0.5%
            print(f"⚠️ 警告: 订单 #{trade.id} ({trade.direction}) 接近止损! 当前价格: {current_price:.4f}, 止损: {trade.sl_price:.4f}")

    # ============ 手动结算接口 ============

    async def settle_trade_manually(
        self,
        trade_id: int,
        close_price: float,
        reason: str = "MANUAL"
    ) -> Optional[SettlementResult]:
        """手动结算订单"""
        trade = await self.db.get_trade_by_id(trade_id)
        if not trade:
            return None
        
        if trade.status != "OPEN":
            return SettlementResult(
                trade_id=trade_id,
                closed=False,
                close_reason=None,
                close_price=None,
                pnl_percentage=None,
                message=f"订单状态不是 OPEN，当前: {trade.status}"
            )
        
        pnl = self._calculate_pnl(
            trade.direction, trade.entry_price, close_price, trade.leverage
        )
        
        await self.db.close_trade(
            trade_id=trade_id,
            close_price=close_price,
            close_reason=reason,
            pnl_percentage=pnl
        )
        
        return SettlementResult(
            trade_id=trade_id,
            closed=True,
            close_reason=reason,
            close_price=close_price,
            pnl_percentage=pnl,
            message=f"手动结算完成, PnL: {pnl:+.2f}%"
        )


# ============ 全局单例 ============

_tracker: Optional[TradeTracker] = None


def get_trade_tracker(
    binance_service: Optional[BinanceService] = None,
    db_service: Optional[DatabaseService] = None
) -> TradeTracker:
    """获取追踪器单例"""
    global _tracker
    if _tracker is None:
        _tracker = TradeTracker(binance_service, db_service)
    return _tracker
