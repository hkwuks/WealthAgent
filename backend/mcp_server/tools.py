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

    # ===== 剩余黄金量化 MCP Tools（补齐） =====

    async def get_gold_status(self) -> dict:
        """获取黄金量化交易系统状态"""
        logger.info(f"[MCP Tool] get_gold_status")
        try:
            result = await self._request("GET", "/gold/trading/status")
            return result
        except Exception as e:
            logger.error(f"获取系统状态失败：{e}")
            return {"success": False, "message": f"获取系统状态失败：{str(e)}", "data": None}

    async def get_gold_strategy_detail(self, strategy_name: str) -> dict:
        """获取策略详情和参数"""
        logger.info(f"[MCP Tool] get_gold_strategy_detail: {strategy_name}")
        try:
            result = await self._request("GET", f"/gold/trading/strategies/{strategy_name}")
            return result
        except Exception as e:
            logger.error(f"获取策略详情失败：{e}")
            return {"success": False, "message": f"获取策略详情失败：{str(e)}", "data": None}

    async def run_gold_sensitivity(self, strategy_name: str, symbol: str = "AU0",
                                   period: str = "d", start_date: str = None,
                                   end_date: str = None, capital: float = 1_000_000,
                                   param_ranges: dict = None) -> dict:
        """运行参数敏感性分析"""
        logger.info(f"[MCP Tool] run_gold_sensitivity: {strategy_name}")
        try:
            payload = {
                "strategy_name": strategy_name, "symbol": symbol, "period": period,
                "start_date": start_date, "end_date": end_date, "capital": capital,
                "param_ranges": param_ranges or {},
            }
            result = await self._request("POST", "/gold/trading/backtest/sensitivity", json=payload)
            return result
        except Exception as e:
            logger.error(f"敏感性分析失败：{e}")
            return {"success": False, "message": f"敏感性分析失败：{str(e)}", "data": None}

    async def run_gold_validation(self, strategy_name: str, symbol: str = "AU0",
                                  period: str = "d", start_date: str = None,
                                  end_date: str = None, capital: float = 1_000_000,
                                  in_sample_ratio: float = 0.7, scenario_name: str = None) -> dict:
        """运行策略验证（In/Out 样本 + 场景验证）"""
        logger.info(f"[MCP Tool] run_gold_validation: {strategy_name}")
        try:
            payload = {
                "strategy_name": strategy_name, "symbol": symbol, "period": period,
                "start_date": start_date, "end_date": end_date, "capital": capital,
                "in_sample_ratio": in_sample_ratio, "scenario_name": scenario_name,
            }
            result = await self._request("POST", "/gold/trading/backtest/validation", json=payload)
            return result
        except Exception as e:
            logger.error(f"策略验证失败：{e}")
            return {"success": False, "message": f"策略验证失败：{str(e)}", "data": None}

    async def run_gold_walk_forward(self, strategy_name: str, symbol: str = "AU0",
                                    period: str = "d", start_date: str = None,
                                    end_date: str = None, capital: float = 1_000_000,
                                    train_window: int = 252, test_window: int = 20) -> dict:
        """运行 Walk-Forward 滚动窗口回测"""
        logger.info(f"[MCP Tool] run_gold_walk_forward: {strategy_name}")
        try:
            payload = {
                "strategy_name": strategy_name, "symbol": symbol, "period": period,
                "start_date": start_date, "end_date": end_date, "capital": capital,
                "train_window": train_window, "test_window": test_window,
            }
            result = await self._request("POST", "/gold/trading/backtest/walk-forward", json=payload)
            return result
        except Exception as e:
            logger.error(f"Walk-Forward 回测失败：{e}")
            return {"success": False, "message": f"Walk-Forward 回测失败：{str(e)}", "data": None}

    async def run_gold_cpcv(self, strategy_name: str, symbol: str = "AU0",
                            period: str = "d", start_date: str = None,
                            end_date: str = None, capital: float = 1_000_000,
                            n_groups: int = 6, k_test: int = 2) -> dict:
        """运行 CPCV 组合交叉验证回测"""
        logger.info(f"[MCP Tool] run_gold_cpcv: {strategy_name}")
        try:
            payload = {
                "strategy_name": strategy_name, "symbol": symbol, "period": period,
                "start_date": start_date, "end_date": end_date, "capital": capital,
                "n_groups": n_groups, "k_test": k_test,
            }
            result = await self._request("POST", "/gold/trading/backtest/cpcv", json=payload)
            return result
        except Exception as e:
            logger.error(f"CPCV 回测失败：{e}")
            return {"success": False, "message": f"CPCV 回测失败：{str(e)}", "data": None}

    async def run_gold_monte_carlo(self, strategy_name: str, symbol: str = "AU0",
                                   period: str = "d", start_date: str = None,
                                   end_date: str = None, capital: float = 1_000_000,
                                   n_simulations: int = 1000) -> dict:
        """运行 Monte Carlo 模拟分析策略风险"""
        logger.info(f"[MCP Tool] run_gold_monte_carlo: {strategy_name}")
        try:
            payload = {
                "strategy_name": strategy_name, "symbol": symbol, "period": period,
                "start_date": start_date, "end_date": end_date, "capital": capital,
                "n_simulations": n_simulations,
            }
            result = await self._request("POST", "/gold/trading/backtest/monte-carlo", json=payload)
            return result
        except Exception as e:
            logger.error(f"Monte Carlo 模拟失败：{e}")
            return {"success": False, "message": f"Monte Carlo 模拟失败：{str(e)}", "data": None}

    async def run_gold_triple_barrier_label(self, symbol: str = "AU0", period: str = "d",
                                            start_date: str = None, end_date: str = None,
                                            tp_multiplier: float = 1.5, sl_multiplier: float = 1.0,
                                            max_holding_days: int = 5) -> dict:
        """运行 Triple-Barrier 三屏障标注"""
        logger.info(f"[MCP Tool] run_gold_triple_barrier_label")
        try:
            payload = {
                "symbol": symbol, "period": period,
                "start_date": start_date, "end_date": end_date,
                "tp_multiplier": tp_multiplier, "sl_multiplier": sl_multiplier,
                "max_holding_days": max_holding_days,
            }
            result = await self._request("POST", "/gold/trading/label/triple-barrier", json=payload)
            return result
        except Exception as e:
            logger.error(f"Triple-Barrier 标注失败：{e}")
            return {"success": False, "message": f"Triple-Barrier 标注失败：{str(e)}", "data": None}

    async def get_gold_feature_importance(self, strategy_name: str = "ml_predictor") -> dict:
        """获取 ML 策略特征重要性"""
        logger.info(f"[MCP Tool] get_gold_feature_importance: {strategy_name}")
        try:
            result = await self._request("GET", f"/gold/trading/feature-importance?strategy_name={strategy_name}")
            return result
        except Exception as e:
            logger.error(f"获取特征重要性失败：{e}")
            return {"success": False, "message": f"获取特征重要性失败：{str(e)}", "data": None}

    async def generate_gold_signal(self, strategy_name: str, symbol: str = "AU0") -> dict:
        """手动触发黄金交易信号生成"""
        logger.info(f"[MCP Tool] generate_gold_signal: {strategy_name}")
        try:
            result = await self._request("POST", f"/gold/trading/signal/generate?strategy_name={strategy_name}&symbol={symbol}")
            return result
        except Exception as e:
            logger.error(f"生成交易信号失败：{e}")
            return {"success": False, "message": f"生成交易信号失败：{str(e)}", "data": None}

    async def get_gold_market_data(self) -> dict:
        """获取黄金实时市场数据仪表盘"""
        logger.info(f"[MCP Tool] get_gold_market_data")
        try:
            result = await self._request("GET", "/gold/trading/market-data")
            return result
        except Exception as e:
            logger.error(f"获取市场数据失败：{e}")
            return {"success": False, "message": f"获取市场数据失败：{str(e)}", "data": None}

    async def get_gold_analysis(self, symbol: str = "AU0", period: str = "d", limit: int = 500) -> dict:
        """获取 K 线技术分析解读"""
        logger.info(f"[MCP Tool] get_gold_analysis")
        try:
            result = await self._request("GET", f"/gold/trading/analysis?symbol={symbol}&period={period}&limit={limit}")
            return result
        except Exception as e:
            logger.error(f"获取技术分析失败：{e}")
            return {"success": False, "message": f"获取技术分析失败：{str(e)}", "data": None}

    async def get_gold_config(self) -> dict:
        """获取黄金交易配置参数"""
        logger.info(f"[MCP Tool] get_gold_config")
        try:
            result = await self._request("GET", "/gold/trading/config")
            return result
        except Exception as e:
            logger.error(f"获取配置失败：{e}")
            return {"success": False, "message": f"获取配置失败：{str(e)}", "data": None}
