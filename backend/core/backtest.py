"""回测引擎 — BacktestEngine + ExecutionEngine + CostModel + SlippageModel"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from .signal import Direction, Order, OrderStatus, Fill, Position, Signal
from .strategy import Strategy, StrategyContext
from .event import Event, EventType, EventBus

if TYPE_CHECKING:
    from .event import EventBus, EventType
    from .data import Bar, FundNavPoint
    from .strategy import Strategy, StrategyContext
    from .config import BacktestConfig


# ═══════════════════════════════════════════
# 滑点模型
# ═══════════════════════════════════════════

class SlippageModel(ABC):
    @abstractmethod
    def apply(self, signal: Signal, bar: Bar) -> tuple[float, float]:
        """返回 (成交价, 滑点成本)"""
        ...


class NoSlippage(SlippageModel):
    def apply(self, signal: Signal, bar: Bar) -> tuple[float, float]:
        return bar.close, 0.0


class PercentageSlippage(SlippageModel):
    def __init__(self, pct: float = 0.001):
        self.pct = pct

    def apply(self, signal: Signal, bar: Bar) -> tuple[float, float]:
        if signal.direction in (Direction.LONG, Direction.CLOSE_SHORT):
            price = bar.close * (1 + self.pct)
        else:
            price = bar.close * (1 - self.pct)
        return price, abs(price - bar.close)


# ═══════════════════════════════════════════
# 成本模型
# ═══════════════════════════════════════════

class CostModel(ABC):
    @abstractmethod
    def calc(self, signal: Signal, fill: Fill) -> float:
        """返回交易成本"""
        ...


class NoCost(CostModel):
    def calc(self, signal: Signal, fill: Fill) -> float:
        return 0.0


# ═══════════════════════════════════════════
# 执行引擎
# ═══════════════════════════════════════════

class ExecutionEngine(ABC):
    """执行引擎 — 订单生命周期管理 + 持仓追踪"""

    @abstractmethod
    def submit(self, signal: Signal) -> Order: ...
    @abstractmethod
    def cancel(self, order_id: str) -> bool: ...
    @abstractmethod
    def get_order(self, order_id: str) -> Order | None: ...
    @abstractmethod
    def get_position(self, symbol: str) -> Position | None: ...
    @abstractmethod
    def positions(self) -> list[Position]: ...
    @abstractmethod
    def on_bar(self, bar: Bar) -> list[Fill]:
        """处理待成交订单，返回本根 bar 产生的成交"""
        ...


class SimExecutionEngine(ExecutionEngine):
    """回测执行引擎 — bar close 成交 + 滑点模型"""

    def __init__(self, slippage: SlippageModel | None = None,
                 fill_ratio: float = 1.0):
        self._slippage = slippage or NoSlippage()
        self._fill_ratio = fill_ratio
        self._orders: dict[str, Order] = {}
        self._pending: dict[str, Signal] = {}
        self._positions: dict[str, Position] = {}
        self._fills: list[Fill] = []

    def submit(self, signal: Signal) -> Order:
        oid = f"o_{signal.id}"
        order = Order(
            id=oid, signal_id=signal.id, symbol=signal.symbol,
            direction=signal.direction, price=signal.price,
            volume=signal.volume, status=OrderStatus.ACCEPTED,
        )
        self._orders[oid] = order
        self._pending[oid] = signal
        return order

    def cancel(self, order_id: str) -> bool:
        if order_id in self._pending:
            self._orders[order_id].status = OrderStatus.CANCELLED
            del self._pending[order_id]
            return True
        return False

    def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def get_position(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    def positions(self) -> list[Position]:
        return list(self._positions.values())

    def on_bar(self, bar: Bar) -> list[Fill]:
        fills: list[Fill] = []
        for oid, signal in list(self._pending.items()):
            order = self._orders[oid]
            vol = signal.volume * self._fill_ratio
            if vol < 0.01:
                order.status = OrderStatus.REJECTED
                del self._pending[oid]
                continue

            price, slippage = self._slippage.apply(signal, bar)
            fill = Fill(
                order_id=oid, price=round(price, 4), volume=vol,
                slippage=round(slippage, 4),
            )
            order.filled_volume = vol
            order.status = OrderStatus.FILLED
            fills.append(fill)
            self._fills.append(fill)

            # 更新持仓
            self._apply_fill(signal, fill)
            del self._pending[oid]

        return fills

    def _apply_fill(self, signal: Signal, fill: Fill):
        pos = self._positions.get(signal.symbol)
        direction = signal.direction

        # 平仓方向 → 减少对应持仓
        if direction in (Direction.CLOSE_LONG, Direction.CLOSE_SHORT):
            close_dir = Direction.LONG if direction == Direction.CLOSE_LONG else Direction.SHORT
            if pos and pos.direction == close_dir and pos.volume > 0:
                avg_cost = pos.avg_price * pos.volume
                fill_cost = fill.price * fill.volume
                pos.realized_pnl += avg_cost - fill_cost if direction == Direction.CLOSE_LONG else fill_cost - avg_cost
                pos.volume -= fill.volume
                if pos.volume <= 0:
                    self._positions.pop(signal.symbol, None)
            return

        # 开仓方向
        if direction in (Direction.LONG, Direction.SHORT):
            if pos is None:
                self._positions[signal.symbol] = Position(
                    symbol=signal.symbol, direction=direction,
                    volume=fill.volume, avg_price=fill.price,
                )
            else:
                # 加仓
                total = pos.avg_price * pos.volume + fill.price * fill.volume
                pos.volume += fill.volume
                pos.avg_price = total / pos.volume


class T1ExecutionEngine(ExecutionEngine):
    """T+1 确认执行引擎（基金）"""

    def __init__(self, confirmation_delay: int = 1):
        self._delay = confirmation_delay
        self._orders: dict[str, Order] = {}
        self._pending: dict[str, tuple[Signal, int]] = {}  # signal -> bars_waited
        self._positions: dict[str, Position] = {}
        self._all_fills: list[Fill] = []

    def submit(self, signal: Signal) -> Order:
        oid = f"o_{signal.id}"
        order = Order(id=oid, signal_id=signal.id, symbol=signal.symbol,
                      direction=signal.direction, price=signal.price,
                      volume=signal.volume, status=OrderStatus.ACCEPTED)
        self._orders[oid] = order
        self._pending[oid] = (signal, 0)
        return order

    def cancel(self, order_id: str) -> bool:
        if order_id in self._pending:
            self._orders[order_id].status = OrderStatus.CANCELLED
            del self._pending[order_id]
            return True
        return False

    def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def get_position(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    def positions(self) -> list[Position]:
        return list(self._positions.values())

    def on_bar(self, bar: Bar) -> list[Fill]:
        fills: list[Fill] = []
        ready: list[tuple[str, Signal]] = []
        remaining: dict[str, tuple[Signal, int]] = {}

        for oid, (signal, waited) in self._pending.items():
            if waited >= self._delay:
                ready.append((oid, signal))
            else:
                remaining[oid] = (signal, waited + 1)

        self._pending = remaining

        for oid, signal in ready:
            order = self._orders[oid]
            price = getattr(bar, "close", getattr(bar, "nav", 0))
            fill = Fill(order_id=oid, price=price, volume=signal.volume)
            order.filled_volume = signal.volume
            order.status = OrderStatus.FILLED
            fills.append(fill)
            self._all_fills.append(fill)
            self._apply_fill(signal, fill)

        return fills

    # ponytail: 持仓逻辑和 SimExecutionEngine 一样，抽成 mixin 以后有必要再说
    def _apply_fill(self, signal: Signal, fill: Fill):
        # 和 SimExecutionEngine._apply_fill 逻辑相同
        pos = self._positions.get(signal.symbol)
        if signal.direction in (Direction.CLOSE_LONG, Direction.CLOSE_SHORT):
            close_dir = Direction.LONG if signal.direction == Direction.CLOSE_LONG else Direction.SHORT
            if pos and pos.direction == close_dir and pos.volume > 0:
                avg_cost = pos.avg_price * pos.volume
                fill_cost = fill.price * fill.volume
                pos.realized_pnl += avg_cost - fill_cost if signal.direction == Direction.CLOSE_LONG else fill_cost - avg_cost
                pos.volume -= fill.volume
                if pos.volume <= 0:
                    self._positions.pop(signal.symbol, None)
            return
        if signal.direction in (Direction.LONG, Direction.SHORT):
            if pos is None:
                self._positions[signal.symbol] = Position(
                    symbol=signal.symbol, direction=signal.direction,
                    volume=fill.volume, avg_price=fill.price,
                )
            else:
                total = pos.avg_price * pos.volume + fill.price * fill.volume
                pos.volume += fill.volume
                pos.avg_price = total / pos.volume


# ═══════════════════════════════════════════
# 回测引擎
# ═══════════════════════════════════════════

@dataclass
class BacktestReport:
    """回测报告（Phase 1 简易版）"""
    total_return: float = 0.0
    total_trades: int = 0
    final_equity: float = 0.0
    equity_curve: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)


class BacktestEngine:
    """回测引擎内核 — EventBus 驱动的事件循环"""

    def __init__(self, config: BacktestConfig):
        self.config = config
        self._event_bus: EventBus | None = None
        self._strategy: Strategy | None = None
        self._data: Any = None  # DataFeed — Phase 1 先接受 list[Bar]
        self._execution: ExecutionEngine | None = None
        self._cost_model: CostModel | None = None
        self._risk: Any = None  # RiskPipeline — Phase 1 暂不严格依赖

    def set_event_bus(self, bus: EventBus):
        self._event_bus = bus

    def set_strategy(self, strategy: Strategy):
        self._strategy = strategy

    def set_data(self, data: Any):
        self._data = data

    def set_executor(self, execution: ExecutionEngine):
        self._execution = execution

    def set_cost_model(self, cost_model: CostModel):
        self._cost_model = cost_model

    def set_risk(self, risk: Any):
        self._risk = risk

    def run(self) -> BacktestReport:
        """事件循环 — 驱动策略回测"""
        from .risk import RiskPipeline, RiskLevel, RiskContext

        bus = self._event_bus or EventBus()
        strategy = self._strategy
        execution = self._execution
        cost_model = self._cost_model or NoCost()
        risk_pipeline = self._risk  # Optional[RiskPipeline]
        bars = self._data or []
        if not strategy:
            raise RuntimeError("Strategy not set")

        ctx = StrategyContext(bus)
        strategy.on_init(ctx)

        _signals_published: list[Signal] = []

        def _capture(event: Event):
            _signals_published.append(event.payload)

        # ponytail: subscribe by value string to avoid circular import on EventType
        bus._subscribers["signal.generated"].append(_capture)

        # 所有待成交订单的信号映射（跨 bar 积累，T+1 撮合需要）
        _pending_signal_map: dict[str, Signal] = {}

        risk_ctx = RiskContext(portfolio_value=self.config.initial_capital)
        equity = self.config.initial_capital
        report = BacktestReport()
        report.equity_curve.append({"bar": 0, "equity": equity})

        for i, bar in enumerate(bars):
            # 发布 BAR_RECEIVED
            bus.publish(Event(EventType.BAR_RECEIVED, bar, source="engine"))

            # 组合级风控（每日一次）
            if risk_pipeline:
                risk_ctx.portfolio_value = equity
                risk_ctx.positions = [p.symbol for p in (execution.positions() if execution else [])]
                portfolio_results = risk_pipeline.run_portfolio(risk_ctx)
                reject = any(r.level == RiskLevel.REJECT for r in portfolio_results)
                if reject:
                    report.equity_curve.append({
                        "bar": i + 1, "equity": equity,
                        "close": getattr(bar, "close", getattr(bar, "nav", 0)),
                        "risk_blocked": True,
                    })
                    continue

            # Strategy 处理数据
            strategy.on_data(bar)

            # 信号级风控 + 执行
            allowed_signals: list[Signal] = []
            for signal in _signals_published:
                # 信号级风控
                if risk_pipeline:
                    risk_ctx.daily_signal_count += 1
                    signal_results = risk_pipeline.run_signal(signal, risk_ctx)
                    if any(r.level == RiskLevel.REJECT for r in signal_results):
                        bus.publish(Event(EventType.SIGNAL_RISK_REJECT, signal, source="risk"))
                        continue
                    bus.publish(Event(EventType.SIGNAL_RISK_PASS, signal, source="risk"))
                allowed_signals.append(signal)

            _signals_published.clear()

            # 提交信号到执行引擎（积累到跨 bar 映射）
            for signal in allowed_signals:
                order = execution.submit(signal) if execution else None
                if order:
                    _pending_signal_map[order.id] = signal

            # ExecutionEngine 撮合
            if execution:
                fills = execution.on_bar(bar)
                for fill in fills:
                    # 从跨 bar 映射中找对应的 signal
                    orig_signal = _pending_signal_map.get(fill.order_id)
                    if orig_signal:
                        cost = cost_model.calc(orig_signal, fill)
                        fill.commission = cost
                        strategy.on_fill(fill.order_id, fill)
                        report.total_trades += 1
                        bus.publish(Event(EventType.ORDER_FILLED, fill, source="execution"))

            # 记录权益曲线
            equity_ts = report.equity_curve[-1]["equity"]
            bar_price = getattr(bar, "close", getattr(bar, "nav", 0))
            if execution and execution.positions():
                for pos in execution.positions():
                    if pos.volume > 0:
                        mk_val = pos.volume * bar_price
                        cost_val = pos.volume * pos.avg_price
                        pos.unrealized_pnl = round(mk_val - cost_val, 4)
                        equity_ts += pos.unrealized_pnl

            report.equity_curve.append({
                "bar": i + 1, "equity": round(equity_ts, 2),
                "close": bar_price,
            })

        report.final_equity = report.equity_curve[-1]["equity"]
        report.total_return = (report.final_equity / self.config.initial_capital) - 1
        bus.publish(Event(EventType.ENGINE_STOP, {"reason": "completed"}, source="engine"))
        return report


def demo():
    """端到端回测自检"""
    from .data import Bar
    from .config import BacktestConfig
    from .strategy import Strategy, StrategyRegistry
    from datetime import datetime

    bus = EventBus()
    cfg = BacktestConfig(initial_capital=100_000)

    # 一个简单策略：close > 100 做多
    @StrategyRegistry.register("demo_backtest")
    class DemoStrategy(Strategy):
        def on_data(self, data):
            if data.close > 100:
                self.ctx.emit(Signal(
                    id="", strategy="demo_backtest", symbol=data.symbol,
                    direction=Direction.LONG, price=data.close, volume=1,
                    reason=f"close={data.close} > 100",
                ))

    # 构造 10 根 bar
    bars = [Bar(symbol="TEST", exchange="DEMO", timeframe="1d",
                datetime=datetime(2026, 7, i + 1),
                open=float(100 + i), high=float(101 + i),
                low=float(99 + i), close=float(100 + i),
                volume=1000) for i in range(10)]

    engine = BacktestEngine(cfg)
    engine.set_event_bus(bus)
    engine.set_strategy(DemoStrategy())
    engine.set_executor(SimExecutionEngine())
    engine.set_data(bars)
    report = engine.run()

    assert report.total_trades > 0, f"expected trades, got {report.total_trades}"
    assert report.total_return != 0 or report.total_trades > 0
    assert len(report.equity_curve) == len(bars) + 1  # 初始 + 每根 bar

    print(f"[backtest] ✅ 端到端回测通过 — {report.total_trades} 笔交易, "
          f"return={report.total_return:.2%}, equity={report.final_equity:.0f}")


if __name__ == "__main__":
    demo()
