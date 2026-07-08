"""FundQuant 异常定义"""


class FundQuantError(Exception):
    """FundQuant 基类异常"""
    def __init__(self, message: str, error_code: str = "FUND_QUANT_ERROR"):
        self.error_code = error_code
        self.message = message
        super().__init__(self.message)


# --- 数据层异常 ---
class DataError(FundQuantError):
    """数据层基类异常"""
    def __init__(self, message: str, error_code: str = "DATA_ERROR"):
        super().__init__(message, error_code)


class DataCollectionError(DataError):
    """数据采集异常"""
    def __init__(self, message: str, fund_code: str = ""):
        super().__init__(
            f"数据采集失败 [{fund_code}]: {message}" if fund_code else f"数据采集失败: {message}",
            "DATA_COLLECTION_ERROR",
        )


class DataQualityError(DataError):
    """数据质量异常"""
    def __init__(self, message: str):
        super().__init__(f"数据质量问题: {message}", "DATA_QUALITY_ERROR")


class StorageError(DataError):
    """存储层异常"""
    def __init__(self, message: str):
        super().__init__(f"存储错误: {message}", "STORAGE_ERROR")


# --- 策略层异常 ---
class StrategyError(FundQuantError):
    """策略层基类异常"""
    def __init__(self, message: str, error_code: str = "STRATEGY_ERROR"):
        super().__init__(message, error_code)


class StrategyNotFoundError(StrategyError):
    """策略未找到"""
    def __init__(self, strategy_name: str):
        super().__init__(f"策略未找到: {strategy_name}", "STRATEGY_NOT_FOUND")


class StrategyParamError(StrategyError):
    """策略参数错误"""
    def __init__(self, message: str):
        super().__init__(f"策略参数错误: {message}", "STRATEGY_PARAM_ERROR")


class StrategyRuntimeError(StrategyError):
    """策略运行时异常"""
    def __init__(self, strategy_name: str, message: str):
        super().__init__(
            f"策略 [{strategy_name}] 运行时异常: {message}",
            "STRATEGY_RUNTIME_ERROR",
        )


# --- 风控层异常 ---
class RiskError(FundQuantError):
    """风控层基类异常"""
    def __init__(self, message: str, error_code: str = "RISK_ERROR"):
        super().__init__(message, error_code)


class RiskCheckFailed(RiskError):
    """风控检查未通过"""
    def __init__(self, check_name: str, reason: str):
        super().__init__(
            f"风控检查 [{check_name}] 未通过: {reason}",
            "RISK_CHECK_FAILED",
        )


# --- 回测层异常 ---
class BacktestError(FundQuantError):
    """回测层基类异常"""
    def __init__(self, message: str, error_code: str = "BACKTEST_ERROR"):
        super().__init__(message, error_code)


class BacktestConfigError(BacktestError):
    """回测配置错误"""
    def __init__(self, message: str):
        super().__init__(f"回测配置错误: {message}", "BACKTEST_CONFIG_ERROR")


class LookAheadBiasError(BacktestError):
    """前视偏差检测"""
    def __init__(self, message: str):
        super().__init__(f"前视偏差风险: {message}", "LOOK_AHEAD_BIAS")


# --- 信号层异常 ---
class SignalError(FundQuantError):
    """信号层基类异常"""
    def __init__(self, message: str, error_code: str = "SIGNAL_ERROR"):
        super().__init__(message, error_code)
