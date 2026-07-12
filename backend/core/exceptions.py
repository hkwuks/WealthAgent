"""AuroraCore 基础异常层级"""
from typing import Optional


class AuroraCoreError(Exception):
    """所有 AuroraCore 异常的基类"""
    pass


class ConfigError(AuroraCoreError):
    """配置错误"""
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message)
        self.field = field


class DataError(AuroraCoreError):
    """数据错误"""
    def __init__(self, message: str, symbol: Optional[str] = None):
        super().__init__(message)
        self.symbol = symbol


class SignalError(AuroraCoreError):
    """信号错误"""
    pass


class RiskError(AuroraCoreError):
    """风控拒绝"""
    def __init__(self, message: str, check_name: Optional[str] = None):
        super().__init__(message)
        self.check_name = check_name


class StrategyError(AuroraCoreError):
    """策略错误"""
    pass


class ExecutionError(AuroraCoreError):
    """执行错误"""
    pass


class ValidationError(AuroraCoreError):
    """验证错误"""
    pass
