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
    """智能理财Agent MCP Tools"""

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

    async def get_gold_prediction(self, symbol: str = "GC", horizon_days: int = 1, model_type: str = "lightgbm") -> dict:
        """获取黄金价格预测"""
        logger.info(f"[MCP Tool] get_gold_prediction: symbol={symbol}, horizon={horizon_days}, model={model_type}")
        try:
            result = await self._request("POST", f"/gold/predict?symbol={symbol}&horizon_days={horizon_days}&model_type={model_type}")
            return result
        except Exception as e:
            logger.error(f"获取黄金预测失败：{e}")
            return {"success": False, "message": f"获取黄金预测失败：{str(e)}", "data": None}

    async def get_gold_tb_prediction(self, symbol: str = "GC", model_type: str = "lightgbm") -> dict:
        """获取 Triple-Barrier 方向预测"""
        logger.info(f"[MCP Tool] get_gold_tb_prediction: symbol={symbol}, model={model_type}")
        try:
            result = await self._request("POST", f"/gold/predict-tb?symbol={symbol}&model_type={model_type}")
            return result
        except Exception as e:
            logger.error(f"获取TB预测失败：{e}")
            return {"success": False, "message": f"获取TB预测失败：{str(e)}", "data": None}

    async def get_gold_price(self) -> dict:
        """获取当前黄金价格和宏观指标"""
        logger.info(f"[MCP Tool] get_gold_price")
        try:
            result = await self._request("GET", "/gold/current")
            return result
        except Exception as e:
            logger.error(f"获取黄金价格失败：{e}")
            return {"success": False, "message": f"获取黄金价格失败：{str(e)}", "data": None}

    async def run_gold_backtest(self, years: int = 1, model_types: str = "lightgbm,xgboost,ridge", method: str = "walk_forward") -> dict:
        """运行黄金预测模型回测"""
        logger.info(f"[MCP Tool] run_gold_backtest: years={years}, models={model_types}, method={method}")
        try:
            payload = {
                "years": years,
                "model_types": model_types,
            }
            endpoint = f"/gold/backtest?years={years}&model_types={model_types}&method={method}"
            result = await self._request("POST", endpoint, json=payload)
            return result
        except Exception as e:
            logger.error(f"运行黄金回测失败：{e}")
            return {"success": False, "message": f"运行黄金回测失败：{str(e)}", "data": None}

    async def get_gold_drift_status(self, model_type: str = None, horizon_days: int = None) -> dict:
        """获取模型漂移检测状态"""
        logger.info(f"[MCP Tool] get_gold_drift_status: model={model_type}, horizon={horizon_days}")
        try:
            params = []
            if model_type:
                params.append(f"model_type={model_type}")
            if horizon_days:
                params.append(f"horizon_days={horizon_days}")
            query = f"/gold/drift-status?{'&'.join(params)}" if params else "/gold/drift-status"
            result = await self._request("GET", query)
            return result
        except Exception as e:
            logger.error(f"获取漂移状态失败：{e}")
            return {"success": False, "message": f"获取漂移状态失败：{str(e)}", "data": None}

    async def get_gold_factor_importance(self, model_type: str = "lightgbm", horizon_days: int = 1) -> dict:
        """获取黄金预测因子重要性"""
        logger.info(f"[MCP Tool] get_gold_factor_importance: model={model_type}, horizon={horizon_days}")
        try:
            result = await self._request("GET", f"/gold/factor-importance?model_type={model_type}&horizon_days={horizon_days}")
            return result
        except Exception as e:
            logger.error(f"获取因子重要性失败：{e}")
            return {"success": False, "message": f"获取因子重要性失败：{str(e)}", "data": None}

    async def get_gold_trend_signal(self, symbol: str = "GC") -> dict:
        """获取黄金趋势跟踪信号"""
        logger.info(f"[MCP Tool] get_gold_trend_signal: symbol={symbol}")
        try:
            result = await self._request("GET", f"/gold/trend-signal?symbol={symbol}")
            return result
        except Exception as e:
            logger.error(f"获取趋势信号失败：{e}")
            return {"success": False, "message": f"获取趋势信号失败：{str(e)}", "data": None}

    async def run_gold_trend_backtest(self, years: int = 2, fast_ma: int = 50, slow_ma: int = 200, sl_multiplier: float = 2.0) -> dict:
        """运行趋势跟踪策略回测"""
        logger.info(f"[MCP Tool] run_gold_trend_backtest: years={years}, fast={fast_ma}, slow={slow_ma}")
        try:
            endpoint = f"/gold/backtest-trend?years={years}&fast_ma={fast_ma}&slow_ma={slow_ma}&sl_multiplier={sl_multiplier}"
            result = await self._request("POST", endpoint)
            return result
        except Exception as e:
            logger.error(f"趋势回测失败：{e}")
            return {"success": False, "message": f"趋势回测失败：{str(e)}", "data": None}

    # ===== 黄金量化交易 MCP Tools =====

    async def get_gold_strategies(self) -> dict:
        """获取黄金量化策略列表及描述"""
        logger.info(f"[MCP Tool] get_gold_strategies")
        try:
            result = await self._request("GET", "/gold/trading/strategies")
            return result
        except Exception as e:
            logger.error(f"获取策略列表失败：{e}")
            return {"success": False, "message": f"获取策略列表失败：{str(e)}", "data": None}

    async def get_gold_signals(self, strategy_name: str = None, limit: int = 20) -> dict:
        """获取最近黄金交易建议信号"""
        logger.info(f"[MCP Tool] get_gold_signals: strategy={strategy_name}, limit={limit}")
        try:
            params = [f"limit={limit}"]
            if strategy_name:
                params.append(f"strategy_name={strategy_name}")
            result = await self._request("GET", f"/gold/trading/signals?{'&'.join(params)}")
            return result
        except Exception as e:
            logger.error(f"获取交易信号失败：{e}")
            return {"success": False, "message": f"获取交易信号失败：{str(e)}", "data": None}

    async def run_gold_strategy_backtest(self, strategy_name: str = "trend_following",
                                          start_date: str = "2024-01-01",
                                          end_date: str = "2024-12-31",
                                          capital: float = 1000000) -> dict:
        """运行黄金量化策略回测"""
        logger.info(f"[MCP Tool] run_gold_strategy_backtest: strategy={strategy_name}")
        try:
            payload = {
                "strategy_name": strategy_name,
                "symbol": "AU0",
                "period": "d",
                "start_date": start_date,
                "end_date": end_date,
                "capital": capital,
            }
            result = await self._request("POST", "/gold/trading/backtest", json=payload)
            return result
        except Exception as e:
            logger.error(f"策略回测失败：{e}")
            return {"success": False, "message": f"策略回测失败：{str(e)}", "data": None}

    async def compare_gold_strategies(self, strategy_names: list[str] = None,
                                      start_date: str = "2024-01-01",
                                      end_date: str = "2024-12-31") -> dict:
        """多策略对比回测"""
        logger.info(f"[MCP Tool] compare_gold_strategies: {strategy_names}")
        try:
            payload = {
                "strategy_names": strategy_names or ["trend_following", "mean_reversion", "ml_predictor"],
                "symbol": "AU0",
                "period": "d",
                "start_date": start_date,
                "end_date": end_date,
                "capital": 1000000,
            }
            result = await self._request("POST", "/gold/trading/compare", json=payload)
            return result
        except Exception as e:
            logger.error(f"多策略对比失败：{e}")
            return {"success": False, "message": f"多策略对比失败：{str(e)}", "data": None}

    async def get_gold_risk_status(self) -> dict:
        """获取黄金交易风控状态"""
        logger.info(f"[MCP Tool] get_gold_risk_status")
        try:
            result = await self._request("GET", "/gold/trading/risk/status")
            return result
        except Exception as e:
            logger.error(f"获取风控状态失败：{e}")
            return {"success": False, "message": f"获取风控状态失败：{str(e)}", "data": None}
