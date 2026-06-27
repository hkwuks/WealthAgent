"""
黄金量化系统错误码定义

规范: 模块_具体错误
级别: DATA_ / STRATEGY_ / BACKTEST_ / RISK_ / SIGNAL_ / SYSTEM_
"""


class GoldTradingError(Exception):
    """黄金量化系统基础异常"""

    def __init__(self, code: str, message: str, detail: dict = None):
        self.code = code
        self.message = message
        self.detail = detail or {}
        super().__init__(f"[{code}] {message}")

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message, "detail": self.detail}


# ===== 数据层 =====
class DataFetchError(GoldTradingError):
    def __init__(self, detail: dict = None):
        super().__init__("DATA_FETCH_FAILED", "数据获取失败", detail)


class DataQualityError(GoldTradingError):
    def __init__(self, detail: dict = None):
        super().__init__("DATA_QUALITY_FAILED", "数据质量检查未通过", detail)


# ===== 策略层 =====
class StrategyNotFoundError(GoldTradingError):
    def __init__(self, name: str):
        super().__init__("STRATEGY_NOT_FOUND", f"策略 '{name}' 不存在")


class StrategyParamError(GoldTradingError):
    def __init__(self, msg: str):
        super().__init__("STRATEGY_PARAM_INVALID", msg)


# ===== 回测层 =====
class BacktestError(GoldTradingError):
    def __init__(self, msg: str, detail: dict = None):
        super().__init__("BACKTEST_FAILED", msg, detail)


# ===== 风控层 =====
class RiskRejectError(GoldTradingError):
    def __init__(self, reason: str):
        super().__init__("RISK_REJECTED", f"风控拒绝: {reason}")


# ===== 信号层 =====
class SignalRejectError(GoldTradingError):
    def __init__(self, reason: str = "信号验证不通过"):
        super().__init__("SIGNAL_REJECTED", reason)


# ===== 系统层 =====
class ConfigError(GoldTradingError):
    def __init__(self, msg: str):
        super().__init__("CONFIG_ERROR", msg)
