"""
MCP Server 主模块

使用 FastMCP 创建 MCP 服务器，并集成到 FastAPI 应用中
"""

from mcp.server.fastmcp import FastMCP
from backend.mcp_server.tools import FundValuationTools
from backend.mcp_server.resources import FundValuationResources
from backend.mcp_server.prompts import FundValuationPrompts
from loguru import logger


def create_mcp_server() -> FastMCP:
    """
    创建并配置 MCP 服务器

    Returns:
        FastMCP: 配置好的 MCP 服务器实例

    注意：
        此 MCP 服务器设计为挂载到 FastAPI 应用中使用，
        不需要独立运行 HTTP 服务器。

        streamable_http_path='/' 确保挂载到 FastAPI 的 /mcp 后，
        最终访问路径就是 /mcp
    """
    # 创建 MCP 服务器实例
    # streamable_http_path='/' 确保挂载到 FastAPI 后路径正确
    mcp = FastMCP(
        name="fund-valuation",
        instructions="""
智能理财Agent MCP 服务器

提供以下功能：
1. 基金管理 - 查询、添加、删除基金
2. 基金估值 - 实时估算基金净值和涨跌幅
3. 市场数据 - 查询股票、ETF、指数行情

支持的基金类型：
- 场内 ETF（实时价格估值）
- 指数基金（基于跟踪指数估值）
- 主动股票型基金（基于持仓估值）
- QDII 基金（混合估值）
        """,
        streamable_http_path='/',
    )

    # 注册 Tools
    _register_tools(mcp)

    # 注册 Resources
    _register_resources(mcp)

    # 注册 Prompts
    _register_prompts(mcp)

    logger.info("MCP 服务器初始化完成")

    return mcp


