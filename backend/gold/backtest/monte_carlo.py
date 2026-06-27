"""
Monte Carlo 模拟 — 对回测交易序列重采样，评估结果稳定性。

原理: bootstrap 交易盈亏序列，生成 N 条路径，计算置信区间。
"""

import numpy as np
from typing import Optional
from loguru import logger


class MonteCarloSimulator:
    """Monte Carlo 回测稳定性模拟"""

    def __init__(self, n_simulations: int = 1000, seed: int = 42):
        """
        Args:
            n_simulations: bootstrap 路径数
            seed: 随机种子（可复现）
        """
        self.n_simulations = n_simulations
        self.seed = seed

    def simulate(self, trades: list[dict], capital: float,
                 n_bars: int) -> dict:
        """
        对交易盈亏序列做 bootstrap 重采样。

        Args:
            trades: 回测产生的交易列表（包含 pnl 字段的 close trade）
            capital: 初始资金
            n_bars: 回测总 bar 数

        Returns:
            分布统计: {mean_return, median_return, p5/p95_return, ...}
        """
        close_trades = [t for t in trades if t.get("type") == "close"]
        if not close_trades:
            return {"error": "没有平仓交易，无法做 Monte Carlo 模拟"}

        pnls = np.array([t.get("pnl", 0) for t in close_trades])
        rng = np.random.RandomState(self.seed)

        path_returns = []
        path_sharpes = []
        path_drawdowns = []
        path_trade_counts = []

        for sim in range(self.n_simulations):
            # bootstrap: 有放回重采样交易序列
            sampled_pnls = rng.choice(pnls, size=len(pnls), replace=True)
            equity = capital
            equity_curve = [equity]
            for pnl in sampled_pnls:
                equity += pnl
                equity_curve.append(equity)

            # 年化（假设 n_bars 交易日 = 回测总天数）
            if len(equity_curve) < 2:
                continue

            eq = np.array(equity_curve, dtype=float)
            total_ret = eq[-1] / capital - 1

            days = len(eq) - 1
            ann_ret = np.exp(np.log(1 + total_ret) * 252 / days) - 1 if days > 0 and total_ret > -1 else 0
            rets = np.diff(eq) / eq[:-1]
            vol = float(np.std(rets) * np.sqrt(252)) if len(rets) > 1 else 0
            sharpe = (ann_ret - 0.025) / vol if vol > 0 else 0
            peak = np.maximum.accumulate(eq)
            dd = float(np.min((eq - peak) / peak)) * 100

            path_returns.append(total_ret * 100)
            path_sharpes.append(sharpe)
            path_drawdowns.append(dd)
            path_trade_counts.append(len(sampled_pnls))

        if not path_returns:
            return {"error": "所有路径模拟失败"}

        arr = np.array(path_returns)
        sharpe_arr = np.array(path_sharpes)
        dd_arr = np.array(path_drawdowns)

        return {
            "n_simulations": len(path_returns),
            "return_pct": {
                "mean": round(float(np.mean(arr)), 2),
                "median": round(float(np.median(arr)), 2),
                "std": round(float(np.std(arr)), 2),
                "p5": round(float(np.percentile(arr, 5)), 2),
                "p25": round(float(np.percentile(arr, 25)), 2),
                "p75": round(float(np.percentile(arr, 75)), 2),
                "p95": round(float(np.percentile(arr, 95)), 2),
                "min": round(float(np.min(arr)), 2),
                "max": round(float(np.max(arr)), 2),
                "positive_ratio": round(float(np.mean(arr > 0) * 100), 1),
            },
            "sharpe_ratio": {
                "mean": round(float(np.mean(sharpe_arr)), 2),
                "p5": round(float(np.percentile(sharpe_arr, 5)), 2),
                "p95": round(float(np.percentile(sharpe_arr, 95)), 2),
                "positive_ratio": round(float(np.mean(sharpe_arr > 0) * 100), 1),
            },
            "max_drawdown_pct": {
                "mean": round(float(np.mean(dd_arr)), 2),
                "p5": round(float(np.percentile(dd_arr, 5)), 2),
                "p95": round(float(np.percentile(dd_arr, 95)), 2),
            },
            "avg_trades": int(np.mean(path_trade_counts)),
        }
