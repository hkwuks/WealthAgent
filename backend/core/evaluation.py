"""评估层 — Metrics, MetricsCalculator, ComparisonReport"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Metrics:
    """统一回测评估指标"""
    # 收益
    total_return: float = 0.0
    annual_return: float = 0.0
    monthly_returns: list[float] = field(default_factory=list)
    # 风险
    volatility: float = 0.0
    max_drawdown: float = 0.0
    var_95: float = 0.0
    cvar_95: float = 0.0
    # 风险调整
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    # 交易统计
    total_trades: int = 0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0


class MetricsCalculator:
    """指标计算器 — 从权益曲线+交易列表计算"""

    @staticmethod
    def calculate(equity_curve: list[float],
                  trades: list[dict] | None = None,
                  risk_free: float = 0.02,
                  periods_per_year: int = 252) -> Metrics:
        """计算全部指标

        >>> m = MetricsCalculator.calculate([100, 110, 108, 115, 120])
        >>> round(m.total_return, 2)
        0.2
        >>> m.total_trades
        0
        """
        if len(equity_curve) < 2:
            return Metrics()

        # 日收益率
        returns = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1]
            if prev != 0:
                returns.append(equity_curve[i] / prev - 1)

        if not returns:
            return Metrics()

        total_return = equity_curve[-1] / equity_curve[0] - 1
        n = len(returns)

        # 年化收益
        annual_return = (1 + total_return) ** (periods_per_year / n) - 1

        # 波动率
        mean_r = sum(returns) / n
        variance = sum((r - mean_r) ** 2 for r in returns) / n
        volatility = math.sqrt(variance * periods_per_year)

        # 最大回撤
        peak = equity_curve[0]
        max_dd = 0.0
        for val in equity_curve[1:]:
            if val > peak:
                peak = val
            dd = (peak - val) / peak
            if dd > max_dd:
                max_dd = dd

        # Sharpe
        sharpe = 0.0
        if volatility > 1e-10:
            sharpe = (annual_return - risk_free) / volatility

        # Sortino — 只用下行波动
        neg_returns = [r for r in returns if r < 0]
        sortino = 0.0
        if neg_returns:
            down_var = sum(r ** 2 for r in neg_returns) / n
            down_vol = math.sqrt(down_var * periods_per_year)
            if down_vol > 1e-10:
                sortino = (annual_return - risk_free) / down_vol

        # Calmar
        calmar = 0.0
        if max_dd > 1e-10:
            calmar = annual_return / max_dd

        # VaR(95%) — 简单分位数
        sorted_r = sorted(returns)
        var_idx = max(0, int(n * 0.05) - 1)
        var_95 = abs(sorted_r[var_idx])
        cvar_95 = abs(sum(sorted_r[:var_idx + 1]) / (var_idx + 1))

        metrics = Metrics(
            total_return=round(total_return, 6),
            annual_return=round(annual_return, 6),
            volatility=round(volatility, 6),
            max_drawdown=round(max_dd, 6),
            sharpe_ratio=round(sharpe, 4),
            sortino_ratio=round(sortino, 4),
            calmar_ratio=round(calmar, 4),
            var_95=round(var_95, 6),
            cvar_95=round(cvar_95, 6),
        )

        # 交易统计
        if trades:
            n_trades = len(trades)
            wins = [t for t in trades if t.get("pnl", 0) > 0]
            losses = [t for t in trades if t.get("pnl", 0) <= 0]
            metrics.total_trades = n_trades
            metrics.win_rate = len(wins) / n_trades if n_trades > 0 else 0.0

            avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
            avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses)) if losses else 1
            metrics.profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0

        return metrics


@dataclass
class ComparisonReport:
    """多策略对比报告"""
    rankings: dict[str, Metrics] = field(default_factory=dict)

    def add(self, name: str, metrics: Metrics):
        self.rankings[name] = metrics

    def sorted(self, by: str = "sharpe_ratio", ascending: bool = False) -> list[tuple[str, Metrics]]:
        return sorted(
            self.rankings.items(),
            key=lambda kv: getattr(kv[1], by, 0),
            reverse=not ascending,
        )

    def to_dict(self) -> dict:
        return {name: {k: getattr(m, k) for k in [
            "total_return", "sharpe_ratio", "max_drawdown",
            "volatility", "total_trades", "win_rate",
        ]} for name, m in self.rankings.items()}


def demo():
    """评估层自检"""
    # MetricsCalculator
    equity = [100.0, 50.0, 75.0, 105.0, 90.0, 130.0]
    m = MetricsCalculator.calculate(equity)
    assert m.total_return == 0.3  # 130/100 - 1
    assert m.total_trades == 0

    # 带交易
    trades = [{"pnl": 10}, {"pnl": -5}, {"pnl": 8}, {"pnl": -3}]
    m2 = MetricsCalculator.calculate(equity, trades)
    assert m2.total_trades == 4
    assert 0.4 < m2.win_rate < 0.6  # 2 wins / 4 trades = 0.5

    # ComparisonReport
    cr = ComparisonReport()
    cr.add("strat_a", m)
    cr.add("strat_b", m2)
    assert len(cr.sorted()) == 2
    assert "strat_a" in cr.to_dict()

    print("[evaluation] ✅ 评估层通过")


if __name__ == "__main__":
    demo()
