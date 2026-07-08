"""FundQuant 枚举定义"""

from enum import Enum


class SignalType(str, Enum):
    """信号类型"""
    TIMING = "timing"
    SELECTION = "selection"
    ALLOCATION = "allocation"
    RISK = "risk"


class Direction(str, Enum):
    """信号方向"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    REBALANCE = "rebalance"


class FundType(str, Enum):
    """基金类型"""
    STOCK = "stock"
    HYBRID = "hybrid"
    BOND = "bond"
    INDEX = "index"
    QDII = "qdii"
    MONEY = "money"
    FOF = "fof"
    ETF = "etf"
    ETF_LINK = "etf_link"


class StrategyType(str, Enum):
    """策略类型"""
    TIMING = "timing"
    SELECTION = "selection"
    ALLOCATION = "allocation"


class RiskLevel(str, Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidenceLevel(str, Enum):
    """置信度等级"""
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class DataQuality(str, Enum):
    """数据质量标记"""
    GOOD = "good"
    STALE = "stale"
    SUSPICIOUS = "suspicious"
    MISSING = "missing"
    ERROR = "error"
