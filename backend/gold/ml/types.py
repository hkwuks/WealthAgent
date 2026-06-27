"""ML 模型类型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List


class ModelType(Enum):
    """模型类型"""
    LIGHTGBM = "lightgbm"
    XGBOOST = "xgboost"
    RIDGE = "ridge"


class PredictionHorizon(Enum):
    """预测周期"""
    SHORT = 1      # 1天
    MEDIUM = 5     # 1周
    LONG = 20      # 1月


@dataclass
class PredictionResult:
    """预测结果"""
    asset_code: str
    current_price: float
    predicted_price: float
    predicted_change: float
    predicted_change_percent: float
    confidence: float
    horizon: int
    model_type: str
    features_used: List[str]
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TripleBarrierResult:
    """Triple-Barrier 标注结果"""
    asset_code: str
    current_price: float
    direction: int              # 1=看涨, -1=看跌, 0=中性
    direction_probability: float  # 方向概率 [0, 1]
    tp_level: float             # 止盈价格
    sl_level: float             # 止损价格
    max_holding_days: int       # 最大持有期
    atr_value: float            # 当前ATR值
    confidence: float
    model_type: str
    features_used: List[str]
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
