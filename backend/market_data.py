import akshare as ak
import yfinance as yf
import aiohttp
import asyncio
import re
import json
from typing import Dict, Optional, List
from datetime import datetime
from backend.models import MarketData, AssetType, FundInfo
from loguru import logger

logger.add("./logs/market_data.log", encoding="utf-8")


class BaseBrokerAPI:
    """券商API基类"""

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        """获取股票价格"""
        pass

    async def get_fund_price(self, code: str) -> Optional[MarketData]:
        """获取基金价格"""
        pass

    async def get_fund_info(self, code: str) -> Optional[FundInfo]:
        """获取基金信息"""
        pass


class EastMoneyAPI(BaseBrokerAPI):
    """东方财富API实现"""

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        try:
            url = f"https://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": f"1.{code}" if code.startswith("6") else f"0.{code}",
                "fields": "f43,f44,f45,f46,f47,f48,f49,f14",
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.3650.96 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    data = await response.json()
                if data.get("data"):
                    tick = data["data"]
                    return MarketData(
                        code=code,
                        name=tick.get("f14", code),
                        price=float(tick.get("f43", 0)),
                        change=float(tick.get("f44", 0)),
                        change_percent=float(tick.get("f45", 0)),
                        volume=float(tick.get("f47", 0)),
                        timestamp=datetime.now(),
                    )
        except Exception as e:
            logger.error(f"EastMoney stock API error: {e}")
        return None

    async def get_fund_price(self, code: str) -> Optional[MarketData]:
        try:
            url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.3650.96 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    content = await response.text()
                nav_match = re.search(
                    r"var Data_netWorthTrend = \[(.*?)\];", content, re.DOTALL
                )
                if nav_match:
                    nav_data = json.loads("[" + nav_match.group(1) + "]")
                    if nav_data:
                        latest = nav_data[-1]
                        return MarketData(
                            code=code,
                            name=code,
                            price=float(latest.get("y", 0)),
                            change=0.0,
                            change_percent=0.0,
                            volume=0.0,
                            timestamp=datetime.now(),
                        )
        except Exception as e:
            logger.error(f"EastMoney fund price API error: {e}")
        return None

    async def get_fund_info(self, code: str) -> Optional[FundInfo]:
        try:
            url = f"https://fund.eastmoney.com/{code}.html"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.3650.96 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    logger.debug(f"Response: {await response.text()}")
                    if response.status == 404:
                        logger.warning(f"EastMoney API returned 404 for {url}")
                        return None
                    content = await response.text()
                name_match = re.search(
                    r'<div class="fundDetail-tit"><h4>(.*?)</h4>', content
                )
                type_match = re.search(r"基金类型：(.*?)<", content)
                nav_match = re.search(r"单位净值：(.*?)<", content)

                fund_name = name_match.group(1) if name_match else code
                fund_type = type_match.group(1) if type_match else "未知"
                nav = float(nav_match.group(1)) if nav_match else 0.0

                return FundInfo(
                    fund_code=code,
                    fund_name=fund_name,
                    fund_type=fund_type,
                    nav=nav,
                    establish_date=None,
                )
        except Exception as e:
            logger.error(f"EastMoney fund info API error: {e}")
        return None


class SinaAPI(BaseBrokerAPI):
    """新浪财经API实现"""

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        try:
            sina_code = f"sh{code}" if code.startswith("6") else f"sz{code}"
            url = f"https://hq.sinajs.cn/list={sina_code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.3650.96 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    content = await response.text()
                match = re.search(r'"(.*?)"', content)
                if match:
                    data = match.group(1).split(",")
                    if len(data) >= 4:
                        return MarketData(
                            code=code,
                            name=data[0],
                            price=float(data[3]),
                            change=float(data[3]) - float(data[2]),
                            change_percent=(float(data[3]) - float(data[2]))
                            / float(data[2])
                            * 100
                            if float(data[2]) > 0
                            else 0,
                            volume=float(data[8]),
                            timestamp=datetime.now(),
                        )
        except Exception as e:
            logger.error(f"Sina stock API error: {e}")
        return None

    async def get_fund_price(self, code: str) -> Optional[MarketData]:
        try:
            url = f"https://hq.sinajs.cn/list=ff_{code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.3650.96 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    content = await response.text()
                match = re.search(r'"(.*?)"', content)
                if match:
                    data = match.group(1).split(",")
                    if len(data) >= 4:
                        return MarketData(
                            code=code,
                            name=data[0],
                            price=float(data[1]),
                            change=float(data[1]) - float(data[2]),
                            change_percent=(float(data[1]) - float(data[2]))
                            / float(data[2])
                            * 100
                            if float(data[2]) > 0
                            else 0,
                            volume=float(data[5]),
                            timestamp=datetime.now(),
                        )
        except Exception as e:
            logger.error(f"Sina fund price API error: {e}")
        return None

    async def get_fund_info(self, code: str) -> Optional[FundInfo]:
        try:
            url = f"https://finance.sina.com.cn/fund/quotes/{code}/unit.shtml"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.3650.96 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    logger.debug(f"Response: {response}")
                    content = await response.text()
                name_match = re.search(r"<h1>(.*?)\(.*?\)</h1>", content)
                type_match = re.search(r"基金类型：(.*?)<", content)
                nav_match = re.search(r"单位净值：(.*?)<", content)

                fund_name = name_match.group(1) if name_match else code
                fund_type = type_match.group(1) if type_match else "未知"
                nav = float(nav_match.group(1)) if nav_match else 0.0

                return FundInfo(
                    fund_code=code,
                    fund_name=fund_name,
                    fund_type=fund_type,
                    nav=nav,
                    establish_date=None,
                )
        except Exception as e:
            logger.error(f"Sina fund info API error: {e}")
        return None


