"""信号层 — Signal, Order, Fill, Position, Direction"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Direction(str, Enum):
    """交易方向 — 资产不可知"""
    LONG = "long"
    SHORT = "short"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"
    HOLD = "hold"


class OrderStatus(str, Enum):
    """订单状态机"""
    PENDING = "pending"      # 待处理
    ACCEPTED = "accepted"    # 风控通过
    REJECTED = "rejected"    # 风控拒绝
    PARTIAL = "partial"      # 部分成交
    FILLED = "filled"        # 全部成交
    CANCELLED = "cancelled"  # 撤销


@dataclass
class Signal:
    """策略输出信号"""
    id: str
    strategy: str
    symbol: str
    direction: Direction
    price: float
    volume: float
    confidence: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    reason: str = ""
    created_at: datetime | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class Order:
    """订单 — 执行引擎内部状态"""
    id: str
    signal_id: str
    symbol: str
    direction: Direction
    price: float
    volume: float
    filled_volume: float = 0
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Fill:
    """成交记录"""
    order_id: str
    price: float
    volume: float
    commission: float = 0
    slippage: float = 0
    timestamp: datetime | None = None


@dataclass
class Position:
    """持仓快照"""
    symbol: str
    direction: Direction
    volume: float
    avg_price: float
    unrealized_pnl: float = 0
    realized_pnl: float = 0


class SignalLifecycle:
    """信号状态机 — 信号转化漏斗统计

    >>> sl = SignalLifecycle()
    >>> sl.on_generate("s1")
    >>> sl.on_risk_pass("s1")
    >>> sl.on_fill("o1")
    >>> sl.stats["generated"]
    1
    """
    def __init__(self):
        self._state: dict[str, set[str]] = {
            "generated": set(),
            "risk_passed": set(),
            "risk_rejected": set(),
            "executed": set(),
            "filled": set(),
        }

    def on_generate(self, signal_id: str) -> None:
        self._state["generated"].add(signal_id)

    def on_risk_pass(self, signal_id: str) -> None:
        self._state["risk_passed"].add(signal_id)

    def on_risk_reject(self, signal_id: str, reason: str = "") -> None:
        self._state["risk_rejected"].add(signal_id)

    def on_execute(self, signal_id: str) -> None:
        self._state["executed"].add(signal_id)

    def on_fill(self, signal_id: str) -> None:
        self._state["filled"].add(signal_id)

    @property
    def stats(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._state.items()}


def demo():
    """数据模型自检"""
    s = Signal(id="s1", strategy="momentum", symbol="AU0",
               direction=Direction.LONG, price=600.0, volume=1)
    assert s.direction == Direction.LONG
    assert s.confidence == 0.0  # default

    o = Order(id="o1", signal_id="s1", symbol="AU0",
              direction=Direction.LONG, price=600.0, volume=1)
    assert o.status == OrderStatus.PENDING

    f = Fill(order_id="o1", price=600.5, volume=1, commission=10.0)
    assert f.commission == 10.0

    p = Position(symbol="AU0", direction=Direction.LONG, volume=1, avg_price=600.0)
    assert p.volume == 1

    # SignalLifecycle
    sl = SignalLifecycle()
    sl.on_generate("s1")
    sl.on_risk_pass("s1")
    sl.on_fill("o1")
    assert sl.stats["generated"] == 1
    assert sl.stats["filled"] == 1

    print("[signal] ✅ 数据模型 + SignalLifecycle 通过")


if __name__ == "__main__":
    demo()
