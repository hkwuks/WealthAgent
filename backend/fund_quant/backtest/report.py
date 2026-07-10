"""回测报告生成 — 完整指标"""

from typing import List, Dict, Optional
import numpy as np
from ..core.models import BacktestResult
from ..risk.metrics import risk_metrics_calculator


class BacktestReport:
    """回测报告生成器"""

    # ── 策略→默认基准映射 ──
    BENCHMARK_MAP = {
        "momentum": "沪深300",
        "valuation_deviation": "沪深300",
        "multi_factor": "中证800",
        "rating_enhanced": "中证800",
        "risk_parity": "股债50/50",
        "smart_dca": "沪深300",
        "interest_rate": "中证全债",
        "fx_momentum": "QDII混合",
        "black_litterman": "股债60/40",
    }

    @staticmethod
    def generate(result: BacktestResult,
                 benchmark_returns: Optional[List[float]] = None) -> dict:
        """生成结构化回测报告"""
        equity = result.equity_curve
        trades = result.trade_log

        if len(equity) < 2:
            return {"summary": {"strategy": result.config.strategy_name, "status": "insufficient_data"}}

        values = [e["total_value"] for e in equity]
        initial = result.config.initial_capital

        # ── 基础指标 ──
        total_ret = (values[-1] - initial) / initial if initial > 0 else 0.0
        returns = []
        for i in range(1, len(values)):
            if values[i - 1] > 0:
                returns.append((values[i] - values[i - 1]) / values[i - 1])

        metrics = risk_metrics_calculator.calculate(returns)
        ann_return = (1 + total_ret) ** (252 / max(len(values), 1)) - 1

        # ── Sortino (已由RiskMetricsCalculator计算) ──

        # ── 信息比率 (Rp - Rb) / TE ──
        information_ratio = None
        if benchmark_returns and len(benchmark_returns) >= len(returns):
            bench = benchmark_returns[:len(returns)]
            excess = np.array(returns) - np.array(bench)
            te = float(np.std(excess, ddof=1) * np.sqrt(252))
            if te > 1e-10:
                information_ratio = round((ann_return - float(np.mean(bench) * 252)) / te, 4)

        # ── 换手率 ──
        buy_volume = sum(t.get("cost", 0) for t in trades if t.get("action") == "buy_confirmed")
        sell_volume = sum(t.get("proceeds", 0) for t in trades if t.get("action") == "sell_confirmed")
        avg_holdings = (values[0] + values[-1]) / 2 if values else initial
        turnover = (buy_volume + sell_volume) / 2 / max(avg_holdings, 1) if avg_holdings > 0 else 0.0

        # ── 费率损耗率 ──
        total_fees = sum(t.get("cost", 0) for t in trades if t.get("action") == "buy_confirmed") * 0.01
        fee_leakage = total_fees / max(total_ret * initial, initial) if max(total_ret * initial, initial) > 0 else 0.0

        # ── 最大连续亏损天数 ──
        max_consecutive_loss_days = 0
        current_streak = 0
        for r in returns:
            if r < 0:
                current_streak += 1
                max_consecutive_loss_days = max(max_consecutive_loss_days, current_streak)
            else:
                current_streak = 0

        # ── 分年度收益 ──
        period_returns = dict(result.period_returns or {})
        if not period_returns:
            yearly: Dict[str, List[float]] = {}
            for e in equity:
                yr = e["date"][:4]
                yearly.setdefault(yr, []).append(e["total_value"])
            for yr, vals in yearly.items():
                if len(vals) > 1:
                    period_returns[yr] = round((vals[-1] - vals[0]) / vals[0], 6)

        # ── 基准选择 ──
        benchmark_name = result.config.benchmark_name if result.config and hasattr(result.config, 'benchmark_name') else \
            BacktestReport.BENCHMARK_MAP.get(getattr(result.config, 'strategy_name', ''), "无基准")
        benchmark_return = None
        if benchmark_returns and len(benchmark_returns) > 1:
            benchmark_return = round(float(np.prod(1 + np.array(benchmark_returns[-len(returns):]))) - 1, 4)

        # ── 胜率 ──
        sell_trades = [t for t in trades if t["action"] == "sell_confirmed"]
        wins = sum(1 for t in sell_trades if t.get("proceeds", 0) > t.get("cost", 0))
        win_rate = wins / len(sell_trades) if sell_trades else 0.0

        return {
            "summary": {
                "strategy": result.config.strategy_name,
                "fund_codes": result.config.fund_codes,
                "period": f"{result.config.start_date} ~ {result.config.end_date}",
                "initial_capital": result.config.initial_capital,
                "status": result.status,
                "benchmark": benchmark_name,
            },
            "performance": {
                "total_return": f"{total_ret * 100:.2f}%",
                "annual_return": f"{ann_return * 100:.2f}%",
                "max_drawdown": f"{metrics.max_drawdown * 100:.2f}%",
                "sharpe_ratio": round(metrics.sharpe_ratio or 0.0, 4),
                "sortino_ratio": round(metrics.sortino_ratio or 0.0, 4),
                "calmar_ratio": round(metrics.calmar_ratio or 0.0, 4),
                "information_ratio": information_ratio,
                "win_rate": f"{win_rate * 100:.1f}%",
                "turnover": round(turnover, 4),
                "fee_leakage": f"{fee_leakage * 100:.2f}%",
                "max_consecutive_loss_days": max_consecutive_loss_days,
            },
            "benchmark": {
                "name": benchmark_name,
                "return": f"{benchmark_return * 100:.2f}%" if benchmark_return is not None else None,
            },
            "trades": {
                "total": result.total_trades,
                "log": trades,
            },
            "equity_curve": equity,
            "period_returns": period_returns,
        }


backtest_report = BacktestReport()