class QQAPI(BaseBrokerAPI):
    """腾讯财经API实现"""

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        try:
            qq_code = f"sh{code}" if code.startswith("6") else f"sz{code}"
            url = f"https://qt.gtimg.cn/q={qq_code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.3650.96 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    content = await response.text()
                match = re.search(r'"(.*?)"', content)
                if match:
                    data = match.group(1).split("~")
                    if len(data) >= 4:
                        return MarketData(
                            code=code,
                            name=data[1],
                            price=float(data[3]),
                            change=float(data[3]) - float(data[4]),
                            change_percent=(float(data[3]) - float(data[4]))
                            / float(data[4])
                            * 100
                            if float(data[4]) > 0
                            else 0,
                            volume=float(data[6]),
                            timestamp=datetime.now(),
                        )
        except Exception as e:
            logger.error(f"QQ stock API error: {e}")
        return None

    async def get_fund_price(self, code: str) -> Optional[MarketData]:
        try:
            url = f"https://fund.qq.com/data/getFundInfo?fundcode={code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.3650.96 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    data = await response.json()
                if data.get("data"):
                    fund_data = data["data"]
                    return MarketData(
                        code=code,
                        name=fund_data.get("fund_name", code),
                        price=float(fund_data.get("NAV", 0)),
                        change=float(fund_data.get("dayGrowth", 0)),
                        change_percent=float(fund_data.get("dayGrowth", 0)),
                        volume=0.0,
                        timestamp=datetime.now(),
                    )
        except Exception as e:
            logger.error(f"QQ fund price API error: {e}")
        return None

    async def get_fund_info(self, code: str) -> Optional[FundInfo]:
        try:
            url = f"https://fund.qq.com/data/getFundInfo?fundcode={code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.3650.96 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    logger.debug(f"Response: {response}")
                    data = await response.json()
                if data.get("data"):
                    fund_data = data["data"]
                    return FundInfo(
                        fund_code=code,
                        fund_name=fund_data.get("fund_name", code),
                        fund_type=fund_data.get("fundtype", "未知"),
                        nav=float(fund_data.get("NAV", 0)),
                        establish_date=fund_data.get("start_date", None),
                    )
        except Exception as e:
            logger.error(f"QQ fund info API error: {e}")
        return None


class HSBCAPI(BaseBrokerAPI):
    """汇丰API实现"""

    async def get_stock_price(self, code: str) -> Optional[MarketData]:

        return None

    async def get_fund_price(self, code: str) -> Optional[MarketData]:

        return None

    async def get_fund_info(self, code: str) -> Optional[FundInfo]:
        try:
            url = f"https://fund.hsbc.com.cn/data/getFundInfo?fundcode={code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.3650.96 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Connection": "keep-alive"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    logger.debug(f"Response: {response.status}")
                    data = await response.json()
                if data.get("data"):
                    fund_data = data["data"]
                    return FundInfo(
                        fund_code=code,
                        fund_name=fund_data.get("fund_name", code),
                        fund_type=fund_data.get("fundtype", "未知"),
                        nav=float(fund_data.get("NAV", 0)),
                        establish_date=fund_data.get("start_date", None),
                    )
        except Exception as e:
            logger.error(f"HSBC fund info API error: {e}")
        return None


