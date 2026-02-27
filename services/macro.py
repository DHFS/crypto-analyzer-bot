"""宏观经济与市场情绪数据服务

提供加密货币市场宏观数据，包括恐慌贪婪指数、市场新闻等
"""
import asyncio
from typing import Optional, List, Dict
from dataclasses import dataclass
from datetime import datetime
import aiohttp


@dataclass
class FearGreedData:
    """恐慌贪婪指数数据结构"""
    value: int  # 指数值 0-100
    classification: str  # 分类: Extreme Fear, Fear, Neutral, Greed, Extreme Greed
    timestamp: datetime
    
    @property
    def classification_cn(self) -> str:
        """中文分类"""
        mapping = {
            "Extreme Fear": "极度恐慌",
            "Fear": "恐慌",
            "Neutral": "中性",
            "Greed": "贪婪",
            "Extreme Greed": "极度贪婪"
        }
        return mapping.get(self.classification, self.classification)
    
    @property
    def emoji(self) -> str:
        """情绪表情"""
        if self.value <= 20:
            return "😱"
        elif self.value <= 40:
            return "😨"
        elif self.value <= 60:
            return "😐"
        elif self.value <= 80:
            return "😏"
        else:
            return "🤑"


@dataclass
class CryptoNews:
    """加密货币新闻数据结构"""
    title: str
    source: str
    url: str
    published_at: datetime
    sentiment: str  # positive, negative, neutral


