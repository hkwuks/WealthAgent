"""
MCP Tools 实现

实现所有 MCP Tool 处理器，调用后端 API 获取数据
"""

import httpx
from typing import Optional
from loguru import logger

# API 基础 URL
API_BASE_URL = "http://127.0.0.1:8000/api"


class FundValuationTools:
    """基金估值系统 MCP Tools"""

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
                elif method == "DELETE":
                    response = await client.delete(url)
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

    async def get_fund_list(self) -> dict:
        """获取当前持仓基金列表"""
        logger.info(f"[MCP Tool] get_fund_list")
        try:
            result = await self._request("GET", "/funds")
            return {
                "success": result.get("success", False),
                "data": result.get("data", {}),
                "message": result.get("message", ""),
            }
        except Exception as e:
            logger.error(f"获取基金列表失败：{e}")
            return {"success": False, "message": f"获取基金列表失败：{str(e)}", "data": None}

    async def add_fund(self, fund_code: str, fund_name: str, fund_type: str, total_shares: float) -> dict:
        """添加新基金到持仓列表"""
        logger.info(f"[MCP Tool] add_fund: {fund_code}")
        try:
            fund_data = {
                "fund_code": fund_code,
                "fund_name": fund_name,
                "fund_type": fund_type,
                "total_shares": total_shares,
            }
            result = await self._request("POST", "/funds/add", json=fund_data)
            return result
        except Exception as e:
            logger.error(f"添加基金失败：{e}")
            return {"success": False, "message": f"添加基金失败：{str(e)}"}

    async def delete_fund(self, fund_code: str) -> dict:
        """从持仓列表中删除基金"""
        logger.info(f"[MCP Tool] delete_fund: {fund_code}")
        try:
            result = await self._request("DELETE", f"/funds/{fund_code}")
            return result
        except Exception as e:
            logger.error(f"删除基金失败：{e}")
            return {"success": False, "message": f"删除基金失败：{str(e)}"}

    async def get_fund_info(self, fund_code: str) -> dict:
        """获取基金详细信息"""
        logger.info(f"[MCP Tool] get_fund_info: {fund_code}")
        try:
            result = await self._request("GET", f"/funds/{fund_code}")
            return result
        except Exception as e:
            logger.error(f"获取基金信息失败：{e}")
            return {"success": False, "message": f"获取基金信息失败：{str(e)}", "data": None}

    async def get_valuation(self, fund_code: str, prefer_holdings: bool = True) -> dict:
        """获取基金实时估值"""
        logger.info(f"[MCP Tool] get_valuation: {fund_code}")
        try:
            result = await self._request("GET", f"/valuation/{fund_code}?prefer_holdings={prefer_holdings}")
            return result
        except Exception as e:
            logger.error(f"获取基金估值失败：{e}")
            return {"success": False, "message": f"获取基金估值失败：{str(e)}", "data": None}

    async def get_batch_valuation(self, fund_codes: list[str], prefer_holdings: bool = True) -> dict:
        """批量获取基金估值"""
        logger.info(f"[MCP Tool] get_batch_valuation: {fund_codes}")
        try:
            payload = {
                "fund_codes": fund_codes,
                "prefer_holdings": prefer_holdings,
            }
            result = await self._request("POST", "/valuation/batch", json=payload)
            return result
        except Exception as e:
            logger.error(f"批量获取基金估值失败：{e}")
            return {"success": False, "message": f"批量获取基金估值失败：{str(e)}", "data": None}

    async def get_stock_price(self, stock_code: str) -> dict:
        """获取 A 股股票实时行情"""
        logger.info(f"[MCP Tool] get_stock_price: {stock_code}")
        try:
            result = await self._request("GET", f"/market/stock/{stock_code}")
            return result
        except Exception as e:
            logger.error(f"获取股票价格失败：{e}")
            return {"success": False, "message": f"获取股票价格失败：{str(e)}", "data": None}

    async def get_etf_price(self, etf_code: str) -> dict:
        """获取场内 ETF 实时行情"""
        logger.info(f"[MCP Tool] get_etf_price: {etf_code}")
        try:
            result = await self._request("GET", f"/market/etf/{etf_code}")
            return result
        except Exception as e:
            logger.error(f"获取 ETF 价格失败：{e}")
            return {"success": False, "message": f"获取 ETF 价格失败：{str(e)}", "data": None}

    async def get_index_price(self, index_code: str) -> dict:
        """获取国内指数实时行情"""
        logger.info(f"[MCP Tool] get_index_price: {index_code}")
        try:
            result = await self._request("GET", f"/market/index/{index_code}")
            return result
        except Exception as e:
            logger.error(f"获取指数价格失败：{e}")
            return {"success": False, "message": f"获取指数价格失败：{str(e)}", "data": None}

    async def get_global_index_price(self, index_code: str) -> dict:
        """获取海外指数实时行情"""
        logger.info(f"[MCP Tool] get_global_index_price: {index_code}")
        try:
            result = await self._request("GET", f"/market/global-index/{index_code}")
            return result
        except Exception as e:
            logger.error(f"获取海外指数价格失败：{e}")
            return {"success": False, "message": f"获取海外指数价格失败：{str(e)}", "data": None}

    async def get_valuation_types(self) -> dict:
        """获取支持的估值类型说明"""
        logger.info(f"[MCP Tool] get_valuation_types")
        try:
            result = await self._request("GET", "/valuation/info/types")
            return result
        except Exception as e:
            logger.error(f"获取估值类型失败：{e}")
            return {"success": False, "message": f"获取估值类型失败：{str(e)}", "data": None}

    async def get_supported_indices(self) -> dict:
        """获取支持的指数列表"""
        logger.info(f"[MCP Tool] get_supported_indices")
        try:
            result = await self._request("GET", "/market/indices")
            return result
        except Exception as e:
            logger.error(f"获取指数列表失败：{e}")
            return {"success": False, "message": f"获取指数列表失败：{str(e)}", "data": None}
