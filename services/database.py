"""数据库服务 - 交易日志与回测数据存储 (支持多模型竞技场v1 0304 00:48)

表结构:
- trade_logs: 交易记录表
- model_performance: 模型性能统计缓存表
"""
import sqlite3
import aiosqlite
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from contextlib import asynccontextmanager
import os


# 数据库路径
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "trades.db")


@dataclass
class TradeLog:
    """交易记录数据类"""
    id: Optional[int]
    timestamp: str
    symbol: str
    timeframe: str
    direction: str  # LONG / SHORT
    leverage: int
    entry_price: float
    tp_price: float
    sl_price: float
    ai_model: str  # 模型名称
    status: str = "OPEN"  # OPEN / CLOSED_TP / CLOSED_SL / EXPIRED
    pnl_percentage: Optional[float] = None
    close_timestamp: Optional[str] = None
    close_price: Optional[float] = None
    close_reason: Optional[str] = None
    ai_raw_response: Optional[str] = None


@dataclass
class ModelStats:
    """模型统计结果"""
    ai_model: str
    total_trades: int
    open_trades: int
    closed_trades: int
    win_count: int
    loss_count: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    avg_win: float
    avg_loss: float


class DatabaseService:
    """异步数据库服务"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self._ensure_data_dir()

    def _ensure_data_dir(self):
        """确保数据目录存在"""
        data_dir = os.path.dirname(self.db_path)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)

    @asynccontextmanager
    async def _get_connection(self):
        """获取数据库连接 (上下文管理器)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            yield db

    async def init_db(self):
        """初始化数据库表结构 (支持自动升级)"""
        async with self._get_connection() as db:
            # 创建主表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS trade_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ('LONG', 'SHORT')),
                    leverage INTEGER NOT NULL DEFAULT 1,
                    entry_price REAL NOT NULL,
                    tp_price REAL NOT NULL,
                    sl_price REAL NOT NULL,
                    ai_model TEXT NOT NULL DEFAULT 'unknown',
                    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'CLOSED_TP', 'CLOSED_SL', 'EXPIRED')),
                    pnl_percentage REAL,
                    close_timestamp DATETIME,
                    close_price REAL,
                    close_reason TEXT CHECK(close_reason IN ('TP', 'SL', 'EXPIRE', None)),
                    ai_raw_response TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 创建索引
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_trade_status ON trade_logs(status)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_trade_symbol ON trade_logs(symbol)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_trade_model ON trade_logs(ai_model)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_trade_timestamp ON trade_logs(timestamp)
            """)
            
            await db.commit()
            
            # 检查并添加新字段 (自动升级)
            await self._migrate_add_ai_model(db)
            
        print(f"✅ 数据库初始化完成: {self.db_path}")

    async def _migrate_add_ai_model(self, db: aiosqlite.Connection):
        """自动迁移：添加 ai_model 字段 (如果缺失)"""
        try:
            # 检查字段是否存在
            cursor = await db.execute("PRAGMA table_info(trade_logs)")
            columns = [row[1] for row in await cursor.fetchall()]
            
            if "ai_model" not in columns:
                print("🔄 数据库升级: 添加 ai_model 字段...")
                await db.execute("""
                    ALTER TABLE trade_logs ADD COLUMN ai_model TEXT DEFAULT 'unknown'
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_trade_model ON trade_logs(ai_model)
                """)
                await db.commit()
                print("✅ 数据库升级完成")
        except Exception as e:
            print(f"⚠️ 数据库迁移警告: {e}")

    # ============ 交易记录 CRUD ============

    async def create_trade(
        self,
        symbol: str,
        timeframe: str,
        direction: str,
        leverage: int,
        entry_price: float,
        tp_price: float,
        sl_price: float,
        ai_model: str,
        ai_raw_response: Optional[str] = None,
        timestamp: Optional[str] = None
    ) -> int:
        """
        创建新交易记录
        
        Returns:
            新记录 ID
        """
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        async with self._get_connection() as db:
            cursor = await db.execute("""
                INSERT INTO trade_logs (
                    timestamp, symbol, timeframe, direction, leverage,
                    entry_price, tp_price, sl_price, ai_model,
                    status, ai_raw_response
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
            """, (
                timestamp, symbol.upper(), timeframe, direction.upper(),
                leverage, entry_price, tp_price, sl_price,
                ai_model, ai_raw_response
            ))
            await db.commit()
            return cursor.lastrowid

    async def close_trade(
        self,
        trade_id: int,
        close_price: float,
        close_reason: str,
        pnl_percentage: float,
        close_timestamp: Optional[str] = None
    ) -> bool:
        """
        结算交易
        
        Args:
            trade_id: 交易ID
            close_price: 平仓价格
            close_reason: 结算原因 (TP/SL/EXPIRE)
            pnl_percentage: 收益率 (已乘杠杆)
            close_timestamp: 结算时间
        """
        if close_timestamp is None:
            close_timestamp = datetime.now().isoformat()
        
        status_map = {
            "TP": "CLOSED_TP",
            "SL": "CLOSED_SL",
            "EXPIRE": "EXPIRED"
        }
        status = status_map.get(close_reason.upper(), "CLOSED_TP")
        
        async with self._get_connection() as db:
            await db.execute("""
                UPDATE trade_logs SET
                    status = ?,
                    pnl_percentage = ?,
                    close_timestamp = ?,
                    close_price = ?,
                    close_reason = ?
                WHERE id = ?
            """, (status, pnl_percentage, close_timestamp, close_price, close_reason.upper(), trade_id))
            await db.commit()
            return True

    async def get_trade_by_id(self, trade_id: int) -> Optional[TradeLog]:
        """根据 ID 获取交易记录"""
        async with self._get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM trade_logs WHERE id = ?", (trade_id,)
            )
            row = await cursor.fetchone()
            if row:
                return self._row_to_trade_log(row)
            return None

    async def get_open_trades(
        self,
        symbol: Optional[str] = None,
        max_age_hours: int = 72
    ) -> List[TradeLog]:
        """
        获取所有未结算订单
        
        Args:
            symbol: 可选，过滤特定交易对
            max_age_hours: 最大持仓时间，超过则视为过期
        """
        cutoff_time = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
        
        async with self._get_connection() as db:
            if symbol:
                cursor = await db.execute("""
                    SELECT * FROM trade_logs 
                    WHERE status = 'OPEN' 
                    AND symbol = ?
                    AND timestamp > ?
                    ORDER BY timestamp DESC
                """, (symbol.upper(), cutoff_time))
            else:
                cursor = await db.execute("""
                    SELECT * FROM trade_logs 
                    WHERE status = 'OPEN' 
                    AND timestamp > ?
                    ORDER BY timestamp DESC
                """, (cutoff_time,))
            
            rows = await cursor.fetchall()
            return [self._row_to_trade_log(row) for row in rows]

    async def get_trade_history(
        self,
        symbol: Optional[str] = None,
        ai_model: Optional[str] = None,
        limit: int = 10,
        status: Optional[str] = None
    ) -> List[TradeLog]:
        """
        获取交易历史
        
        Args:
            symbol: 交易对过滤
            ai_model: 模型过滤
            limit: 返回数量限制
            status: 状态过滤 (OPEN/CLOSED_TP/CLOSED_SL/EXPIRED)
        """
        async with self._get_connection() as db:
            query = "SELECT * FROM trade_logs WHERE 1=1"
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol.upper())
            
            if ai_model:
                query += " AND ai_model = ?"
                params.append(ai_model)
            
            if status:
                query += " AND status = ?"
                params.append(status)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [self._row_to_trade_log(row) for row in rows]

    # ============ 统计查询 (Model Arena 核心) ============

    async def get_model_performance_stats(
        self,
        symbol: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, ModelStats]:
        """
        获取各模型的性能统计 (Model Arena 核心查询)
        
        Args:
            symbol: 可选，过滤特定交易对
            days: 统计最近 N 天的数据
        
        Returns:
            Dict[模型名, 统计数据]
        """
        cutoff_time = (datetime.now() - timedelta(days=days)).isoformat()
        
        async with self._get_connection() as db:
            # 基础查询条件
            base_where = "timestamp > ?"
            params = [cutoff_time]
            
            if symbol:
                base_where += " AND symbol = ?"
                params.append(symbol.upper())
            
            # 按模型分组统计
            cursor = await db.execute(f"""
                SELECT 
                    ai_model,
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status IN ('CLOSED_TP', 'CLOSED_SL', 'EXPIRED') THEN 1 ELSE 0 END) as closed_count,
                    SUM(CASE WHEN status = 'CLOSED_TP' THEN 1 ELSE 0 END) as win_count,
                    SUM(CASE WHEN status = 'CLOSED_SL' THEN 1 ELSE 0 END) as loss_count,
                    SUM(CASE WHEN pnl_percentage IS NOT NULL THEN pnl_percentage ELSE 0 END) as total_pnl,
                    AVG(CASE WHEN status IN ('CLOSED_TP', 'CLOSED_SL') THEN pnl_percentage END) as avg_pnl,
                    AVG(CASE WHEN status = 'CLOSED_TP' THEN pnl_percentage END) as avg_win,
                    AVG(CASE WHEN status = 'CLOSED_SL' THEN pnl_percentage END) as avg_loss
                FROM trade_logs
                WHERE {base_where}
                GROUP BY ai_model
                ORDER BY total_pnl DESC
            """, params)
            
            rows = await cursor.fetchall()
            
            result = {}
            for row in rows:
                model = row["ai_model"] or "unknown"
                closed = row["closed_count"] or 0
                wins = row["win_count"] or 0
                losses = row["loss_count"] or 0
                
                result[model] = ModelStats(
                    ai_model=model,
                    total_trades=row["total_trades"] or 0,
                    open_trades=row["open_count"] or 0,
                    closed_trades=closed,
                    win_count=wins,
                    loss_count=losses,
                    win_rate=(wins / closed * 100) if closed > 0 else 0,
                    total_pnl=row["total_pnl"] or 0,
                    avg_pnl=row["avg_pnl"] or 0,
                    avg_win=row["avg_win"] or 0,
                    avg_loss=row["avg_loss"] or 0
                )
            
            return result

    async def get_global_stats(
        self,
        symbol: Optional[str] = None,
        days: int = 30
    ) -> ModelStats:
        """获取全局统计 (所有模型汇总)"""
        cutoff_time = (datetime.now() - timedelta(days=days)).isoformat()
        
        async with self._get_connection() as db:
            base_where = "timestamp > ?"
            params = [cutoff_time]
            
            if symbol:
                base_where += " AND symbol = ?"
                params.append(symbol.upper())
            
            cursor = await db.execute(f"""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status IN ('CLOSED_TP', 'CLOSED_SL', 'EXPIRED') THEN 1 ELSE 0 END) as closed_count,
                    SUM(CASE WHEN status = 'CLOSED_TP' THEN 1 ELSE 0 END) as win_count,
                    SUM(CASE WHEN status = 'CLOSED_SL' THEN 1 ELSE 0 END) as loss_count,
                    SUM(CASE WHEN pnl_percentage IS NOT NULL THEN pnl_percentage ELSE 0 END) as total_pnl,
                    AVG(CASE WHEN status IN ('CLOSED_TP', 'CLOSED_SL') THEN pnl_percentage END) as avg_pnl
                FROM trade_logs
                WHERE {base_where}
            """, params)
            
            row = await cursor.fetchone()
            
            closed = row["closed_count"] or 0
            wins = row["win_count"] or 0
            losses = row["loss_count"] or 0
            
            return ModelStats(
                ai_model="ALL_MODELS",
                total_trades=row["total_trades"] or 0,
                open_trades=row["open_count"] or 0,
                closed_trades=closed,
                win_count=wins,
                loss_count=losses,
                win_rate=(wins / closed * 100) if closed > 0 else 0,
                total_pnl=row["total_pnl"] or 0,
                avg_pnl=row["avg_pnl"] or 0,
                avg_win=0,  # 全局不计算
                avg_loss=0
            )

    async def get_equity_curve_data(
        self,
        ai_model: Optional[str] = None,
        symbol: Optional[str] = None,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        获取权益曲线数据 (用于绘制资金曲线)
        
        Returns:
            List[{"timestamp": str, "cumulative_pnl": float}]
        """
        cutoff_time = (datetime.now() - timedelta(days=days)).isoformat()
        
        async with self._get_connection() as db:
            query = """
                SELECT close_timestamp, pnl_percentage
                FROM trade_logs
                WHERE status IN ('CLOSED_TP', 'CLOSED_SL')
                AND close_timestamp IS NOT NULL
                AND close_timestamp > ?
            """
            params = [cutoff_time]
            
            if ai_model:
                query += " AND ai_model = ?"
                params.append(ai_model)
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol.upper())
            
            query += " ORDER BY close_timestamp ASC"
            
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            
            # 计算累计盈亏
            curve = []
            cumulative = 0
            for row in rows:
                cumulative += row["pnl_percentage"] or 0
                curve.append({
                    "timestamp": row["close_timestamp"],
                    "cumulative_pnl": cumulative,
                    "trade_pnl": row["pnl_percentage"]
                })
            
            return curve

    async def expire_old_trades(self, max_age_hours: int = 72) -> int:
        """
        将超过最大持仓时间的订单标记为过期
        
        Returns:
            过期的订单数量
        """
        cutoff_time = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
        
        async with self._get_connection() as db:
            cursor = await db.execute("""
                UPDATE trade_logs SET
                    status = 'EXPIRED',
                    close_timestamp = ?,
                    close_reason = 'EXPIRE',
                    pnl_percentage = 0
                WHERE status = 'OPEN'
                AND timestamp < ?
            """, (datetime.now().isoformat(), cutoff_time))
            await db.commit()
            return cursor.rowcount

    # ============ 辅助方法 ============

    def _row_to_trade_log(self, row: sqlite3.Row) -> TradeLog:
        """将数据库行转换为 TradeLog 对象"""
        return TradeLog(
            id=row["id"],
            timestamp=row["timestamp"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            direction=row["direction"],
            leverage=row["leverage"],
            entry_price=row["entry_price"],
            tp_price=row["tp_price"],
            sl_price=row["sl_price"],
            ai_model=row.get("ai_model", "unknown"),
            status=row["status"],
            pnl_percentage=row["pnl_percentage"],
            close_timestamp=row["close_timestamp"],
            close_price=row["close_price"],
            close_reason=row["close_reason"],
            ai_raw_response=row["ai_raw_response"]
        )

    async def close(self):
        """关闭数据库连接 (通常不需要显式调用)"""
        pass  # aiosqlite 自动管理连接


# ============ 全局单例 ============

_db_service: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    """获取数据库服务单例"""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service
