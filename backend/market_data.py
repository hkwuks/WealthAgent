import asyncio
import aiohttp
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from loguru import logger
import akshare as ak
import yfinance as yf

from backend.models import (
    MarketData,
    FundInfo,
    Holding,
    MarketType,
    AssetType,
)

logger.add("./logs/market_data.log", encoding="utf-8")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}

INDEX_MAPPING = {
    "000001": {"name": "上证指数", "code": "sh000001"},
    "000016": {"name": "上证50", "code": "sh000016"},
    "000300": {"name": "沪深300", "code": "sh000300"},
    "000905": {"name": "中证500", "code": "sh000905"},
    "000852": {"name": "中证1000", "code": "sh000852"},
    "399001": {"name": "深证成指", "code": "sz399001"},
    "399006": {"name": "创业板指", "code": "sz399006"},
    "399673": {"name": "创业板50", "code": "sz399673"},
    "000688": {"name": "科创50", "code": "sh000688"},
    "399005": {"name": "中小板指", "code": "sz399005"},
    "931079": {"name": "国证2000", "code": "sz399303"},
    "399303": {"name": "国证2000", "code": "sz399303"},
    "399997": {"name": "中证白酒", "code": "sz399997"},
    "399808": {"name": "中证新能源", "code": "sz399808"},
    "399967": {"name": "中证军工", "code": "sz399967"},
    "399986": {"name": "中证银行", "code": "sz399986"},
    "399975": {"name": "中证证券", "code": "sz399975"},
    "000932": {"name": "中证消费", "code": "sh000932"},
    "000933": {"name": "中证医药", "code": "sh000933"},
    "000922": {"name": "中证红利", "code": "sh000922"},
}

GLOBAL_INDEX_MAPPING = {
    "nasdaq": {"name": "纳斯达克指数", "code": "NDX", "secid": "100.NDX", "sina": "gb_$nasdaq", "qq": "us.IXIC"},
    "nasdaq100": {"name": "纳斯达克100", "code": "NDX", "secid": "100.NDX", "sina": "gb_$nasdaq", "qq": "us.IXIC"},
    "sp500": {"name": "标普500", "code": "SPX", "secid": "100.SPX", "sina": "gb_$spx", "qq": "us.INX"},
    "dowjones": {"name": "道琼斯", "code": "DJI", "secid": "100.DJIA", "sina": "gb_$dji", "qq": "us.DJI"},
    "dji": {"name": "道琼斯", "code": "DJI", "secid": "100.DJIA", "sina": "gb_$dji", "qq": "us.DJI"},
    "hsi": {"name": "恒生指数", "code": "HSI", "secid": "100.HSI", "sina": "hkHSI", "qq": "hkHSI"},
    "hangseng": {"name": "恒生指数", "code": "HSI", "secid": "100.HSI", "sina": "hkHSI", "qq": "hkHSI"},
    "nikkei": {"name": "日经225", "code": "N225", "secid": "100.N225", "sina": "gb_$n225", "qq": "us.N225"},
    "n225": {"name": "日经225", "code": "N225", "secid": "100.N225", "sina": "gb_$n225", "qq": "us.N225"},
}

_session: Optional[aiohttp.ClientSession] = None

async def get_session() -> aiohttp.ClientSession:
    """获取共享的 aiohttp session"""
    global _session
    if _session is None or _session.closed:
        connector = aiohttp.TCPConnector(limit=20, limit_per_host=5, ttl_dns_cache=300)
        timeout = aiohttp.ClientTimeout(total=15.0, connect=5.0)
        _session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    return _session

async def close_session():
    """关闭共享的 aiohttp session"""
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