class MacroService:
    """宏观经济数据服务"""
    
    # API 端点
    FEAR_GREED_API = "https://api.alternative.me/fng/"
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP Session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "CryptoAnalyzerBot/1.0"
                }
            )
        return self._session
    
    async def close(self):
        """关闭 HTTP Session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def get_fear_greed_index(self, limit: int = 1) -> List[FearGreedData]:
        """
        获取加密货币恐慌贪婪指数
        
        Args:
            limit: 获取历史数据条数 (1-365)，默认1条（最新）
            
        Returns:
            List[FearGreedData]: 恐慌贪婪指数数据列表
            
        Raises:
            Exception: API 请求失败时抛出异常
            
        指数解读:
            0-24: 极度恐慌 (Extreme Fear) - 可能是买入机会
            25-49: 恐慌 (Fear) - 市场情绪低迷
            50: 中性 (Neutral)
            51-75: 贪婪 (Greed) - 市场情绪高涨
            76-100: 极度贪婪 (Extreme Greed) - 可能是卖出信号
        """
        session = await self._get_session()
        
        params = {
            "limit": min(max(limit, 1), 365),  # 限制范围 1-365
            "format": "json"
        }
        
        try:
            async with session.get(self.FEAR_GREED_API, params=params) as response:
                if response.status != 200:
                    raise Exception(f"API 请求失败: HTTP {response.status}")
                
                data = await response.json()
                
                if "data" not in data:
                    raise Exception("API 返回数据格式异常")
                
                results = []
                for item in data["data"]:
                    fg_data = FearGreedData(
                        value=int(item["value"]),
                        classification=item["value_classification"],
                        timestamp=datetime.fromtimestamp(int(item["timestamp"]))
                    )
                    results.append(fg_data)
                
                return results
                
        except aiohttp.ClientError as e:
            raise Exception(f"网络请求异常: {str(e)}")
        except asyncio.TimeoutError:
            raise Exception("请求超时，请稍后重试")
        except Exception as e:
            raise Exception(f"获取恐慌贪婪指数失败: {str(e)}")
    
    async def get_fear_greed_summary(self) -> Dict:
        """
        获取恐慌贪婪指数摘要（包含趋势分析）
        
        Returns:
            Dict: {
                "current": FearGreedData,  # 当前指数
                "history": List[FearGreedData],  # 近7天历史
                "trend": str,  # 趋势: rising, falling, stable
                "analysis": str  # 简短分析
            }
        """
        # 获取当前和近7天历史数据
        history = await self.get_fear_greed_index(limit=7)
        
        if not history:
            raise Exception("无法获取恐慌贪婪指数数据")
        
        current = history[0]
        
        # 计算趋势
        if len(history) >= 2:
            prev_value = history[1].value
            diff = current.value - prev_value
            
            if abs(diff) <= 3:
                trend = "stable"
                trend_cn = "平稳"
            elif diff > 0:
                trend = "rising"
                trend_cn = "上升"
            else:
                trend = "falling"
                trend_cn = "下降"
        else:
            trend = "unknown"
            trend_cn = "未知"
        
        # 生成分析
        analysis = self._generate_fear_greed_analysis(current, trend)
        
        return {
            "current": current,
            "history": history,
            "trend": trend,
            "trend_cn": trend_cn,
            "analysis": analysis
        }
    
    def _generate_fear_greed_analysis(self, data: FearGreedData, trend: str) -> str:
        """生成恐慌贪婪指数分析文本"""
        value = data.value
        classification = data.classification_cn
        
        if value <= 20:
            return f"市场处于{classification}状态({value})，投资者过度悲观，可能是逢低布局的机会"
        elif value <= 40:
            return f"市场呈现{classification}情绪({value})，情绪偏冷，建议谨慎操作"
        elif value <= 60:
            return f"市场情绪{classification}({value})，多空力量相对平衡"
        elif value <= 80:
            return f"市场处于{classification}状态({value})，情绪高涨，注意回调风险"
        else:
            return f"市场呈现{classification}({value})，投资者过度乐观，需警惕顶部风险"
    
    async def get_recent_crypto_news(
        self, 
        currencies: Optional[List[str]] = None,
        limit: int = 5
    ) -> List[CryptoNews]:
        """
        获取最近加密货币新闻 (预留接口)
        
        当前返回 Mock 数据，未来可接入：
        - CryptoPanic API (https://cryptopanic.com/developers/api/)
        - NewsAPI
        - CoinDesk RSS
        
        Args:
            currencies: 关注的币种列表，如 ["BTC", "ETH"]
            limit: 返回新闻条数
            
        Returns:
            List[CryptoNews]: 新闻列表
        """
        # TODO: 接入真实新闻 API
        # 当前返回基于市场状态的 Mock 数据
        
        mock_news = [
            CryptoNews(
                title="比特币ETF资金流入创新高，机构持续增持",
                source="CoinDesk",
                url="https://coindesk.com",
                published_at=datetime.now(),
                sentiment="positive"
            ),
            CryptoNews(
                title="美联储会议纪要暗示加息周期接近尾声",
                source="Bloomberg",
                url="https://bloomberg.com",
                published_at=datetime.now(),
                sentiment="positive"
            ),
            CryptoNews(
                title="以太坊Layer2生态TVL突破历史新高",
                source="DeFiLlama",
                url="https://defillama.com",
                published_at=datetime.now(),
                sentiment="positive"
            ),
            CryptoNews(
                title="监管机构加强对稳定币的审查力度",
                source="Reuters",
                url="https://reuters.com",
                published_at=datetime.now(),
                sentiment="negative"
            ),
            CryptoNews(
                title="主要交易所宣布降低合约交易手续费",
                source="The Block",
                url="https://theblock.co",
                published_at=datetime.now(),
                sentiment="neutral"
            )
        ]
        
        return mock_news[:limit]
    
    async def get_macro_summary(self) -> Dict:
        """
        获取完整宏观数据摘要
        
        Returns:
            Dict: 包含恐慌贪婪指数、市场新闻等宏观数据
        """
        fg_task = self.get_fear_greed_summary()
        news_task = self.get_recent_crypto_news(limit=3)
        
        fg_data, news_data = await asyncio.gather(
            fg_task, 
            news_task,
            return_exceptions=True
        )
        
        # 处理异常
        if isinstance(fg_data, Exception):
            raise fg_data
        
        return {
            "fear_greed": fg_data,
            "news": news_data if not isinstance(news_data, Exception) else [],
            "timestamp": datetime.now()
        }


# 便捷函数：快速获取恐慌贪婪指数
async def get_fear_greed() -> FearGreedData:
    """快速获取当前恐慌贪婪指数"""
    service = MacroService()
    try:
        data = await service.get_fear_greed_index(limit=1)
        return data[0] if data else None
    finally:
        await service.close()


if __name__ == "__main__":
    # 测试代码
    async def test():
        service = MacroService()
        try:
            # 测试恐慌贪婪指数
            print("=" * 50)
            print("恐慌贪婪指数测试")
            print("=" * 50)
            
            summary = await service.get_fear_greed_summary()
            current = summary["current"]
            
            print(f"当前指数: {current.value} {current.emoji}")
            print(f"分类: {current.classification} ({current.classification_cn})")
            print(f"趋势: {summary['trend_cn']}")
            print(f"分析: {summary['analysis']}")
            print()
            print("近7天历史:")
            for fg in summary["history"]:
                print(f"  {fg.timestamp.strftime('%m-%d')}: {fg.value} ({fg.classification_cn})")
            
            # 测试新闻
            print()
            print("=" * 50)
            print("新闻测试")
            print("=" * 50)
            
            news_list = await service.get_recent_crypto_news(limit=3)
            for news in news_list:
                print(f"[{news.sentiment}] {news.title}")
                print(f"  来源: {news.source}")
                print()
                
        finally:
            await service.close()
    
    asyncio.run(test())