class MarketDataService:
    """市场数据服务"""

    def __init__(self):
        self.cache: Dict[str, MarketData] = {}
        self.cache_timeout = 60
        self.brokers = self._init_brokers()

    def _init_brokers(self) -> List[BaseBrokerAPI]:
        """初始化券商API列表"""
        return [EastMoneyAPI(), SinaAPI(), QQAPI(), HSBCAPI()]

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        """获取股票价格"""
        try:
            # 尝试使用券商API
            for broker in self.brokers:
                try:
                    data = await broker.get_stock_price(code)
                    if data:
                        return data
                except Exception as e:
                    logger.error(f"Broker {broker.__class__.__name__} error: {e}")

            # fallback到yfinance
            if code.startswith("6"):
                symbol = f"{code}.SS"
            elif code.startswith("0") or code.startswith("3"):
                symbol = f"{code}.SZ"
            else:
                symbol = code

            ticker = yf.Ticker(symbol)
            info = ticker.history(period="1d", interval="1m")

            if info.empty:
                return None

            latest = info.iloc[-1]
            return MarketData(
                code=code,
                name=code,
                price=float(latest["Close"]),
                change=float(latest["Close"] - latest["Open"]),
                change_percent=float(
                    (latest["Close"] - latest["Open"]) / latest["Open"] * 100
                ),
                volume=float(latest["Volume"]),
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Error getting stock price for {code}: {e}")
            return None

    async def get_fund_price(self, code: str) -> Optional[MarketData]:
        """获取基金价格"""
        try:
            # 尝试使用券商API
            for broker in self.brokers:
                try:
                    data = await broker.get_fund_price(code)
                    if data:
                        return data
                except Exception as e:
                    logger.error(f"Broker {broker.__class__.__name__} error: {e}")

            # fallback到akshare
            fund_etf_hist_df = ak.fund_etf_hist_sina(symbol=code)
            if fund_etf_hist_df.empty:
                return None

            latest = fund_etf_hist_df.iloc[-1]
            return MarketData(
                code=code,
                name=code,
                price=float(latest["close"]),
                change=float(latest["close"] - latest["open"]),
                change_percent=float(
                    (latest["close"] - latest["open"]) / latest["open"] * 100
                ),
                volume=float(latest["volume"]),
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Error getting fund price for {code}: {e}")
            return None

    async def get_fund_info(self, fund_code: str) -> Optional[FundInfo]:
        """获取基金信息"""
        try:
            # 尝试使用券商API
            for broker in self.brokers:
                try:
                    info = await broker.get_fund_info(fund_code)
                    if info:
                        return info
                except Exception as e:
                    logger.error(f"Broker {broker.__class__.__name__} error: {e}")

            # fallback到akshare
            try:
                fund_info = ak.fund_open_fund_info(fund=fund_code, indicator="基本信息")
                if not fund_info.empty:
                    return FundInfo(
                        fund_code=fund_code,
                        fund_name=fund_info.get("基金名称", fund_code),
                        fund_type=fund_info.get("基金类型", "未知"),
                        nav=float(fund_info.get("单位净值", 0)),
                        establish_date=fund_info.get("成立日期", None),
                    )
            except Exception as e:
                logger.error(f"AkShare error: {e}")

            return None
        except Exception as e:
            logger.error(f"Error getting fund info for {fund_code}: {e}")
            return None

    async def get_index_price(self, code: str) -> Optional[MarketData]:
        """获取指数价格"""
        try:
            index_stock_hist_df = ak.index_stock_hist(symbol=code, period="daily")
            if index_stock_hist_df.empty:
                return None

            latest = index_stock_hist_df.iloc[-1]
            return MarketData(
                code=code,
                name=code,
                price=float(latest["收盘"]),
                change=float(latest["收盘"] - latest["开盘"]),
                change_percent=float(
                    (latest["收盘"] - latest["开盘"]) / latest["开盘"] * 100
                ),
                volume=float(latest["成交量"]),
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Error getting index price for {code}: {e}")
            return None

    async def get_market_data(
        self, code: str, asset_type: AssetType
    ) -> Optional[MarketData]:
        """获取市场数据"""
        # 检查缓存
        cache_key = f"{asset_type.value}:{code}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        data = None
        if asset_type == AssetType.STOCK:
            data = await self.get_stock_price(code)
        elif asset_type == AssetType.FUND:
            data = await self.get_fund_price(code)
        elif asset_type == AssetType.INDEX:
            data = await self.get_index_price(code)

        if data:
            self.cache[cache_key] = data

        return data

    async def get_batch_market_data(self, items: List[tuple]) -> Dict[str, MarketData]:
        """批量获取市场数据"""
        tasks = []
        for code, asset_type in items:
            tasks.append(self.get_market_data(code, asset_type))

        results = await asyncio.gather(*tasks)
        return {
            item[0]: result
            for item, result in zip(items, results)
            if result is not None
        }

    def clear_cache(self):
        """清除缓存"""
        self.cache.clear()


market_data_service = MarketDataService()


async def get_fund_info(fund_code: str) -> Optional[FundInfo]:
    """获取基金信息的外部接口"""
    try:
        result = await market_data_service.get_fund_info(fund_code)
        if result:
            return result
        # 如果所有API都失败，返回一个基本的FundInfo对象
        return FundInfo(
            fund_code=fund_code,
            fund_name=f"基金{fund_code}",
            fund_type="未知",
            nav=0.0,
            establish_date=None,
        )
    except Exception as e:
        logger.error(f"Error in get_fund_info: {e}")
        return FundInfo(
            fund_code=fund_code,
            fund_name=f"基金{fund_code}",
            fund_type="未知",
            nav=0.0,
            establish_date=None,
        )