def determine_market_type(fund_code: str, fund_name: str = "", fund_type: str = "") -> MarketType:
    """
    判断基金是场内基金还是场外基金
    
    判断规则：
    1. 场内基金代码特征：
       - 上海交易所ETF：510xxx, 511xxx, 512xxx, 513xxx, 515xxx, 516xxx, 517xxx, 518xxx
       - 深圳交易所：15xxxx, 16xxxx, 18xxxx
    2. 场外基金代码特征：
       - 一般以 0 开头，前两位为 TA 编码
       - 519xxx 是上海场外基金
    3. 基金名称特征：
       - 包含 ETF、LOF、封闭式 的通常是场内基金
       - 包含 联接 的通常是场外基金
    
    Args:
        fund_code: 基金代码
        fund_name: 基金名称（可选，用于辅助判断）
        fund_type: 基金类型（可选，用于辅助判断）
    
    Returns:
        MarketType: 市场类型枚举值
    """
    if not fund_code:
        return MarketType.UNKNOWN
    
    code_prefix = fund_code[:2]
    code_prefix3 = fund_code[:3] if len(fund_code) >= 3 else ""
    
    if fund_name:
        name_upper = fund_name.upper()
        if "联接" in fund_name:
            return MarketType.OFF_EXCHANGE
        if any(kw in name_upper for kw in ["ETF", "LOF", "封闭式"]):
            return MarketType.ON_EXCHANGE
        
    if fund_type:
        type_upper = fund_type.upper()
        if "联接" in fund_type:
            return MarketType.OFF_EXCHANGE
        if any(kw in type_upper for kw in ["ETF", "LOF", "封闭式"]):
            return MarketType.ON_EXCHANGE
    
    if code_prefix in ("15", "16", "18"):
        return MarketType.ON_EXCHANGE
    
    if code_prefix == "51":
        if code_prefix3 in ("510", "511", "512", "513", "515", "516", "517", "518"):
            return MarketType.ON_EXCHANGE
        else:
            return MarketType.OFF_EXCHANGE
    
    if code_prefix == "50":
        return MarketType.ON_EXCHANGE
    
    if code_prefix == "52":
        return MarketType.ON_EXCHANGE
    
    if fund_code.startswith("0"):
        return MarketType.OFF_EXCHANGE
    
    return MarketType.UNKNOWN


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

    async def get_fund_holdings(self, fund_code: str) -> List[Holding]:
        """获取基金持仓"""
        return []

    async def get_index_price(self, code: str) -> Optional[MarketData]:
        """获取指数价格"""
        pass

    async def get_etf_realtime_data(self, code: str) -> Optional[Dict[str, Any]]:
        """获取ETF实时数据"""
        return None