def _register_tools(mcp: FastMCP):
    """注册所有 MCP Tools"""
    tools = FundValuationTools()

    @mcp.tool()
    async def get_fund_list() -> dict:
        """获取当前持仓基金列表"""
        return await tools.get_fund_list()

    @mcp.tool()
    async def add_fund(fund_code: str, fund_name: str, fund_type: str, total_shares: float) -> dict:
        """
        添加新基金到持仓列表

        Args:
            fund_code: 基金代码（如 110022, 510300）
            fund_name: 基金名称
            fund_type: 基金类型（如 ETF, 指数基金，股票型，混合型，QDII 等）
            total_shares: 持有份额
        """
        return await tools.add_fund(fund_code, fund_name, fund_type, total_shares)

    @mcp.tool()
    async def delete_fund(fund_code: str) -> dict:
        """
        从持仓列表中删除基金

        Args:
            fund_code: 基金代码
        """
        return await tools.delete_fund(fund_code)

    @mcp.tool()
    async def get_fund_info(fund_code: str) -> dict:
        """
        获取基金详细信息

        Args:
            fund_code: 基金代码
        """
        return await tools.get_fund_info(fund_code)

    @mcp.tool()
    async def get_valuation(fund_code: str, prefer_holdings: bool = True) -> dict:
        """
        获取基金实时估值

        Args:
            fund_code: 基金代码
            prefer_holdings: 是否优先使用持仓估值（默认 True）
        """
        return await tools.get_valuation(fund_code, prefer_holdings)

    @mcp.tool()
    async def get_batch_valuation(fund_codes: list[str], prefer_holdings: bool = True) -> dict:
        """
        批量获取基金估值

        Args:
            fund_codes: 基金代码列表
            prefer_holdings: 是否优先使用持仓估值
        """
        return await tools.get_batch_valuation(fund_codes, prefer_holdings)

    @mcp.tool()
    async def get_stock_price(stock_code: str) -> dict:
        """
        获取 A 股股票实时行情

        Args:
            stock_code: 股票代码（如 600519, 000858）
        """
        return await tools.get_stock_price(stock_code)

    @mcp.tool()
    async def get_etf_price(etf_code: str) -> dict:
        """
        获取场内 ETF 实时行情

        Args:
            etf_code: ETF 代码（如 510300, 159915）
        """
        return await tools.get_etf_price(etf_code)

    @mcp.tool()
    async def get_index_price(index_code: str) -> dict:
        """
        获取国内指数实时行情

        Args:
            index_code: 指数代码（如 000300, 000905, 399006）
        """
        return await tools.get_index_price(index_code)

    @mcp.tool()
    async def get_global_index_price(index_code: str) -> dict:
        """
        获取海外指数实时行情

        Args:
            index_code: 指数代码（如 nasdaq, sp500, hsi, n225）
        """
        return await tools.get_global_index_price(index_code)

    @mcp.tool()
    async def get_valuation_types() -> dict:
        """获取支持的估值类型说明"""
        return await tools.get_valuation_types()

    @mcp.tool()
    async def get_supported_indices() -> dict:
        """获取支持的指数列表"""
        return await tools.get_supported_indices()

    @mcp.tool()
    async def get_gold_prediction(symbol: str = "GC", horizon_days: int = 1, model_type: str = "lightgbm") -> dict:
        """
        获取黄金价格预测

        Args:
            symbol: 黄金交易代码（默认 GC）
            horizon_days: 预测天数（1, 5, 20）
            model_type: 模型类型（lightgbm, xgboost, ridge）
        """
        return await tools.get_gold_prediction(symbol, horizon_days, model_type)

    @mcp.tool()
    async def get_gold_tb_prediction(symbol: str = "GC", model_type: str = "lightgbm") -> dict:
        """
        获取 Triple-Barrier 方向预测（看涨/看跌概率+止盈止损价格）

        Args:
            symbol: 黄金交易代码（默认 GC）
            model_type: 模型类型（lightgbm, xgboost, ridge）
        """
        return await tools.get_gold_tb_prediction(symbol, model_type)

    @mcp.tool()
    async def get_gold_price() -> dict:
        """获取当前黄金价格和宏观指标"""
        return await tools.get_gold_price()

    @mcp.tool()
    async def run_gold_backtest(years: int = 1, model_types: str = "lightgbm,xgboost,ridge", method: str = "walk_forward") -> dict:
        """
        运行黄金预测模型回测

        Args:
            years: 回测年数（1, 2, 3）
            model_types: 模型类型，逗号分隔（默认所有模型）
            method: 回测方法（walk_forward 或 cpcv）
        """
        return await tools.run_gold_backtest(years, model_types, method)

    @mcp.tool()
    async def get_gold_drift_status(model_type: str = None, horizon_days: int = None) -> dict:
        """
        获取模型漂移检测状态

        Args:
            model_type: 模型类型（可选，lightgbm/xgboost/ridge）
            horizon_days: 预测周期（可选，1/5/20）
        """
        return await tools.get_gold_drift_status(model_type, horizon_days)

    @mcp.tool()
    async def get_gold_factor_importance(model_type: str = "lightgbm", horizon_days: int = 1) -> dict:
        """
        获取黄金预测因子重要性

        Args:
            model_type: 模型类型（默认 lightgbm）
            horizon_days: 预测周期（默认 1）
        """
        return await tools.get_gold_factor_importance(model_type, horizon_days)

    @mcp.tool()
    async def get_gold_trend_signal(symbol: str = "GC") -> dict:
        """
        获取黄金趋势跟踪信号（MA交叉+ATR止损）

        Args:
            symbol: 黄金交易代码（默认 GC）
        """
        return await tools.get_gold_trend_signal(symbol)

    @mcp.tool()
    async def run_gold_trend_backtest(years: int = 2, fast_ma: int = 50, slow_ma: int = 200, sl_multiplier: float = 2.0) -> dict:
        """
        运行趋势跟踪策略回测

        Args:
            years: 回测年数
            fast_ma: 快速MA天数（默认50）
            slow_ma: 慢速MA天数（默认200）
            sl_multiplier: ATR止损倍数（默认2.0）
        """
        return await tools.run_gold_trend_backtest(years, fast_ma, slow_ma, sl_multiplier)

    # ===== 黄金量化交易 MCP Tools =====

    @mcp.tool()
    async def get_gold_strategies() -> dict:
        """获取黄金量化策略列表及描述"""
        return await tools.get_gold_strategies()

    @mcp.tool()
    async def get_gold_signals(strategy_name: str = None, limit: int = 20) -> dict:
        """
        获取最近黄金交易建议信号

        Args:
            strategy_name: 策略名称过滤（可选）
            limit: 返回数量限制（默认20）
        """
        return await tools.get_gold_signals(strategy_name, limit)

    @mcp.tool()
    async def run_gold_strategy_backtest(strategy_name: str = "trend_following",
                                          start_date: str = "2024-01-01",
                                          end_date: str = "2024-12-31",
                                          capital: float = 1000000) -> dict:
        """
        运行黄金量化策略回测（趋势跟踪/均值回归/ML预测）

        Args:
            strategy_name: 策略名称（trend_following/mean_reversion/ml_predictor）
            start_date: 开始日期（默认2024-01-01）
            end_date: 结束日期（默认2024-12-31）
            capital: 回测资金（默认1000000）
        """
        return await tools.run_gold_strategy_backtest(strategy_name, start_date, end_date, capital)

    @mcp.tool()
    async def compare_gold_strategies(strategy_names: str = "trend_following,mean_reversion,ml_predictor",
                                       start_date: str = "2024-01-01",
                                       end_date: str = "2024-12-31") -> dict:
        """
        多策略对比回测

        Args:
            strategy_names: 策略名称，逗号分隔
            start_date: 开始日期
            end_date: 结束日期
        """
        names = [s.strip() for s in strategy_names.split(",")]
        return await tools.compare_gold_strategies(names, start_date, end_date)

    @mcp.tool()
    async def get_gold_risk_status() -> dict:
        """获取黄金交易风控状态"""
        return await tools.get_gold_risk_status()


