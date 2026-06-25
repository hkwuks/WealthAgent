from typing import Optional
from datetime import datetime

from backend.gold.core.models import (
    GoldBarData, GoldSignal, GoldPosition, SignalDirection,
)
from backend.gold.backtest.cost_model import CostModel
from backend.gold.strategy.base import StrategyBase, StrategyContext
from backend.gold.core.config import GoldSettings
from loguru import logger


class BacktestStrategyContext(StrategyContext):
    """回测策略上下文 — 模拟撮合"""

    def __init__(self, capital: float, cost_model: CostModel,
                 multiplier: int = 1000, margin_rate: float = 0.08):
        self.initial_capital = capital
        self.capital = capital
        self.cost_model = cost_model
        self.multiplier = multiplier
        self.margin_rate = margin_rate

        self._positions: dict[str, GoldPosition] = {}
        self._equity_curve: list[float] = [capital]
        self._trades: list[dict] = []
        self._signals: list[GoldSignal] = []
        self._max_capital: float = capital
        self._current_prices: dict[str, float] = {}
        self._bar_count: int = 0

    @property
    def mode(self) -> str:
        return "backtest"

    def on_signal(self, signal: GoldSignal):
        self._signals.append(signal)
        if signal.direction in (SignalDirection.LONG, SignalDirection.SHORT):
            self._open_position(signal)
        elif signal.direction in (SignalDirection.CLOSE_LONG, SignalDirection.CLOSE_SHORT):
            self._close_position(signal)

    def _open_position(self, signal: GoldSignal):
        notional = signal.price * self.multiplier * signal.volume
        margin = notional * self.margin_rate
        cost = self.cost_model.open_cost(signal.volume)

        if margin + cost > self.capital:
            logger.debug(f"资金不足，跳过开仓: margin={margin}, cost={cost}, capital={self.capital}")
            return

        direction = "long" if signal.direction == SignalDirection.LONG else "short"
        pos = GoldPosition(
            symbol=signal.symbol, direction=direction,
            volume=signal.volume, avg_price=signal.price, margin=margin,
        )
        self._positions[signal.symbol] = pos
        self.capital -= cost

        self._trades.append({
            "type": "open", "direction": direction,
            "symbol": signal.symbol, "price": signal.price,
            "volume": signal.volume, "commission": self.cost_model.open_commission_per_lot * signal.volume,
            "slippage": self.cost_model.slippage_per_lot * signal.volume,
            "open_bar": self._bar_count,
            "timestamp": signal.created_at.isoformat() if signal.created_at else "",
        })

    def _close_position(self, signal: GoldSignal):
        pos = self._positions.get(signal.symbol)
        if not pos:
            return

        if pos.direction == "long":
            pnl = (signal.price - pos.avg_price) * self.multiplier * pos.volume
        else:
            pnl = (pos.avg_price - signal.price) * self.multiplier * pos.volume

        cost = self.cost_model.close_cost(pos.volume)
        net_pnl = pnl - cost
        self.capital += pos.margin + net_pnl

        # 找对应的open trade算holding_bars
        open_bar = 0
        for t in reversed(self._trades):
            if t["type"] == "open" and t["symbol"] == signal.symbol:
                open_bar = t.get("open_bar", 0)
                break

        self._trades.append({
            "type": "close", "direction": pos.direction,
            "symbol": signal.symbol, "price": signal.price,
            "volume": pos.volume, "pnl": net_pnl,
            "commission": self.cost_model.close_commission_per_lot * pos.volume,
            "slippage": self.cost_model.slippage_per_lot * pos.volume,
            "holding_bars": self._bar_count - open_bar,
            "timestamp": signal.created_at.isoformat() if signal.created_at else "",
        })

        del self._positions[signal.symbol]

    def get_position(self, symbol: str) -> Optional[GoldPosition]:
        return self._positions.get(symbol)

    def get_balance(self) -> float:
        return self.capital

    def update_equity(self, bar: GoldBarData):
        """每bar更新权益曲线"""
        self._current_prices[bar.symbol] = bar.close
        self._bar_count += 1

        unrealized = 0
        for symbol, pos in self._positions.items():
            price = self._current_prices.get(symbol, pos.avg_price)
            if pos.direction == "long":
                unrealized += (price - pos.avg_price) * self.multiplier * pos.volume
            else:
                unrealized += (pos.avg_price - price) * self.multiplier * pos.volume

        equity = self.capital + sum(p.margin for p in self._positions.values()) + unrealized
        self._equity_curve.append(equity)
        self._max_capital = max(self._max_capital, equity)


class Backtester:
    """事件驱动回测引擎"""

    def __init__(self, config: GoldSettings = None):
        self.config = config or GoldSettings()

    def run(self, strategy: StrategyBase, bars: list[GoldBarData],
            capital: float = None, params: dict = None) -> dict:
        capital = capital or self.config.backtest_capital
        cost_model = CostModel(
            open_commission_per_lot=self.config.backtest_commission_per_lot,
            close_commission_per_lot=self.config.backtest_commission_per_lot,
            close_today_commission_per_lot=self.config.backtest_close_commission_per_lot,
            slippage_per_lot=self.config.backtest_slippage_per_lot,
        )
        context = BacktestStrategyContext(
            capital=capital, cost_model=cost_model,
            multiplier=self.config.au_multiplier,
            margin_rate=self.config.au_margin_rate,
        )

        if params:
            for k, v in params.items():
                if hasattr(strategy, k):
                    setattr(strategy, k, v)

        strategy.set_context(context)
        strategy.on_init(context)

        for bar in bars:
            strategy.on_bar(bar)
            context.update_equity(bar)

        from backend.gold.backtest.report import BacktestReport
        report = BacktestReport().generate(
            equity_curve=context._equity_curve,
            trades=context._trades,
            capital=capital,
            start_date=bars[0].datetime.strftime("%Y-%m-%d") if bars else "",
            end_date=bars[-1].datetime.strftime("%Y-%m-%d") if bars else "",
            risk_free_rate=self.config.risk_free_rate,
        )

        return {
            "strategy": strategy.strategy_name,
            "signals": [s.model_dump() for s in context._signals],
            "trades": context._trades,
            "report": report,
        }