class EastMoneyAPI(BaseBrokerAPI):
    """东方财富API实现"""

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        try:
            is_hk = len(code) == 5 and code.isdigit()
            is_us = code.isalpha() and code.isupper() and len(code) <= 5
            
            if is_us:
                secid = f"107.{code}"
            elif is_hk:
                secid = f"116.{code}"
            elif code.startswith("6"):
                secid = f"1.{code}"
            else:
                secid = f"0.{code}"
            
            url = "https://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": secid,
                "fields": "f43,f44,f45,f46,f47,f48,f49,f14,f169,f170",
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    data = await response.json()
                if data.get("data"):
                    tick = data["data"]
                    price_divisor = 1000 if is_hk else 100
                    price = float(tick.get("f43", 0)) / price_divisor
                    change = float(tick.get("f169", 0)) / 100
                    change_percent = float(tick.get("f170", 0)) / 100
                    
                    return MarketData(
                        code=code,
                        name=tick.get("f14", code) or code,
                        price=price,
                        change=change,
                        change_percent=change_percent,
                        volume=float(tick.get("f47", 0)),
                        timestamp=datetime.now(),
                    )
        except Exception as e:
            logger.error(f"EastMoney stock API error for {code}: {e}")
        return None

    async def get_fund_price(self, code: str) -> Optional[MarketData]:
        try:
            url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    content = await response.text()
                nav_match = re.search(r"var Data_netWorthTrend = \[(.*?)\];", content, re.DOTALL)
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

    async def _get_fund_detail_info(self, code: str) -> Dict[str, Optional[str]]:
        result: Dict[str, Optional[str]] = {"benchmark": None, "tracking_index": None}
        try:
            url = f"https://fundf10.eastmoney.com/jbgk_{code}.html"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    if response.status != 200:
                        return result
                    content = await response.text()
                
                benchmark_match = re.search(r'业绩比较基准.*?<td[^>]*>(.*?)</td>', content, re.DOTALL)
                if benchmark_match:
                    result["benchmark"] = benchmark_match.group(1).strip()
                
                tracking_match = re.search(r'跟踪标的.*?<td[^>]*>(.*?)</td>', content, re.DOTALL)
                if tracking_match:
                    result["tracking_index"] = tracking_match.group(1).strip()
                    
        except Exception as e:
            logger.error(f"EastMoney fund detail API error: {e}")
        return result

    async def get_fund_info(self, code: str) -> Optional[FundInfo]:
        try:
            url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    if response.status == 404:
                        return None
                    content = await response.text()
                    
                name_match = re.search(r'var fS_name = "([^"]+)";', content)
                type_match = re.search(r'var fS_type = "([^"]+)";', content)
                nav_match = re.search(r'var Data_netWorthTrend = \[(.*?)\];', content, re.DOTALL)
                
                fund_name = name_match.group(1) if name_match else code
                fund_type = type_match.group(1) if type_match else "未知"
                
                nav = None
                if nav_match:
                    try:
                        nav_data = json.loads("[" + nav_match.group(1) + "]")
                        if nav_data:
                            latest = nav_data[-1]
                            nav = float(latest.get("y", 0))
                    except Exception:
                        pass

                market_type = determine_market_type(code, fund_name, fund_type)
                detail_info = await self._get_fund_detail_info(code)

                return FundInfo(
                    fund_code=code,
                    fund_name=fund_name,
                    fund_type=fund_type,
                    nav=nav,
                    establish_date=None,
                    market_type=market_type,
                    benchmark=detail_info.get("benchmark"),
                    tracking_index=detail_info.get("tracking_index"),
                )
        except Exception as e:
            logger.error(f"EastMoney fund info API error: {e}")
        return None

    async def get_fund_holdings(self, fund_code: str) -> List[Holding]:
        try:
            df = await asyncio.to_thread(ak.fund_portfolio_hold_em, symbol=fund_code)
            
            if df.empty:
                logger.warning(f"No holdings data for fund {fund_code}")
                return []
            
            holdings = []
            for _, row in df.iterrows():
                try:
                    weight_str = str(row.get('占净值比例', '0'))
                    weight = float(weight_str.replace('%', '')) if '%' in weight_str else float(weight_str)
                    
                    holding = Holding(
                        asset_code=str(row.get('股票代码', '')),
                        asset_name=str(row.get('股票名称', '')),
                        asset_type=AssetType.STOCK,
                        quantity=float(row.get('持股数', 0)) if row.get('持股数') else 0,
                        market_value=float(row.get('持仓市值', 0)) if row.get('持仓市值') else 0,
                        weight=weight,
                        price=float(row.get('最新价', 0)) if row.get('最新价') else 0,
                    )
                    holdings.append(holding)
                except Exception as e:
                    logger.warning(f"Error parsing holding row: {e}")
                    continue
            
            logger.info(f"Got {len(holdings)} holdings for fund {fund_code}")
            return holdings
            
        except Exception as e:
            logger.error(f"Error getting fund holdings for {fund_code}: {e}")
            return []

    async def get_index_price(self, code: str) -> Optional[MarketData]:
        try:
            df = await asyncio.to_thread(ak.index_zh_a_hist, symbol=code, period="daily", start_date="20200101", end_date="20991231")
            if df.empty:
                return None

            latest = df.iloc[-1]
            return MarketData(
                code=code,
                name=code,
                price=float(latest["收盘"]),
                change=float(latest["收盘"] - latest["开盘"]),
                change_percent=float((latest["收盘"] - latest["开盘"]) / latest["开盘"] * 100) if latest["开盘"] > 0 else 0,
                volume=float(latest["成交量"]),
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"EastMoney index price API error: {e}")
        return None

    async def get_etf_realtime_data(self, code: str) -> Optional[Dict[str, Any]]:
        try:
            df = await asyncio.to_thread(ak.fund_etf_spot_em)
            etf_info = df[df['代码'] == code]
            
            if not etf_info.empty:
                row = etf_info.iloc[0]
                return {
                    "code": code,
                    "name": row.get('名称', ''),
                    "price": float(row.get('最新价', 0)),
                    "change_percent": float(row.get('涨跌幅', 0)),
                    "previous_close": float(row.get('昨收', 0)),
                    "volume": float(row.get('成交量', 0)),
                    "amount": float(row.get('成交额', 0)),
                }
        except Exception as e:
            logger.error(f"EastMoney ETF realtime API error: {e}")
        return None


