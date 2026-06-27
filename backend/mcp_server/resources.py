"""
MCP Resources 实现

实现所有 MCP Resource 处理器，提供 URI 形式的资源访问
"""

import httpx
import json
from datetime import datetime
from loguru import logger

API_BASE_URL = "http://127.0.0.1:8000/api"


class FundValuationResources:
    """智能理财Agent MCP Resources"""

    def __init__(self, api_base_url: str = API_BASE_URL):
        self.api_base_url = api_base_url

    async def _request(self, method: str, endpoint: str, json: dict = None) -> dict:
        """发送 HTTP 请求到后端 API"""
        url = f"{self.api_base_url}{endpoint}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0, read=60.0)) as client:
            try:
                if method == "GET":
                    response = await client.get(url)
                elif method == "POST":
                    response = await client.post(url, json=json)
                else:
                    raise ValueError(f"不支持的 HTTP 方法：{method}")
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as e:
                logger.error(f"HTTP 超时：{url}, 错误：{e}")
                raise
            except httpx.HTTPError as e:
                logger.error(f"HTTP 错误：{url}, 错误：{type(e).__name__}: {str(e)}")
                raise

    async def get_fund_resource(self, fund_code: str) -> str:
        """
        获取基金详细信息资源

        Resource URI: fund://{fund_code}
        """
        logger.info(f"[MCP Resource] get_fund_resource: {fund_code}")
        try:
            result = await self._request("GET", f"/funds/{fund_code}")

            if not result.get("success"):
                return f"获取基金信息失败：{result.get('message', '未知错误')}"

            data = result.get("data", {})
            if not data:
                return f"未找到基金：{fund_code}"

            # 格式化输出
            output = []
            output.append(f"# 基金信息：{data.get('fund_name', 'N/A')} ({fund_code})")
            output.append("")
            output.append(f"- **基金代码**: {fund_code}")
            output.append(f"- **基金名称**: {data.get('fund_name', 'N/A')}")
            output.append(f"- **基金类型**: {data.get('fund_type', 'N/A')}")

            if data.get('total_shares'):
                output.append(f"- **持有份额**: {data.get('total_shares'):,.2f}")

            if data.get('nav'):
                output.append(f"- **单位净值**: ¥{data.get('nav'):,.4f}")

            if data.get('market_type'):
                output.append(f"- **市场类型**: {'场内' if data.get('market_type') == 'on_exchange' else '场外'}")

            if data.get('establish_date'):
                output.append(f"- **成立日期**: {data.get('establish_date')}")

            if data.get('benchmark'):
                output.append(f"- **业绩基准**: {data.get('benchmark')}")

            if data.get('tracking_index'):
                output.append(f"- **跟踪指数**: {data.get('tracking_index')}")

            output.append("")
            output.append(f"_数据获取时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_")

            return "\n".join(output)

        except Exception as e:
            logger.error(f"获取基金资源失败：{e}")
            return f"获取基金资源失败：{str(e)}"

    async def get_valuation_resource(self, fund_code: str) -> str:
        """
        获取基金实时估值资源

        Resource URI: valuation://{fund_code}
        """
        logger.info(f"[MCP Resource] get_valuation_resource: {fund_code}")
        try:
            result = await self._request("GET", f"/valuation/{fund_code}")

            if not result.get("success"):
                return f"获取基金估值失败：{result.get('message', '未知错误')}"

            data = result.get("data", {})
            if not data:
                return f"无法获取基金估值：{fund_code}"

            # 格式化输出
            output = []
            output.append(f"# 基金估值：{data.get('fund_name', 'N/A')} ({fund_code})")
            output.append("")
            output.append("## 估值结果")
            output.append("")
            output.append(f"- **估算净值**: ¥{data.get('estimated_nav', 'N/A'):.4f}" if data.get('estimated_nav') else "- **估算净值**: N/A")
            output.append(f"- **估算涨跌幅**: {data.get('estimated_change_percent', 'N/A'):.2f}%" if data.get('estimated_change_percent') else "- **估算涨跌幅**: N/A")
            output.append(f"- **昨日净值**: ¥{data.get('previous_nav', 'N/A'):.4f}" if data.get('previous_nav') else "- **昨日净值**: N/A")
            output.append(f"- **最新净值**: ¥{data.get('latest_nav', 'N/A'):.4f}" if data.get('latest_nav') else "- **最新净值**: N/A")
            output.append(f"- **净值日期**: {data.get('nav_date', 'N/A')}")

            output.append("")
            output.append("## 估值信息")
            output.append("")
            output.append(f"- **估值类型**: {data.get('valuation_type', 'N/A')}")
            output.append(f"- **估值方法**: {data.get('valuation_method', 'N/A')}")
            output.append(f"- **置信度**: {data.get('confidence', 0) * 100:.0f}%" if data.get('confidence') else "- **置信度**: N/A")
            output.append(f"- **说明**: {data.get('confidence_note', 'N/A')}" if data.get('confidence_note') else "- **说明**: 无")

            if data.get('benchmark_info'):
                benchmark = data['benchmark_info']
                output.append("")
                output.append("## 基准信息")
                output.append("")
                if benchmark.get('name'):
                    output.append(f"- **基准名称**: {benchmark.get('name')}")
                if benchmark.get('change_percent') is not None:
                    output.append(f"- **基准涨跌幅**: {benchmark.get('change_percent'):.2f}%")

            output.append("")
            output.append(f"_估值时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_")

            return "\n".join(output)

        except Exception as e:
            logger.error(f"获取估值资源失败：{e}")
            return f"获取估值资源失败：{str(e)}"

    async def get_stock_resource(self, stock_code: str) -> str:
        """
        获取股票行情资源

        Resource URI: market://stock/{stock_code}
        """
        logger.info(f"[MCP Resource] get_stock_resource: {stock_code}")
        try:
            result = await self._request("GET", f"/market/stock/{stock_code}")

            if not result.get("success"):
                return f"获取股票行情失败：{result.get('message', '未知错误')}"

            data = result.get("data", {})
            if not data:
                return f"未找到股票：{stock_code}"

            # 格式化输出
            output = []
            output.append(f"# 股票行情：{data.get('name', 'N/A')} ({stock_code})")
            output.append("")
            output.append("## 实时数据")
            output.append("")
            output.append(f"- **当前价格**: ¥{data.get('price', 0):.2f}")

            change = data.get('change')
            change_pct = data.get('change_percent')
            if change is not None and change_pct is not None:
                sign = "+" if change >= 0 else ""
                output.append(f"- **涨跌额**: {sign}{change:.2f}")
                output.append(f"- **涨跌幅**: {sign}{change_pct:.2f}%")

            if data.get('volume'):
                output.append(f"- **成交量**: {data.get('volume'):,.0f}")

            if data.get('high'):
                output.append(f"- **最高价**: ¥{data.get('high'):.2f}")
            if data.get('low'):
                output.append(f"- **最低价**: ¥{data.get('low'):.2f}")
            if data.get('open'):
                output.append(f"- **开盘价**: ¥{data.get('open'):.2f}")
            if data.get('prev_close'):
                output.append(f"- **昨收价**: ¥{data.get('prev_close'):.2f}")

            output.append("")
            output.append(f"_数据时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_")

            return "\n".join(output)

        except Exception as e:
            logger.error(f"获取股票资源失败：{e}")
            return f"获取股票资源失败：{str(e)}"

    async def get_etf_resource(self, etf_code: str) -> str:
        """
        获取 ETF 行情资源

        Resource URI: market://etf/{etf_code}
        """
        logger.info(f"[MCP Resource] get_etf_resource: {etf_code}")
        try:
            result = await self._request("GET", f"/market/etf/{etf_code}")

            if not result.get("success"):
                return f"获取 ETF 行情失败：{result.get('message', '未知错误')}"

            data = result.get("data", {})
            if not data:
                return f"未找到 ETF：{etf_code}"

            # 格式化输出
            output = []
            output.append(f"# ETF 行情：{data.get('name', 'N/A')} ({etf_code})")
            output.append("")
            output.append("## 实时数据")
            output.append("")
            output.append(f"- **当前价格**: ¥{data.get('price', 0):.3f}")

            change = data.get('change')
            change_pct = data.get('change_percent')
            if change is not None and change_pct is not None:
                sign = "+" if change >= 0 else ""
                output.append(f"- **涨跌额**: {sign}{change:.3f}")
                output.append(f"- **涨跌幅**: {sign}{change_pct:.2f}%")

            if data.get('volume'):
                output.append(f"- **成交量**: {data.get('volume'):,.0f}")
            if data.get('amount'):
                output.append(f"- **成交额**: ¥{data.get('amount'):,.0f}")

            output.append("")
            output.append(f"_数据时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_")

            return "\n".join(output)

        except Exception as e:
            logger.error(f"获取 ETF 资源失败：{e}")
            return f"获取 ETF 资源失败：{str(e)}"

    async def get_index_resource(self, index_code: str) -> str:
        """
        获取指数行情资源

        Resource URI: market://index/{index_code}
        """
        logger.info(f"[MCP Resource] get_index_resource: {index_code}")
        try:
            result = await self._request("GET", f"/market/index/{index_code}")

            if not result.get("success"):
                return f"获取指数行情失败：{result.get('message', '未知错误')}"

            data = result.get("data", {})
            if not data:
                return f"未找到指数：{index_code}"

            # 格式化输出
            output = []
            output.append(f"# 指数行情：{data.get('name', 'N/A')} ({index_code})")
            output.append("")
            output.append("## 实时数据")
            output.append("")
            output.append(f"- **当前点位**: {data.get('price', 0):.2f}")

            change = data.get('change')
            change_pct = data.get('change_percent')
            if change is not None and change_pct is not None:
                sign = "+" if change >= 0 else ""
                output.append(f"- **涨跌额**: {sign}{change:.2f}")
                output.append(f"- **涨跌幅**: {sign}{change_pct:.2f}%")

            output.append("")
            output.append(f"_数据时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_")

            return "\n".join(output)

        except Exception as e:
            logger.error(f"获取指数资源失败：{e}")
            return f"获取指数资源失败：{str(e)}"

    async def get_global_index_resource(self, index_code: str) -> str:
        """
        获取海外指数行情资源

        Resource URI: market://global-index/{index_code}
        """
        logger.info(f"[MCP Resource] get_global_index_resource: {index_code}")
        try:
            result = await self._request("GET", f"/market/global-index/{index_code}")

            if not result.get("success"):
                return f"获取海外指数行情失败：{result.get('message', '未知错误')}"

            data = result.get("data", {})
            if not data:
                return f"未找到海外指数：{index_code}"

            # 格式化输出
            output = []
            output.append(f"# 海外指数行情：{data.get('name', 'N/A')} ({index_code})")
            output.append("")
            output.append("## 实时数据")
            output.append("")
            output.append(f"- **当前点位**: {data.get('price', 0):.2f}")

            change = data.get('change')
            change_pct = data.get('change_percent')
            if change is not None and change_pct is not None:
                sign = "+" if change >= 0 else ""
                output.append(f"- **涨跌额**: {sign}{change:.2f}")
                output.append(f"- **涨跌幅**: {sign}{change_pct:.2f}%")

            output.append("")
            output.append(f"_数据时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_")

            return "\n".join(output)

        except Exception as e:
            logger.error(f"获取海外指数资源失败：{e}")
            return f"获取海外指数资源失败：{str(e)}"
