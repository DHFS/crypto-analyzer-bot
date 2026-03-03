"""Binance 合约数据获取服务 - 支持异步操作与资金面数据"""
import os
import asyncio
from typing import Optional
import pandas as pd
import aiohttp
from config import config


class BinanceService:
    """Binance 合约市场数据服务 - 异步版本"""

    BASE_URL = "https://fapi.binance.com"
    
    # 时间周期映射
    TIMEFRAME_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }

    # 多时间周期共振配置
    MULTI_TIMEFRAME_CONFIG = {
        "15m": ["5m", "15m", "1h"],
        "30m": ["15m", "30m", "1h"],
        "1h": ["15m", "1h", "4h"],
        "4h": ["1h", "4h", "1d"],
        "1d": ["4h", "1d", "1d"],
    }

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self._request_semaphore = asyncio.Semaphore(5)
        self._proxy = config.HTTP_PROXY if config.HTTP_PROXY else None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP Session"""
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            timeout = aiohttp.ClientTimeout(total=30)
            
            # 创建 session，使用代理
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    "User-Agent": "CryptoAnalyzerBot/1.0",
                    "Accept": "application/json"
                }
            )
        return self.session

    async def close(self):
        """关闭 Session"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def _request(self, endpoint: str, params: dict = None) -> dict:
        """发送 HTTP 请求"""
        session = await self._get_session()
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            async with self._request_semaphore:
                async with session.get(url, params=params, proxy=self._proxy) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise Exception(f"API 错误 {response.status}: {text}")
                    return await response.json()
        except aiohttp.ClientError as e:
            raise Exception(f"网络请求异常: {str(e)}")

    def _normalize_symbol(self, symbol: str) -> str:
        """标准化交易对格式"""
        return symbol.replace("/", "").upper()

    async def get_klines(
        self, 
        symbol: str, 
        timeframe: str, 
        limit: int = 100
    ) -> pd.DataFrame:
        """获取合约K线数据"""
        interval = self.TIMEFRAME_MAP.get(timeframe)
        if not interval:
            raise ValueError(f"不支持的时间周期: {timeframe}")

        symbol = self._normalize_symbol(symbol)

        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }

        data = await self._request("/fapi/v1/klines", params)

        # 转换为DataFrame
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ])

        # 数据类型转换
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        return df[["timestamp", "open", "high", "low", "close", "volume"]]

    async def get_ticker(self, symbol: str) -> dict:
        """获取最新价格和24h统计"""
        symbol = self._normalize_symbol(symbol)
        data = await self._request("/fapi/v1/ticker/24hr", {"symbol": symbol})

        return {
            "symbol": data["symbol"],
            "price": float(data["lastPrice"]),
            "price_change": float(data["priceChange"]),
            "price_change_percent": float(data["priceChangePercent"]),
            "high_24h": float(data["highPrice"]),
            "low_24h": float(data["lowPrice"]),
            "volume_24h": float(data["volume"]),
            "quote_volume_24h": float(data["quoteVolume"]),
        }

    async def get_open_interest(self, symbol: str) -> dict:
        """获取未平仓合约量"""
        symbol = self._normalize_symbol(symbol)
        data = await self._request("/fapi/v1/openInterest", {"symbol": symbol})
        
        ticker = await self.get_ticker(symbol)
        oi_amount = float(data["openInterest"])
        
        return {
            "symbol": symbol,
            "open_interest": oi_amount,
            "open_interest_usdt": oi_amount * ticker["price"],
            "timestamp": pd.to_datetime(data["time"], unit="ms"),
        }

    async def get_funding_rate(self, symbol: str) -> dict:
        """获取资金费率"""
        symbol = self._normalize_symbol(symbol)
        data = await self._request("/fapi/v1/premiumIndex", {"symbol": symbol})

        return {
            "symbol": symbol,
            "funding_rate": float(data["lastFundingRate"]) * 100,
            "next_funding_time": pd.to_datetime(data["nextFundingTime"], unit="ms"),
            "mark_price": float(data["markPrice"]),
            "index_price": float(data["indexPrice"]),
            "estimated_rate": float(data.get("estimatedSettlePrice", 0)),
        }

    async def get_long_short_ratio(self, symbol: str, period: str = "15m") -> dict:
        """获取多空持仓人数比"""
        symbol = self._normalize_symbol(symbol)
        valid_periods = ["5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"]
        
        if period not in valid_periods:
            raise ValueError(f"不支持的统计周期: {period}")

        params = {
            "symbol": symbol,
            "period": period,
            "limit": 1
        }
        
        data = await self._request("/futures/data/topLongShortAccountRatio", params)
        
        if not data:
            raise Exception(f"未获取到 {symbol} 的多空比数据")

        latest = data[0]
        long_ratio = float(latest["longAccount"])
        short_ratio = float(latest["shortAccount"])

        return {
            "symbol": symbol,
            "period": period,
            "long_short_ratio": long_ratio / short_ratio if short_ratio > 0 else 0,
            "long_account": long_ratio * 100,
            "short_account": short_ratio * 100,
            "timestamp": pd.to_datetime(latest["timestamp"], unit="ms"),
        }

    async def get_multi_timeframe_data(self, symbol: str, primary_timeframe: str) -> dict:
        """获取多时间周期数据"""
        symbol = self._normalize_symbol(symbol)
        timeframes = self.MULTI_TIMEFRAME_CONFIG.get(
            primary_timeframe, 
            [primary_timeframe, primary_timeframe, primary_timeframe]
        )
        
        small_tf, primary_tf, large_tf = timeframes

        results = await asyncio.gather(
            self.get_klines(symbol, small_tf, limit=100),
            self.get_klines(symbol, primary_tf, limit=100),
            self.get_klines(symbol, large_tf, limit=100),
            self.get_ticker(symbol),
            return_exceptions=True
        )

        for result in results:
            if isinstance(result, Exception):
                raise result

        return {
            "symbol": symbol,
            "primary": primary_timeframe,
            "timeframes": {
                "small": {"name": small_tf, "description": "入场/出场精准点位", "klines": results[0]},
                "primary": {"name": primary_tf, "description": "主交易周期", "klines": results[1]},
                "large": {"name": large_tf, "description": "大趋势判断", "klines": results[2]},
            },
            "ticker": results[3]
        }

    async def get_leverage_brackets(self, symbol: str) -> list:
        """获取交易对杠杆分层数据 (用于精确计算爆仓价)"""
        symbol = self._normalize_symbol(symbol)
        
        try:
            data = await self._request("/fapi/v1/leverageBracket", {"symbol": symbol})
            if data and len(data) > 0:
                brackets = data[0].get("brackets", [])
                # 提取有用的信息
                result = []
                for bracket in brackets:
                    result.append({
                        "bracket": bracket.get("bracket"),
                        "initial_leverage": bracket.get("initialLeverage"),
                        "notional_cap": bracket.get("notionalCap"),
                        "notional_floor": bracket.get("notionalFloor"),
                        "maint_margin_ratio": bracket.get("maintMarginRatio"),
                        "cum": bracket.get("cum"),
                    })
                return result
            return []
        except Exception:
            # 如果 API 调用失败，返回默认值
            return [{
                "initial_leverage": 125,
                "maint_margin_ratio": 0.004,
                "notional_cap": 50000,
            }]

    def get_maintenance_margin_rate(self, leverage_brackets: list, position_value: float) -> float:
        """根据仓位价值获取维持保证金率"""
        if not leverage_brackets:
            return 0.004  # 默认 0.4%
        
        for bracket in leverage_brackets:
            notional_cap = bracket.get("notionalCap", float('inf'))
            notional_floor = bracket.get("notionalFloor", 0)
            if notional_floor <= position_value <= notional_cap:
                return bracket.get("maint_margin_ratio", 0.004)
        
        # 如果超过最高档位，返回最后一档的维持保证金率
        return leverage_brackets[-1].get("maint_margin_ratio", 0.5) if leverage_brackets else 0.004

    async def get_full_market_data(self, symbol: str, timeframe: str) -> dict:
        """获取完整的市场数据"""
        results = await asyncio.gather(
            self.get_multi_timeframe_data(symbol, timeframe),
            self.get_funding_rate(symbol),
            self.get_open_interest(symbol),
            self.get_long_short_ratio(symbol, period="15m"),
            self.get_leverage_brackets(symbol),
            return_exceptions=True
        )

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # 杠杆分层数据获取失败不影响其他数据
                if i == 4:
                    results[i] = []
                else:
                    raise result

        return {
            **results[0],
            "funding_rate": results[1],
            "open_interest": results[2],
            "long_short_ratio": results[3],
            "leverage_brackets": results[4],
        }
