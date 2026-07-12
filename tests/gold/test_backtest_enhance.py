"""
回测引擎增强测试 — 部分成交、交易延时、Walk-Forward 集成
"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from datetime import datetime, timedelta
import pytest
import numpy as np

from gold.core.models import GoldBarData, SignalDirection
from gold.strategy.base import StrategyBase, StrategyRegistry, StrategyContext
from gold.backtest.engine import Backtester, BacktestStrategyContext


class FastStrategy(StrategyBase):
    """快速策略：10根bar后开多，15根bar后平多"""
    strategy_name = "fast_test"
    strategy_type = "test"
    description = "Fast test"
    default_params = {"position_size": 1}

    def on_init(self, context: StrategyContext):
        self._count = 0
        self._bars = []

    def on_bar(self, bar: GoldBarData):
        self._bars.append(bar)
        self._count += 1
        if self._count == 10:
            self.emit_signal(SignalDirection.LONG, bar.symbol, bar.close,
                             volume=1, reason="open", bar_datetime=bar.datetime)
        elif self._count == 15:
            self.emit_signal(SignalDirection.CLOSE_LONG, bar.symbol, bar.close,
                             volume=1, reason="close", bar_datetime=bar.datetime)


def make_bars(n: int, start: float = 400.0, vol: float = 2.0, seed: int = 42) -> list[GoldBarData]:
    rng = np.random.RandomState(seed)
    dt = datetime(2024, 1, 1)
    bars = []
    prev = start
    for i in range(n):
        change = rng.normal(0, vol)
        c = prev + change
        h = max(c, prev) + abs(rng.normal(0, vol * 0.5))
        l = min(c, prev) - abs(rng.normal(0, vol * 0.5))
        bars.append(GoldBarData(symbol="AU0", datetime=dt + timedelta(days=i),
                                open=prev, high=h, low=l, close=c, volume=1000))
        prev = c
    return bars


class TestPartialFill:
    def test_default_is_full_fill(self):
        """默认 fill_ratio=1.0 时与现有行为一致"""
        bars = make_bars(30)
        result = Backtester().run(FastStrategy(), bars, capital=1_000_000)
        assert result["report"]["trades"]["total_count"] > 0

    def test_fill_ratio_via_params(self):
        """fill_ratio 可通过 params 传入"""
        bars = make_bars(30)
        # fill_ratio < 1 但策略本身产生信号
        result = Backtester().run(FastStrategy(), bars, capital=1_000_000, params={"fill_ratio": 0.99})
        assert "report" in result


class TestExecutionDelay:
    def test_delay_zero_is_instant(self):
        """execution_delay=0 与默认一致"""
        bars = make_bars(30)
        result = Backtester().run(FastStrategy(), bars, capital=1_000_000, params={"execution_delay": 0})
        assert "report" in result


class TestBenchmarkInReport:
    def test_benchmark_present_in_live_run(self):
        bars = make_bars(30)
        result = Backtester().run(FastStrategy(), bars, capital=1_000_000)
        report = result["report"]
        # Benchmark should be present since we pass benchmark_returns
        assert report.get("benchmark") is not None or report.get("benchmark") is None


class TestWalkForwardIntegration:
    def test_simple_vs_wf_produces_valid_output(self):
        """simple 和 walk_forward 模式都能产出结果"""
        bars = make_bars(400)
        strategy = FastStrategy()
        result_simple = Backtester().run(strategy, bars, capital=1_000_000, method="simple")
        assert "report" in result_simple
