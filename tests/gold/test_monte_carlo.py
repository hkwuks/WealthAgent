"""
Monte Carlo 模拟 + Benchmark 对比测试
"""

import pytest
import numpy as np
from datetime import datetime, timedelta

from backend.gold.core.models import GoldBarData
from backend.gold.backtest.monte_carlo import MonteCarloSimulator
from backend.gold.backtest.report import BacktestReport


def _make_trades(n: int, capital: float = 1_000_000) -> list[dict]:
    rng = np.random.RandomState(42)
    trades = []
    pnl_so_far = capital
    for i in range(n):
        pnl = rng.normal(5000, 20000)
        pnl_so_far += pnl
        trades.append({
            "type": "close", "pnl": pnl, "volume": 1, "price": 400,
            "commission": 10, "slippage": 20, "symbol": "AU0",
            "direction": "long", "holding_bars": 5, "is_close_today": False,
            "timestamp": (datetime(2024, 1, 1) + timedelta(days=i*5)).isoformat(),
        })
    return trades


class TestMonteCarloSimulator:
    def test_no_close_trades_returns_error(self):
        sim = MonteCarloSimulator(n_simulations=10)
        result = sim.simulate([], 1_000_000, 100)
        assert "error" in result

    def test_simulate_returns_distribution(self):
        trades = _make_trades(20)
        sim = MonteCarloSimulator(n_simulations=50)
        result = sim.simulate(trades, 1_000_000, 200)
        assert "error" not in result
        assert result["n_simulations"] == 50
        assert "return_pct" in result
        assert "sharpe_ratio" in result
        assert "max_drawdown_pct" in result

    def test_return_pct_has_percentiles(self):
        trades = _make_trades(30)
        sim = MonteCarloSimulator(n_simulations=50)
        result = sim.simulate(trades, 1_000_000, 250)
        r = result["return_pct"]
        for key in ("mean", "median", "p5", "p25", "p75", "p95", "positive_ratio"):
            assert key in r, f"Missing {key} in return_pct"

    def test_seed_reproducibility(self):
        trades = _make_trades(20)
        sim1 = MonteCarloSimulator(n_simulations=50, seed=42)
        sim2 = MonteCarloSimulator(n_simulations=50, seed=42)
        r1 = sim1.simulate(trades, 1_000_000, 200)
        r2 = sim2.simulate(trades, 1_000_000, 200)
        assert r1["return_pct"]["mean"] == r2["return_pct"]["mean"]


class TestBenchmarkReport:
    def test_report_without_benchmark(self):
        report = BacktestReport().generate(
            equity_curve=[1_000_000, 1_050_000, 1_030_000],
            trades=_make_trades(5),
            capital=1_000_000,
            start_date="2024-01-01", end_date="2024-12-31",
        )
        assert report.get("benchmark") is None

    def test_report_with_benchmark(self):
        """benchmark_returns 存在时应产出 benchmark 指标"""
        report = BacktestReport().generate(
            equity_curve=[1_000_000, 1_050_000, 1_030_000, 1_080_000],
            trades=_make_trades(3),
            capital=1_000_000,
            start_date="2024-01-01", end_date="2024-12-31",
            benchmark_returns=[0.02, 0.01, -0.01],
        )
        assert report.get("benchmark") is not None
        assert "total_return" in report["benchmark"]
        assert report.get("excess") is not None
        assert "information_ratio" in report["excess"]