class SinaAPI(BaseBrokerAPI):
    """新浪财经API实现
    
    支持功能:
    - 股票实时行情 (A股、港股)
    - 基金净值
    - 指数行情
    """

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        try:
            is_hk = len(code) == 5 and code.isdigit()
            is_us = code.isalpha() and code.isupper() and len(code) <= 5
            
            if is_us:
                sina_code = f"gb_{code}"
            elif is_hk:
                sina_code = f"hk{code}"
            elif code.startswith("6"):
                sina_code = f"sh{code}"
            else:
                sina_code = f"sz{code}"
            
            url = f"https://hq.sinajs.cn/list={sina_code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://finance.sina.com.cn/",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    content = await response.text()
                match = re.search(r'"(.*?)"', content)
                if match:
                    data = match.group(1).split(",")
                    if is_us:
                        if len(data) >= 9:
                            name = data[0]
                            current_price = float(data[1]) if data[1] else 0
                            change = float(data[2]) if data[2] else 0
                            change_percent = float(data[3]) if data[3] else 0
                            
                            return MarketData(
                                code=code,
                                name=name,
                                price=current_price,
                                change=change,
                                change_percent=change_percent,
                                volume=0.0,
                                timestamp=datetime.now(),
                            )
                    elif is_hk:
                        if len(data) >= 10:
                            name = data[1]
                            current_price = float(data[6]) if data[6] and data[6] != name else 0
                            pre_close = float(data[3]) if data[3] else 0
                            volume = float(data[12]) if len(data) > 12 and data[12] else 0
                            
                            return MarketData(
                                code=code,
                                name=name,
                                price=current_price,
                                change=current_price - pre_close,
                                change_percent=(current_price - pre_close) / pre_close * 100 if pre_close > 0 else 0,
                                volume=volume,
                                timestamp=datetime.now(),
                            )
                    else:
                        if len(data) >= 9:
                            open_price = float(data[1]) if data[1] else 0
                            pre_close = float(data[2]) if data[2] else 0
                            current_price = float(data[3]) if data[3] else 0
                            volume = float(data[8]) if data[8] else 0
                            
                            return MarketData(
                                code=code,
                                name=data[0],
                                price=current_price,
                                change=current_price - pre_close,
                                change_percent=(current_price - pre_close) / pre_close * 100 if pre_close > 0 else 0,
                                volume=volume,
                                timestamp=datetime.now(),
                            )
        except Exception as e:
            logger.error(f"Sina stock API error: {e}")
        return None

    async def get_fund_price(self, code: str) -> Optional[MarketData]:
        try:
            url = f"https://hq.sinajs.cn/list=ff_{code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://finance.sina.com.cn/",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    content = await response.text()
                match = re.search(r'"(.*?)"', content)
                if match:
                    data = match.group(1).split(",")
                    if len(data) >= 6 and data[0]:
                        current_nav = float(data[1]) if data[1] else 0
                        pre_nav = float(data[2]) if data[2] else 0
                        
                        return MarketData(
                            code=code,
                            name=data[0],
                            price=current_nav,
                            change=current_nav - pre_nav,
                            change_percent=(current_nav - pre_nav) / pre_nav * 100 if pre_nav > 0 else 0,
                            volume=float(data[5]) if data[5] else 0,
                            timestamp=datetime.now(),
                        )
        except Exception as e:
            logger.error(f"Sina fund price API error: {e}")
        return None

    async def get_fund_info(self, code: str) -> Optional[FundInfo]:
        try:
            url = f"https://hq.sinajs.cn/list=ff_{code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://finance.sina.com.cn/",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    content = await response.text()
                match = re.search(r'"(.*?)"', content)
                if match:
                    data = match.group(1).split(",")
                    if len(data) >= 6 and data[0]:
                        fund_name = data[0]
                        nav = float(data[1]) if data[1] else None
                        market_type = determine_market_type(code, fund_name)
                        
                        detail_info = await EastMoneyAPI()._get_fund_detail_info(code)
                        
                        return FundInfo(
                            fund_code=code,
                            fund_name=fund_name,
                            fund_type="未知",
                            nav=nav,
                            establish_date=None,
                            market_type=market_type,
                            benchmark=detail_info.get("benchmark"),
                            tracking_index=detail_info.get("tracking_index"),
                        )
        except Exception as e:
            logger.error(f"Sina fund info API error: {e}")
        return None

    async def get_index_price(self, code: str) -> Optional[MarketData]:
        try:
            if code.startswith("6") or code.startswith("000"):
                sina_code = f"sh{code}"
            else:
                sina_code = f"sz{code}"
            
            url = f"https://hq.sinajs.cn/list={sina_code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://finance.sina.com.cn/",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    content = await response.text()
                match = re.search(r'"(.*?)"', content)
                if match:
                    data = match.group(1).split(",")
                    if len(data) >= 9:
                        open_price = float(data[1]) if data[1] else 0
                        pre_close = float(data[2]) if data[2] else 0
                        current_price = float(data[3]) if data[3] else 0
                        volume = float(data[8]) if data[8] else 0
                        
                        return MarketData(
                            code=code,
                            name=data[0],
                            price=current_price,
                            change=current_price - pre_close,
                            change_percent=(current_price - pre_close) / pre_close * 100 if pre_close > 0 else 0,
                            volume=volume,
                            timestamp=datetime.now(),
                        )
        except Exception as e:
            logger.error(f"Sina index API error: {e}")
        return None


