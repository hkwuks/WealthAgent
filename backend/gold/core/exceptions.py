class GoldTradingError(Exception):
    """黄金量化交易基础异常"""
    pass


class StrategyError(GoldTradingError):
    """策略异常"""
    pass


class DataError(GoldTradingError):
    """数据异常"""
    pass


class RiskCheckError(GoldTradingError):
    """风控异常"""
    pass