def _register_resources(mcp: FastMCP):
    """注册所有 MCP Resources"""
    resources = FundValuationResources()

    @mcp.resource("fund://{fund_code}")
    async def get_fund_resource(fund_code: str) -> str:
        """获取基金详细信息资源"""
        return await resources.get_fund_resource(fund_code)

    @mcp.resource("valuation://{fund_code}")
    async def get_valuation_resource(fund_code: str) -> str:
        """获取基金实时估值资源"""
        return await resources.get_valuation_resource(fund_code)

    @mcp.resource("market://stock/{stock_code}")
    async def get_stock_resource(stock_code: str) -> str:
        """获取股票行情资源"""
        return await resources.get_stock_resource(stock_code)

    @mcp.resource("market://etf/{etf_code}")
    async def get_etf_resource(etf_code: str) -> str:
        """获取 ETF 行情资源"""
        return await resources.get_etf_resource(etf_code)

    @mcp.resource("market://index/{index_code}")
    async def get_index_resource(index_code: str) -> str:
        """获取指数行情资源"""
        return await resources.get_index_resource(index_code)

    @mcp.resource("market://global-index/{index_code}")
    async def get_global_index_resource(index_code: str) -> str:
        """获取海外指数行情资源"""
        return await resources.get_global_index_resource(index_code)


def _register_prompts(mcp: FastMCP):
    """注册所有 MCP Prompts"""
    prompts = FundValuationPrompts()

    @mcp.prompt()
    def analyze_fund(fund_code: str) -> str:
        """
        分析单只基金的投资价值

        Args:
            fund_code: 基金代码
        """
        return prompts.analyze_fund(fund_code)

    @mcp.prompt()
    def portfolio_summary() -> str:
        """生成持仓组合总结报告"""
        return prompts.portfolio_summary()

    @mcp.prompt()
    def market_daily() -> str:
        """生成市场日报"""
        return prompts.market_daily()


# 导出工具类，供外部使用
__all__ = ["create_mcp_server"]
