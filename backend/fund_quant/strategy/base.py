"""FundQuant 策略基类 + 注册表"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Type
from datetime import date
from loguru import logger

from ..core.enums import StrategyType
from ..core.models import FundSignal, StrategyContext, FundDataPoint, Portfolio, InformationSet


class FundStrategyBase(ABC):
    """基金量化策略基类"""

    strategy_name: str = ""
    strategy_type: str = ""
    description: str = ""
    default_params: dict = {}
    param_ranges: dict = {}
    applicable_fund_types: list = []
    min_history_days: int = 60
    _state: dict = {}

    def __init__(self, params: Optional[dict] = None):
        merged = {**self.default_params, **(params or {})}
        self.params = merged
        self._state = {}

    def on_init(self, context: StrategyContext):
        """策略初始化"""

    def on_data(self, data: FundDataPoint):
        """数据更新回调"""

    @abstractmethod
    def on_evaluate(self, portfolio: Optional[Portfolio],
                    info_set: Optional[InformationSet]) -> List[FundSignal]:
        """策略评估"""

    def emit_signal(self, signal_type, fund_code: str,
                    direction, confidence: float,
                    reason: str, **kwargs) -> FundSignal:
        """发射信号"""
        import uuid
        return FundSignal(
            signal_id=f"{self.strategy_name}_{uuid.uuid4().hex[:8]}",
            fund_code=fund_code,
            signal_type=signal_type,
            direction=direction,
            confidence=min(max(confidence, 0.0), 1.0),
            reason=reason,
            strategy_name=self.strategy_name,
            **kwargs,
        )

    def save_state(self) -> dict:
        return self._state.copy()

    def load_state(self, state: dict):
        self._state = state


class StrategyRegistry:
    """策略注册表（单例）"""
    _instance = None
    _strategies: Dict[str, Type[FundStrategyBase]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._discover_strategies()
        return cls._instance

    def _discover_strategies(self):
        """自动发现已导入的策略类"""
        pass

    @classmethod
    def register(cls, strategy_cls: Type[FundStrategyBase]):
        """注册策略类"""
        name = strategy_cls.strategy_name
        if not name:
            logger.warning(f"策略类 {strategy_cls.__name__} 缺少 strategy_name")
            return
        cls._strategies[name] = strategy_cls
        logger.debug(f"策略已注册: {name} ({strategy_cls.strategy_type})")

    def get_strategy(self, name: str) -> Optional[FundStrategyBase]:
        """获取策略实例"""
        cls = self._strategies.get(name)
        if cls:
            return cls()
        return None

    def get_strategy_class(self, name: str) -> Optional[Type[FundStrategyBase]]:
        return self._strategies.get(name)

    def list_strategies(self) -> List[dict]:
        """列出所有已注册策略"""
        return [
            {
                "name": cls.strategy_name,
                "type": cls.strategy_type,
                "description": cls.description,
                "default_params": cls.default_params,
                "applicable_fund_types": cls.applicable_fund_types,
            }
            for cls in self._strategies.values()
        ]

    def list_by_type(self, strategy_type: StrategyType) -> List[dict]:
        """按类型列出策略"""
        return [
            s for s in self.list_strategies()
            if s["type"] == strategy_type.value or s["type"] == strategy_type
        ]
