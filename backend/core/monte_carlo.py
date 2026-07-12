"""蒙特卡洛模拟 — 回测稳定性分析 + 参数敏感性"""
from __future__ import annotations

from typing import Any
from dataclasses import dataclass, field


@dataclass
class MonteCarloResult:
    n_simulations: int = 0
    return_pct: dict = field(default_factory=dict)
    sharpe_ratio: dict = field(default_factory=dict)
    max_drawdown_pct: dict = field(default_factory=dict)
    avg_trades: int = 0


class MonteCarloSimulator:
    """Monte Carlo 回测稳定性模拟 — bootstrap 交易盈亏序列

    >>> mc = MonteCarloSimulator(n_simulations=100, seed=42)
    >>> trades = [{"pnl": 100}, {"pnl": -50}, {"pnl": 200}, {"pnl": -30}]
    >>> r = mc.simulate(trades, capital=10000, n_bars=252)
    >>> isinstance(r, MonteCarloResult)
    True
    >>> r.n_simulations > 0
    True
    """

    def __init__(self, n_simulations: int = 1000, seed: int = 42):
        self.n_sim = n_simulations
        self.seed = seed

    def simulate(self, trades: list[dict], capital: float,
                 n_bars: int) -> MonteCarloResult:
        close_trades = [t for t in trades if t.get("type") in ("close", None)]
        pnls = [t.get("pnl", 0) for t in close_trades if t.get("pnl") is not None]
        if not pnls:
            return MonteCarloResult()

        import numpy as np
        arr = np.array(pnls, dtype=float)
        rng = np.random.RandomState(self.seed)

        path_returns, path_sharpes, path_drawdowns = [], [], []
        for _ in range(self.n_sim):
            sampled = rng.choice(arr, size=len(arr), replace=True)
            eq = np.cumsum(np.concatenate([[capital], sampled]))
            total_ret = float(eq[-1] / capital - 1)
            days = len(eq) - 1
            ann_ret = (np.exp(np.log(1 + total_ret) * 252 / days) - 1
                       if days > 0 and total_ret > -1 else 0.0)
            rets = np.diff(eq) / eq[:-1]
            vol = float(np.std(rets) * np.sqrt(252)) if len(rets) > 1 else 0.0
            sharpe = float((ann_ret - 0.025) / vol) if vol > 0 else 0.0
            peak = np.maximum.accumulate(eq)
            dd = float(np.min((eq - peak) / peak)) * 100
            path_returns.append(total_ret * 100)
            path_sharpes.append(sharpe)
            path_drawdowns.append(dd)

        if not path_returns:
            return MonteCarloResult()

        ra = np.array(path_returns)
        sa = np.array(path_sharpes)
        da = np.array(path_drawdowns)
        return MonteCarloResult(
            n_simulations=len(path_returns),
            return_pct=self._stats(ra),
            sharpe_ratio=self._stats(sa),
            max_drawdown_pct=self._stats(da),
            avg_trades=int(np.mean([len(pnls)])),
        )

    @staticmethod
    def _stats(a: np.ndarray) -> dict:
        import numpy as np
        return {
            "mean": round(float(np.mean(a)), 2),
            "median": round(float(np.median(a)), 2),
            "std": round(float(np.std(a)), 2),
            "p5": round(float(np.percentile(a, 5)), 2),
            "p25": round(float(np.percentile(a, 25)), 2),
            "p75": round(float(np.percentile(a, 75)), 2),
            "p95": round(float(np.percentile(a, 95)), 2),
            "min": round(float(np.min(a)), 2),
            "max": round(float(np.max(a)), 2),
            "positive_ratio": round(float(np.mean(a > 0) * 100), 1),
        }


class SensitivityAnalyzer:
    """参数敏感性分析

    给定基参和偏移范围，逐个参数扰动，观察指标变化。
    """

    def __init__(self, base_params: dict, ranges: dict[str, list]):
        self.base = base_params
        self.ranges = ranges

    def analyze(self, eval_fn: callable) -> dict[str, Any]:
        results = {}
        for param, values in self.ranges.items():
            scores = []
            for v in values:
                params = dict(self.base, **{param: v})
                score = eval_fn(params)
                scores.append({"value": v, "score": score})
            results[param] = scores
        return results


def demo():
    mc = MonteCarloSimulator(n_simulations=100, seed=42)
    trades = [{"pnl": 100}, {"pnl": -50}, {"pnl": 200}, {"pnl": 80},
              {"pnl": -30}, {"pnl": 150}, {"pnl": 60}]
    r = mc.simulate(trades, 10000, 252)
    assert r.n_simulations == 100
    print(f"[monte_carlo] ✅ {r.n_simulations} paths, "
          f"return={r.return_pct['mean']}%, sharpe={r.sharpe_ratio['mean']}")

    sa = SensitivityAnalyzer({"period": 20}, {"period": [10, 20, 30]})
    res = sa.analyze(lambda p: p["period"] * 0.01)
    assert len(res["period"]) == 3
    print(f"[sensitivity] ✅ 敏感性分析通过")


if __name__ == "__main__":
    demo()
