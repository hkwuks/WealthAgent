from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime

from backend.gold.core.models import (
    GoldSignal, GoldBarData, GoldPosition, SignalDirection,
)


class StrategyContext:
    """
    策略运行上下文 — 回测和信号模式共用接口

    回测模式: BacktestStrategyContext（模拟撮合）
    信号模式: SignalStrategyContext（仅记录信号，不撮合）
    """

    @property
    def mode(self) -> str:
        raise NotImplementedError

    def on_signal(self, signal: GoldSignal):
        raise NotImplementedError

    def get_position(self, symbol: str) -> Optional[GoldPosition]:
        raise NotImplementedError

    def get_balance(self) -> float:
        raise NotImplementedError


class StrategyBase(ABC):
    """
    策略基类 — 不依赖VeighNa，轻量设计

    子类需实现:
    - on_init(context): 初始化
    - on_bar(bar): K线回调，策略主逻辑

    子类可调用:
    - emit_signal(): 输出交易信号
    - get_position(): 查询当前持仓
    """

    strategy_name: str = ""
    strategy_type: str = ""
    description: str = ""
    default_params: dict = {}
    param_ranges: dict = {}

    def __init__(self, **kwargs):
        for key, value in {**self.default_params, **kwargs}.items():
            setattr(self, key, value)
        self._context: Optional[StrategyContext] = None
        self._signals: list[GoldSignal] = []

    def set_context(self, context: StrategyContext):
        self._context = context

    @abstractmethod
    def on_init(self, context: StrategyContext):
        ...

    @abstractmethod
    def on_bar(self, bar: GoldBarData):
        ...

    def emit_signal(self, direction: SignalDirection, symbol: str,
                    price: float, volume: int = 1,
                    stop_loss: float = None, take_profit: float = None,
                    confidence: float = 0.0, reason: str = "",
                    bar_datetime: datetime = None):
        """输出交易信号"""
        now = bar_datetime or datetime.now()
        signal = GoldSignal(
            signal_id=f"{self.strategy_name}_{now.strftime('%Y%m%d%H%M%S')}_{len(self._signals)}",
            strategy_id=self.strategy_name,
            strategy_name=self.strategy_name,
            symbol=symbol,
            direction=direction,
            price=price,
            volume=volume,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=confidence,
            reason=reason,
            created_at=now,
        )

        if not self._validate_signal(signal):
            return

        self._signals.append(signal)
        if self._context:
            self._context.on_signal(signal)

    def get_position(self, symbol: str) -> Optional[GoldPosition]:
        if self._context:
            return self._context.get_position(symbol)
        return None

    def _validate_signal(self, signal: GoldSignal) -> bool:
        if signal.volume <= 0:
            return False
        if signal.price <= 0:
            return False
        if signal.stop_loss and signal.direction == SignalDirection.LONG:
            if signal.stop_loss >= signal.price:
                return False
        if signal.stop_loss and signal.direction == SignalDirection.SHORT:
            if signal.stop_loss <= signal.price:
                return False
        return True


class StrategyRegistry:
    """策略注册表"""
    _strategies: dict[str, type] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(strategy_class):
            cls._strategies[name] = strategy_class
            return strategy_class
        return decorator

    @classmethod
    def get(cls, name: str) -> Optional[type]:
        return cls._strategies.get(name)

    @classmethod
    def list_all(cls) -> dict[str, type]:
        return cls._strategies.copy()
