from typing import Optional
from datetime import datetime
import numpy as np

from backend.gold.core.models import (
    GoldBarData, GoldSignal, GoldPosition, SignalDirection,
)
from backend.gold.backtest.cost_model import CostModel
from backend.gold.strategy.base import StrategyBase, StrategyContext
from backend.gold.core.config import GoldSettings
from loguru import logger


class BacktestStrategyContext(StrategyContext):
    """回测策略上下文 — 模拟撮合（含部分成交和交易延时）"""

    def __init__(self, capital: float, cost_model: CostModel,
                 multiplier: int = 1000, margin_rate: float = 0.08,
                 fill_ratio: float = 1.0, execution_delay: int = 0):
        self.initial_capital = capital
        self.capital = capital
        self.cost_model = cost_model
        self.multiplier = multiplier
        self.margin_rate = margin_rate
        self.fill_ratio = fill_ratio
        self.execution_delay = execution_delay

        self._positions: dict[str, GoldPosition] = {}
        self._equity_curve: list[float] = [capital]
        self._trades: list[dict] = []
        self._signals: list[GoldSignal] = []
        self._max_capital: float = capital
        self._current_prices: dict[str, float] = {}
        self._bar_count: int = 0
        # {symbol: open_bar_index} 用于平今判断
        self._open_bars: dict[str, int] = {}
        # 当前 bar ATR 值（由引擎设置）
        self.current_atr: float = 0.0
        # 延迟成交队列: [(delay_counter, signal, ...)]
        self._pending_orders: list[dict] = []

    @property
    def mode(self) -> str:
        return "backtest"

    def on_signal(self, signal: GoldSignal):
        self._signals.append(signal)
        if signal.direction in (SignalDirection.LONG, SignalDirection.SHORT):
            if self.execution_delay > 0:
                # 进入延迟队列
                self._pending_orders.append({
                    "remaining_delay": self.execution_delay,
                    "signal": signal,
                })
            else:
                self._open_position(signal)
        elif signal.direction in (SignalDirection.CLOSE_LONG, SignalDirection.CLOSE_SHORT):
            if self.execution_delay > 0:
                self._pending_orders.append({
                    "remaining_delay": self.execution_delay,
                    "signal": signal,
                })
            else:
                self._close_position(signal)

    def process_pending_orders(self, current_bar: GoldBarData):
        """每 bar 处理延迟队列"""
        if not self._pending_orders:
            return

        remaining = []
        for order in self._pending_orders:
            order["remaining_delay"] -= 1
            if order["remaining_delay"] <= 0:
                signal = order["signal"]
                # 用当前 bar 的 close 更新价格（模拟延迟成交价）
                if signal.direction in (SignalDirection.LONG, SignalDirection.SHORT):
                    # 部分成交模拟
                    import random as _r
                    effective_volume = signal.volume
                    if self.fill_ratio < 1.0:
                        if _r.random() > self.fill_ratio:
                            effective_volume = max(1, int(signal.volume * _r.uniform(0.1, 0.9)))
                    signal.price = current_bar.close  # 更新为延迟后的价格
                    signal.volume = effective_volume
                    self._open_position(signal)
                else:
                    signal.price = current_bar.close
                    self._close_position(signal)
            else:
                remaining.append(order)
        self._pending_orders = remaining

    def _open_position(self, signal: GoldSignal):
        notional = signal.price * self.multiplier * signal.volume
        margin = notional * self.margin_rate
        cost = self.cost_model.open_cost(signal.volume, atr_value=self.current_atr)

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
        self._open_bars[signal.symbol] = self._bar_count

        self._trades.append({
            "type": "open", "direction": direction,
            "symbol": signal.symbol, "price": signal.price,
            "volume": signal.volume, "commission": self.cost_model.open_commission_per_lot * signal.volume,
            "slippage": self.cost_model._slippage(signal.volume, atr_value=self.current_atr),
            "open_bar": self._bar_count,
            "timestamp": signal.created_at.isoformat() if signal.created_at else "",
        })

    def _close_position(self, signal: GoldSignal):
        pos = self._positions.get(signal.symbol)
        if not pos:
            return

        # 判断是否平今
        open_bar = self._open_bars.get(signal.symbol, -999)
        is_close_today = open_bar == self._bar_count

        if pos.direction == "long":
            pnl = (signal.price - pos.avg_price) * self.multiplier * pos.volume
        else:
            pnl = (pos.avg_price - signal.price) * self.multiplier * pos.volume

        cost = self.cost_model.close_cost(pos.volume, is_close_today=is_close_today,
                                          atr_value=self.current_atr)
        net_pnl = pnl - cost
        self.capital += pos.margin + net_pnl

        # 找对应的open trade算holding_bars
        holding_bars = self._bar_count - open_bar if open_bar >= 0 else 0

        self._trades.append({
            "type": "close", "direction": pos.direction,
            "symbol": signal.symbol, "price": signal.price,
            "volume": pos.volume, "pnl": net_pnl,
            "commission": self.cost_model.close_commission_per_lot * pos.volume if not is_close_today
                          else self.cost_model.close_today_commission_per_lot * pos.volume,
            "slippage": self.cost_model._slippage(pos.volume, atr_value=self.current_atr),
            "holding_bars": holding_bars,
            "is_close_today": is_close_today,
            "timestamp": signal.created_at.isoformat() if signal.created_at else "",
        })

        del self._positions[signal.symbol]
        self._open_bars.pop(signal.symbol, None)

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
            capital: float = None, params: dict = None,
            method: str = "simple") -> dict:
        """
        运行回测。

        Args:
            method: "simple" — 一次性回测（默认，有 look-ahead 风险）
                    "walk_forward" — 滚动窗口回测（Purging+Embargo，ML策略推荐）
                    自动: ML 策略默认走 walk_forward，其他走 simple
        """
        strategy_name = getattr(strategy, 'strategy_name', '')
        is_ml = strategy_name in ('ml_predictor',)
        effective_method = method if method != 'auto' else ('walk_forward' if is_ml else 'simple')
        capital = capital or self.config.backtest_capital

        if effective_method == 'walk_forward':
            return self._run_walk_forward(strategy.__class__, bars, capital, params)

        # ── simple 模式（原逻辑） ──
        cost_model = CostModel(
            open_commission_per_lot=strategy.commission_per_lot if strategy.commission_per_lot is not None else self.config.backtest_commission_per_lot,
            close_commission_per_lot=strategy.commission_per_lot if strategy.commission_per_lot is not None else self.config.backtest_commission_per_lot,
            close_today_commission_per_lot=self.config.backtest_close_commission_per_lot,
            slippage_per_lot=self.config.backtest_slippage_per_lot,
            multiplier=self.config.au_multiplier,
        )

        if params:
            for k, v in params.items():
                if hasattr(strategy, k):
                    setattr(strategy, k, v)

        # 从策略或参数读取撮合参数
        fill_ratio = getattr(strategy, 'fill_ratio', 1.0)
        execution_delay = getattr(strategy, 'execution_delay', 0)
        if params:
            fill_ratio = params.get('fill_ratio', fill_ratio)
            execution_delay = params.get('execution_delay', execution_delay)

        context = BacktestStrategyContext(
            capital=capital, cost_model=cost_model,
            multiplier=self.config.au_multiplier,
            margin_rate=self.config.au_margin_rate,
            fill_ratio=float(fill_ratio),
            execution_delay=int(execution_delay),
        )

        strategy.set_context(context)
        strategy.on_init(context)

        atr_values = self._calc_atr_series(bars, 14)

        for i, bar in enumerate(bars):
            context.current_atr = atr_values[i] if i < len(atr_values) else 0.0
            strategy.on_bar(bar)
            context.update_equity(bar)
            context.process_pending_orders(bar)

        from backend.gold.backtest.report import BacktestReport

        # 计算基准收益率（买入持有）
        benchmark_returns = None
        if len(bars) > 1:
            closes = np.array([b.close for b in bars])
            benchmark_returns = (closes[1:] - closes[:-1]) / closes[:-1]

        report = BacktestReport().generate(
            equity_curve=context._equity_curve,
            trades=context._trades,
            capital=capital,
            start_date=bars[0].datetime.strftime("%Y-%m-%d") if bars else "",
            end_date=bars[-1].datetime.strftime("%Y-%m-%d") if bars else "",
            risk_free_rate=self.config.risk_free_rate,
            benchmark_returns=benchmark_returns,
        )

        return {
            "strategy": strategy_name,
            "signals": [s.model_dump() for s in context._signals],
            "trades": context._trades,
            "report": report,
        }

    def _run_walk_forward(self, strategy_cls: type[StrategyBase],
                          bars: list[GoldBarData], capital: float,
                          params: dict = None) -> dict:
        """内部 Walk-Forward 回测，产出与 simple 模式兼容的报告"""
        from backend.gold.backtest.walk_forward import WalkForwardValidator

        validator = WalkForwardValidator(capital=capital, config=self.config)
        result = validator.validate(strategy_cls, bars, params=params)

        if "error" in result:
            return {"strategy": strategy_cls.__name__, "report": self._empty_report(capital), "signals": [], "trades": [],
                    "walk_forward": result, "error": result["error"]}

        # 汇总所有窗口的信号/交易
        all_signals = []
        all_trades = []
        for w in result.get("windows", []):
            all_signals.extend(w.get("signals", []))
            all_trades.extend(w.get("trades", []))

        # 从各窗口报告生成汇总 equity curve
        equity_increments = [capital]
        for w in result.get("windows", []):
            return_pct = w.get("total_return_pct") or 0
            equity_increments.append(equity_increments[-1] * (1 + return_pct / 100))

        from backend.gold.backtest.report import BacktestReport
        start_date = bars[0].datetime.strftime("%Y-%m-%d") if bars else ""
        end_date = bars[-1].datetime.strftime("%Y-%m-%d") if bars else ""
        report = BacktestReport().generate(
            equity_curve=equity_increments,
            trades=all_trades,
            capital=capital,
            start_date=start_date,
            end_date=end_date,
            risk_free_rate=self.config.risk_free_rate,
        )

        return {
            "strategy": strategy_cls.strategy_name if hasattr(strategy_cls, 'strategy_name') else strategy_cls.__name__,
            "signals": all_signals[-100:],
            "trades": all_trades[-100:],
            "report": report,
            "walk_forward": {
                "method": "walk_forward",
                "n_windows": result.get("n_windows", 0),
                "avg_return_pct": result.get("avg_return_pct"),
                "avg_sharpe": result.get("avg_sharpe"),
                "positive_window_ratio": result.get("positive_window_ratio"),
            },
        }

    @staticmethod
    def _empty_report(capital: float) -> dict:
        return {
            "performance": {"total_return": 0, "annualized_return": 0, "sharpe_ratio": 0,
                           "sortino_ratio": 0, "calmar_ratio": 0, "win_rate": 0, "profit_factor": None},
            "risk": {"max_drawdown": 0, "var_95": 0, "cvar_95": 0, "volatility": 0,
                    "downside_deviation": 0, "skewness": 0, "kurtosis": 0},
            "trades": {"total_count": 0, "avg_holding_bars": 0, "avg_profit": 0, "avg_loss": 0, "max_single_loss": 0},
            "cost": {"total_commission": 0, "total_slippage": 0, "gross_pnl": 0, "net_pnl": 0},
            "meta": {"capital": capital, "start_date": "", "end_date": "", "total_days": 0, "risk_free_rate": 0.025},
        }

    @staticmethod
    def _calc_atr_series(bars: list[GoldBarData], period: int = 14) -> list[float]:
        """计算 ATR 序列，用于动态滑点"""
        if len(bars) < 2:
            return [0.0] * len(bars)

        trs = []
        for i in range(1, len(bars)):
            h, l, pc = bars[i].high, bars[i].low, bars[i-1].close
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)

        atr_values = [0.0] * len(bars)
        for i in range(len(bars)):
            if i == 0:
                continue
            window = trs[max(0, i - period):i]
            atr_values[i] = sum(window) / len(window) if window else 0.0
        return atr_values
