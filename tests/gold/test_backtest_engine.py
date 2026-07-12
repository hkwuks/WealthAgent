"""回测引擎测试"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from datetime import datetime
import pytest

from gold.core.models import GoldBarData, SignalDirection
from gold.strategy.base import StrategyBase, StrategyRegistry, StrategyContext
from gold.backtest.engine import Backtester


class DummyStrategy(StrategyBase):
    """测试用策略：每5根bar交替做多/做空"""

    def __init__(self, **kwargs):
        # Set default params explicitly
        params = {"position_size": 1}
        params.update(kwargs)
        super().__init__(**params)

    strategy_name = "dummy_test"
    strategy_type = "dummy"
    description = "Test strategy"

    def on_init(self, context: StrategyContext):
        self._count = 0
        self._bars = []

    def on_bar(self, bar: GoldBarData):
        self._bars.append(bar)
        self._count += 1
        if self._count % 5 != 0:
            return
        if (self._count // 5) % 2 == 1:
            self.emit_signal(SignalDirection.LONG, bar.symbol, bar.close,
                             volume=1, reason="dummy_long", bar_datetime=bar.datetime)
        else:
            self.emit_signal(SignalDirection.CLOSE_LONG, bar.symbol, bar.close,
                             volume=1, reason="dummy_close", bar_datetime=bar.datetime)


def make_bars(n=30, start_price=100.0) -> list[GoldBarData]:
    """生成模拟K线"""
    bars = []
    price = start_price
    for i in range(n):
        dt = datetime(2025, 1, 1 + i // 5, 1 + i % 5, 0, 0) if i < 155 else datetime(2025, 12, 1, 0, 0)
        # ensure unique dates
        from datetime import timedelta
        base = datetime(2025, 1, 1)
        dt = base + timedelta(days=i)
        price = price * (1 + (i % 7 - 3) * 0.005)  # oscillate
        bars.append(GoldBarData(
            symbol="AU0", exchange="SHFE", period="d",
            datetime=dt,
            open=round(price * 0.998, 2),
            high=round(price * 1.005, 2),
            low=round(price * 0.995, 2),
            close=round(price, 2),
            volume=1000 + i * 10,
        ))
    return bars


class TestBacktester:
    def test_run_dummy_strategy(self):
        bars = make_bars(60)
        strategy = DummyStrategy()
        backtester = Backtester()
        result = backtester.run(strategy, bars, capital=100_000)

        assert result["strategy"] == "dummy_test"
        assert result["report"]["meta"]["capital"] == 100_000
        assert len(result["signals"]) > 0
        assert len(result["trades"]) > 0

    def test_empty_bars_returns_empty_report(self):
        """空K线时返回空报告"""
        strategy = DummyStrategy()
        backtester = Backtester()
        result = backtester.run(strategy, [], capital=100_000)
        assert len(result["signals"]) == 0
        assert result["report"]["trades"]["total_count"] == 0

    def test_position_open_and_close(self):
        bars = make_bars(30)
        strategy = DummyStrategy()
        backtester = Backtester()
        result = backtester.run(strategy, bars, capital=100_000)

        # dummy opens every 5 bars and closes every 10
        signals = result["signals"]
        trades = result["trades"]
        assert len([s for s in signals if s["direction"] in ("long", "short")]) >= 2
        assert len([t for t in trades if t["type"] == "close"]) >= 1

    def test_report_has_full_metrics(self):
        """验证回测报告包含完整指标"""
        bars = make_bars(60)
        strategy = DummyStrategy()
        result = Backtester().run(strategy, bars, capital=100_000)

        report = result["report"]
        assert "performance" in report
        assert "risk" in report
        assert "trades" in report
        assert "meta" in report
        assert report["meta"]["capital"] == 100_000

    def test_cost_model_affects_pnl(self):
        bars = make_bars(60)

        strategy1 = DummyStrategy()
        result1 = Backtester().run(strategy1, bars, capital=100_000)

        strategy2 = DummyStrategy()
        strategy2.commission_per_lot = 50.0
        result2 = Backtester().run(strategy2, bars, capital=100_000)

        final1 = result1["report"]["meta"]["capital"] + result1["report"]["cost"]["net_pnl"]
        final2 = result2["report"]["meta"]["capital"] + result2["report"]["cost"]["net_pnl"]
        # Higher cost should give lower (or equal) PnL
        assert final2 <= final1 + 1e-6

    def test_insufficient_capital_skips_trade(self):
        bars = make_bars(30)
        strategy = DummyStrategy()
        result = Backtester().run(strategy, bars, capital=100)
        # With only 100 capital, margin for 1 lot of ~100 price * 1000 * 8% = 8000 > 100
        assert result["report"]["trades"]["total_count"] == 0

    def test_atr_calculation_series(self):
        bars = make_bars(60)
        atr_vals = Backtester._calc_atr_series(bars, 14)
        assert len(atr_vals) == len(bars)
        # First bar should be 0, later ones > 0 (atr from bar 1 onward)
        assert atr_vals[0] == 0
        assert sum(atr_vals[20:]) > 0

    def test_strategy_params_override(self):
        class ConfigStrategy(DummyStrategy):
            default_params = {"position_size": 2, "threshold": 0.1}
        strategy = ConfigStrategy()
        backtester = Backtester()
        bars = make_bars(30)
        result = backtester.run(strategy, bars, capital=100_000,
                                params={"position_size": 5, "threshold": 0.2})
        assert strategy.position_size == 5
        assert strategy.threshold == 0.2
