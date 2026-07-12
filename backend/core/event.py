"""事件驱动核心 — EventBus 发布/订阅"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable


class EventType(str, Enum):
    """标准事件类型"""
    BAR_RECEIVED = "bar.received"
    SIGNAL_GENERATED = "signal.generated"
    SIGNAL_RISK_PASS = "signal.risk_pass"
    SIGNAL_RISK_REJECT = "signal.risk_reject"
    ORDER_SUBMITTED = "order.submitted"
    ORDER_ACCEPTED = "order.accepted"
    ORDER_PARTIAL = "order.partial"
    ORDER_FILLED = "order.filled"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_REJECTED = "order.rejected"
    TRADE_CLOSED = "trade.closed"
    DAILY_SETTLEMENT = "daily.settlement"
    ENGINE_STOP = "engine.stop"


@dataclass
class Event:
    """事件"""
    type: EventType
    payload: Any
    source: str = ""
    timestamp: datetime | None = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


Handler = Callable[["Event"], None]


class EventBus:
    """事件总线 — 发布/订阅，回测与实盘共用

    >>> bus = EventBus()
    >>> collected = []
    >>> bus.subscribe(EventType.ENGINE_STOP, lambda e: collected.append(e))
    >>> bus.publish(Event(EventType.ENGINE_STOP, {"code": 0}))
    >>> len(collected) == 1
    True
    >>> collected[0].payload["code"]
    0
    """

    def __init__(self):
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)
        self._history: list[Event] = []

    def subscribe(self, event_type: EventType, handler: Handler):
        self._subscribers[event_type.value].append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler):
        self._subscribers[event_type.value].remove(handler)

    def publish(self, event: Event):
        for handler in self._subscribers.get(event.type.value, []):
            handler(event)
        self._history.append(event)

    def replay(self, since: int = 0):
        """回放历史事件 — 调试/回溯用"""
        for event in self._history[since:]:
            yield event


def demo():
    """E2E 自检"""
    bus = EventBus()
    seen = []

    bus.subscribe(EventType.BAR_RECEIVED, lambda e: seen.append(("bar", e.payload)))
    bus.subscribe(EventType.ENGINE_STOP, lambda e: seen.append(("stop", e.payload)))

    bus.publish(Event(EventType.BAR_RECEIVED, {"close": 100.5}, source="test"))
    bus.publish(Event(EventType.ENGINE_STOP, {"reason": "done"}, source="test"))

    assert len(seen) == 2, f"expected 2 events, got {len(seen)}"
    assert seen[0] == ("bar", {"close": 100.5})
    assert seen[1] == ("stop", {"reason": "done"})
    assert len(list(bus.replay())) == 2

    print("[event] ✅ EventBus 基础功能通过")


if __name__ == "__main__":
    demo()