class QQAPI(BaseBrokerAPI):
    """腾讯财经API实现
    
    支持功能:
    - 股票实时行情 (A股、港股)
    - 基金净值和信息
    - 指数行情
    """

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        try:
            is_hk = len(code) == 5 and code.isdigit()
            is_us = code.isalpha() and code.isupper() and len(code) <= 5
            
            if is_us:
                qq_code = f"us.{code}"
            elif is_hk:
                qq_code = f"hk{code}"
            elif code.startswith("6"):
                qq_code = f"sh{code}"
            else:
                qq_code = f"sz{code}"
            
            url = f"https://qt.gtimg.cn/q={qq_code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://gu.qq.com/",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    content = await response.text()
                match = re.search(r'"(.*?)"', content)
                if match:
                    data = match.group(1).split("~")
                    if len(data) >= 7:
                        name = data[1]
                        current_price = float(data[3]) if data[3] else 0
                        pre_close = float(data[4]) if data[4] else 0
                        volume = float(data[6]) if data[6] else 0
                        
                        return MarketData(
                            code=code,
                            name=name,
                            price=current_price,
                            change=current_price - pre_close,
                            change_percent=(current_price - pre_close) / pre_close * 100 if pre_close > 0 else 0,
                            volume=volume,
                            timestamp=datetime.now(),
                        )
        except Exception as e:
            logger.error(f"QQ stock API error: {e}")
        return None

    async def get_fund_price(self, code: str) -> Optional[MarketData]:
        try:
            url = f"https://fund.qq.com/data/getFundInfo?fundcode={code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://gu.qq.com/",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    data = await response.json()
                if data.get("data"):
                    fund_data = data["data"]
                    nav = float(fund_data.get("NAV", 0)) if fund_data.get("NAV") else 0
                    day_growth = float(fund_data.get("dayGrowth", 0)) if fund_data.get("dayGrowth") else 0
                    
                    return MarketData(
                        code=code,
                        name=fund_data.get("fund_name", code),
                        price=nav,
                        change=nav * day_growth / 100 if nav > 0 else 0,
                        change_percent=day_growth,
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
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://gu.qq.com/",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    data = await response.json()
                if data.get("data"):
                    fund_data = data["data"]
                    fund_name = fund_data.get("fund_name", code)
                    fund_type = fund_data.get("fundtype", "未知")
                    market_type = determine_market_type(code, fund_name, fund_type)
                    
                    detail_info = await EastMoneyAPI()._get_fund_detail_info(code)
                    
                    return FundInfo(
                        fund_code=code,
                        fund_name=fund_name,
                        fund_type=fund_type,
                        nav=float(fund_data.get("NAV", 0)) if fund_data.get("NAV") else None,
                        establish_date=fund_data.get("start_date", None),
                        market_type=market_type,
                        benchmark=detail_info.get("benchmark"),
                        tracking_index=detail_info.get("tracking_index"),
                    )
        except Exception as e:
            logger.error(f"QQ fund info API error: {e}")
        return None

    async def get_index_price(self, code: str) -> Optional[MarketData]:
        try:
            if code.startswith("6") or code.startswith("000"):
                qq_code = f"sh{code}"
            else:
                qq_code = f"sz{code}"
            
            url = f"https://qt.gtimg.cn/q={qq_code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://gu.qq.com/",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                    content = await response.text()
                match = re.search(r'"(.*?)"', content)
                if match:
                    data = match.group(1).split("~")
                    if len(data) >= 7:
                        name = data[1]
                        current_price = float(data[3]) if data[3] else 0
                        pre_close = float(data[4]) if data[4] else 0
                        volume = float(data[6]) if data[6] else 0
                        
                        return MarketData(
                            code=code,
                            name=name,
                            price=current_price,
                            change=current_price - pre_close,
                            change_percent=(current_price - pre_close) / pre_close * 100 if pre_close > 0 else 0,
                            volume=volume,
                            timestamp=datetime.now(),
                        )
        except Exception as e:
            logger.error(f"QQ index API error: {e}")
        return None


class HSBCAPI(BaseBrokerAPI):
    """汇丰银行API实现
    
    支持功能:
    - 汇丰代销基金信息查询
    - 汇丰代销基金净值查询
    
    注意: 
    - 汇丰API主要用于查询汇丰代销的基金产品
    - 对于一般A股、港股和指数不支持
    - 基金持仓数据不可用
    """

    _FUND_DATA_URL = "https://www.hsbc.com.cn/content/dam/hsbc/cn/sc/investments/mutual-funds/data/fund-data.json"
    _cache: Dict[str, Any] = {}
    _cache_time: Optional[datetime] = None
    _cache_ttl = 3600

    async def _get_fund_data(self) -> Optional[List[Dict[str, Any]]]:
        """获取汇丰基金数据（带缓存）"""
        now = datetime.now()
        if self._cache_time and (now - self._cache_time).total_seconds() < self._cache_ttl:
            return self._cache.get("funds")
        
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(self._FUND_DATA_URL, headers=headers, timeout=aiohttp.ClientTimeout(total=10.0)) as response:
                    if response.status != 200:
                        return None
                    data = await response.json()
                    
                if data and isinstance(data, list):
                    self._cache["funds"] = data
                    self._cache_time = now
                    return data
        except Exception as e:
            logger.error(f"HSBC fund data fetch error: {e}")
        return None

    async def _find_fund(self, code: str) -> Optional[Dict[str, Any]]:
        """查找指定基金"""
        funds = await self._get_fund_data()
        if funds:
            for fund in funds:
                if fund.get("fundCode") == code:
                    return fund
        return None

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        return None

    async def get_fund_price(self, code: str) -> Optional[MarketData]:
        try:
            fund = await self._find_fund(code)
            if fund:
                nav = float(fund.get("nav", 0)) if fund.get("nav") else 0
                pre_nav = float(fund.get("preNav", nav)) if fund.get("preNav") else nav
                change_percent = float(fund.get("dayChange", 0)) if fund.get("dayChange") else 0
                
                return MarketData(
                    code=code,
                    name=fund.get("fundName", code),
                    price=nav,
                    change=nav - pre_nav,
                    change_percent=change_percent,
                    volume=0.0,
                    timestamp=datetime.now(),
                )
        except Exception as e:
            logger.error(f"HSBC fund price API error: {e}")
        return None

    async def get_fund_info(self, code: str) -> Optional[FundInfo]:
        try:
            fund = await self._find_fund(code)
            if fund:
                fund_name = fund.get("fundName", code)
                market_type = determine_market_type(code, fund_name)
                
                return FundInfo(
                    fund_code=code,
                    fund_name=fund_name,
                    fund_type=fund.get("fundType", "未知"),
                    nav=float(fund.get("nav", 0)) if fund.get("nav") else None,
                    establish_date=fund.get("inceptionDate"),
                    market_type=market_type,
                    benchmark=fund.get("benchmark"),
                    tracking_index=fund.get("trackingIndex"),
                )
        except Exception as e:
            logger.error(f"HSBC fund info API error: {e}")
        return None

    async def get_fund_holdings(self, fund_code: str) -> List[Holding]:
        return []

    async def get_index_price(self, code: str) -> Optional[MarketData]:
        return None

    async def get_etf_realtime_data(self, code: str) -> Optional[Dict[str, Any]]:
        return None


class AkShareFallbackAPI(BaseBrokerAPI):
    """AkShare fallback实现"""

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        return None

    async def get_fund_price(self, code: str) -> Optional[MarketData]:
        try:
            df = await asyncio.to_thread(ak.fund_etf_hist_em, symbol=code, period="daily", start_date="20200101", end_date="20991231", adjust="")
            if df.empty:
                return None

            latest = df.iloc[-1]
            return MarketData(
                code=code,
                name=code,
                price=float(latest["收盘"]),
                change=float(latest["收盘"] - latest["开盘"]),
                change_percent=float((latest["收盘"] - latest["开盘"]) / latest["开盘"] * 100) if latest["开盘"] > 0 else 0,
                volume=float(latest["成交量"]),
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"AkShare fund price API error: {e}")
        return None

    async def get_fund_info(self, code: str) -> Optional[FundInfo]:
        try:
            fund_info = await asyncio.to_thread(ak.fund_open_fund_info_em, symbol=code, indicator="单位净值走势")
            if not fund_info.empty:
                fund_name = code
                fund_type = "未知"
                market_type = determine_market_type(code, fund_name, fund_type)
                
                latest_nav = None
                if len(fund_info) > 0:
                    latest_row = fund_info.iloc[-1]
                    latest_nav = float(latest_row.get("单位净值", 0)) if "单位净值" in latest_row else None
                
                detail_info = await EastMoneyAPI()._get_fund_detail_info(code)
                
                return FundInfo(
                    fund_code=code,
                    fund_name=fund_name,
                    fund_type=fund_type,
                    nav=latest_nav,
                    establish_date=None,
                    market_type=market_type,
                    benchmark=detail_info.get("benchmark"),
                    tracking_index=detail_info.get("tracking_index"),
                )
        except Exception as e:
            logger.error(f"AkShare fund info API error: {e}")
        return None

    async def get_fund_nav_history(self, code: str) -> Optional[Dict[str, Any]]:
        """
        获取基金历史净值
        返回: {"previous_nav": 昨日净值, "latest_nav": 最新净值, "nav_date": 净值日期}
        """
        try:
            fund_info = await asyncio.to_thread(ak.fund_open_fund_info_em, symbol=code, indicator="单位净值走势")
            if fund_info is not None and len(fund_info) >= 2:
                latest = fund_info.iloc[-1]
                previous = fund_info.iloc[-2]
                
                latest_nav = float(latest['单位净值']) if latest['单位净值'] else None
                previous_nav = float(previous['单位净值']) if previous['单位净值'] else None
                nav_date = str(latest['净值日期']) if '净值日期' in latest else None
                
                return {
                    "previous_nav": previous_nav,
                    "latest_nav": latest_nav,
                    "nav_date": nav_date
                }
        except Exception as e:
            logger.error(f"AkShare fund nav history API error: {e}")
        return None

    async def get_index_price(self, code: str) -> Optional[MarketData]:
        try:
            df = await asyncio.to_thread(ak.index_zh_a_hist, symbol=code, period="daily", start_date="20200101", end_date="20991231")
            if df.empty:
                return None

            latest = df.iloc[-1]
            return MarketData(
                code=code,
                name=code,
                price=float(latest["收盘"]),
                change=float(latest["收盘"] - latest["开盘"]),
                change_percent=float((latest["收盘"] - latest["开盘"]) / latest["开盘"] * 100) if latest["开盘"] > 0 else 0,
                volume=float(latest["成交量"]),
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"AkShare index price API error: {e}")
        return None


class YFinanceFallbackAPI(BaseBrokerAPI):
    """YFinance fallback实现"""

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        try:
            if len(code) == 5 and code.isdigit():
                symbol = f"{code}.HK"
            elif code.isalpha() and code.isupper():
                symbol = code
            elif code.startswith("6"):
                symbol = f"{code}.SS"
            elif code.startswith("0") or code.startswith("3"):
                symbol = f"{code}.SZ"
            else:
                symbol = code

            ticker = yf.Ticker(symbol)
            info = await asyncio.to_thread(ticker.history, period="1d", interval="1m")

            if info is None or info.empty:
                return None
            
            if len(info) == 0:
                return None

            latest = info.iloc[-1]
            
            if latest is None:
                return None
            
            close_price = latest.get("Close")
            open_price = latest.get("Open")
            volume = latest.get("Volume")
            
            if close_price is None or open_price is None:
                return None

            return MarketData(
                code=code,
                name=code,
                price=float(close_price),
                change=float(close_price - open_price),
                change_percent=float((close_price - open_price) / open_price * 100) if open_price > 0 else 0,
                volume=float(volume) if volume is not None else 0,
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"YFinance stock API error: {e}")
        return None


class MarketDataService:
    """市场数据服务"""

    def __init__(self):
        self.cache: Dict[str, MarketData] = {}
        self.cache_timeout = 60
        self.brokers = self._init_brokers()

    def _init_brokers(self) -> List[BaseBrokerAPI]:
        """初始化券商API列表"""
        return [
            EastMoneyAPI(),
            SinaAPI(),
            QQAPI(),
            HSBCAPI(),
        ]

    async def get_stock_price(self, code: str) -> Optional[MarketData]:
        """获取股票价格"""
        for broker in self.brokers:
            try:
                data = await broker.get_stock_price(code)
                if data:
                    return data
            except Exception as e:
                logger.debug(f"Broker {broker.__class__.__name__} error: {e}")
        
        return await YFinanceFallbackAPI().get_stock_price(code)

    async def get_fund_price(self, code: str) -> Optional[MarketData]:
        """获取基金价格"""
        for broker in self.brokers:
            try:
                data = await broker.get_fund_price(code)
                if data:
                    return data
            except Exception as e:
                logger.debug(f"Broker {broker.__class__.__name__} error: {e}")
        
        return await AkShareFallbackAPI().get_fund_price(code)

    async def get_fund_info(self, fund_code: str) -> Optional[FundInfo]:
        """获取基金信息"""
        logger.info(f"Getting fund info for {fund_code}")
        
        for broker in self.brokers:
            try:
                logger.debug(f"Trying broker: {broker.__class__.__name__}")
                info = await broker.get_fund_info(fund_code)
                if info:
                    logger.info(f"Successfully got fund info from {broker.__class__.__name__}")
                    return info
            except Exception as e:
                logger.debug(f"Broker {broker.__class__.__name__} error: {e}")
        
        logger.debug("Trying AkShare as fallback")
        info = await AkShareFallbackAPI().get_fund_info(fund_code)
        if info:
            logger.info("Successfully got fund info from AkShare")
            return info

        logger.warning(f"All data sources failed for fund {fund_code}")
        return FundInfo(
            fund_code=fund_code,
            fund_name=f"基金{fund_code}",
            fund_type="未知",
            nav=0.0,
            establish_date=None,
            market_type=determine_market_type(fund_code),
            benchmark=None,
            tracking_index=None,
        )

    async def get_fund_holdings(self, fund_code: str) -> List[Holding]:
        """获取基金持仓"""
        return await EastMoneyAPI().get_fund_holdings(fund_code)

    async def get_fund_nav_history(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """
        获取基金历史净值
        
        Args:
            fund_code: 基金代码
            
        Returns:
            Optional[Dict]: {"previous_nav": 昨日净值, "latest_nav": 最新净值, "nav_date": 净值日期}
        """
        return await AkShareFallbackAPI().get_fund_nav_history(fund_code)

    async def get_index_price(self, code: str) -> Optional[MarketData]:
        """获取指数价格"""
        for broker in self.brokers:
            try:
                data = await broker.get_index_price(code)
                if data:
                    return data
            except Exception as e:
                logger.debug(f"Broker {broker.__class__.__name__} error: {e}")
        
        return await AkShareFallbackAPI().get_index_price(code)

    async def get_etf_realtime_data(self, code: str) -> Optional[Dict[str, Any]]:
        """获取ETF实时数据"""
        return await EastMoneyAPI().get_etf_realtime_data(code)

    async def get_index_realtime_data(self, index_code: str) -> Optional[Dict[str, Any]]:
        """
        获取指数实时数据
        
        Args:
            index_code: 指数代码（如 000300）
            
        Returns:
            Optional[Dict]: 包含价格、涨跌幅等信息的字典
        """
        index_info = INDEX_MAPPING.get(index_code)
        if not index_info:
            logger.warning(f"Index {index_code} not in mapping")
            return None
        
        try:
            session = await get_session()
            full_code = index_info["code"]
            secid = f"1.{index_code}" if full_code.startswith("sh") else f"0.{index_code}"
            
            url = "https://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": secid,
                "fields": "f43,f44,f45,f46,f47,f48,f49,f14,f169,f170",
            }
            
            async with session.get(url, params=params, headers=DEFAULT_HEADERS) as response:
                data = await response.json()
            
            if data.get("data"):
                tick = data["data"]
                price = float(tick.get("f43", 0)) / 100
                change_percent = float(tick.get("f170", 0)) / 100
                
                return {
                    "code": index_code,
                    "name": tick.get("f14", index_info["name"]),
                    "price": price,
                    "change_percent": change_percent,
                }
            
            logger.warning(f"Index {index_code} not found in response")
            return None
        except Exception as e:
            logger.error(f"Error getting index realtime data for {index_code}: {e}")
            return None

    async def get_global_index_realtime_data(self, index_code: str) -> Optional[Dict[str, Any]]:
        """
        获取海外指数实时数据
        
        Args:
            index_code: 指数代码（如 nasdaq, sp500, hsi）
            
        Returns:
            Optional[Dict]: 包含价格、涨跌幅等信息的字典
        """
        index_info = GLOBAL_INDEX_MAPPING.get(index_code.lower())
        if not index_info:
            logger.warning(f"Global index {index_code} not in mapping")
            return None
        
        try:
            session = await get_session()
            secid = index_info["secid"]
            url = "https://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": secid,
                "fields": "f43,f44,f45,f46,f47,f48,f49,f14,f169,f170",
            }
            
            async with session.get(url, params=params, headers=DEFAULT_HEADERS) as response:
                data = await response.json()
            
            if data.get("data"):
                tick = data["data"]
                price = float(tick.get("f43", 0)) / 100
                change_percent = float(tick.get("f170", 0)) / 100
                
                return {
                    "code": index_code,
                    "name": index_info["name"],
                    "price": price,
                    "change_percent": change_percent,
                }
        except Exception as e:
            logger.error(f"Error getting global index data for {index_code}: {e}")
        
        try:
            session = await get_session()
            sina_code = index_info["sina"]
            url = f"https://hq.sinajs.cn/list={sina_code}"
            headers = {**DEFAULT_HEADERS, "Referer": "https://finance.sina.com.cn/"}
            
            async with session.get(url, headers=headers) as response:
                content = await response.text()
            
            match = re.search(r'"(.*?)"', content)
            if match:
                data = match.group(1).split(",")
                if len(data) >= 4:
                    name = data[0] if data[0] else index_info["name"]
                    price = float(data[1]) if data[1] else 0
                    change_percent = float(data[3]) if data[3] else 0
                    
                    return {
                        "code": index_code,
                        "name": name,
                        "price": price,
                        "change_percent": change_percent,
                    }
        except Exception as e:
            logger.error(f"Error getting global index data from Sina for {index_code}: {e}")
        
        return None

    async def get_market_data(self, code: str, asset_type: AssetType) -> Optional[MarketData]:
        """获取市场数据"""
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
        result_map = {}
        tasks = []
        for code, asset_type in items:
            tasks.append(self.get_market_data(code, asset_type))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for (code, _), result in zip(items, results):
            if isinstance(result, Exception):
                logger.error(f"Error getting market data for {code}: {result}")
            elif result is not None:
                result_map[code] = result
        
        return result_map

    def clear_cache(self):
        """清除缓存"""
        self.cache.clear()


market_data_service = MarketDataService()
