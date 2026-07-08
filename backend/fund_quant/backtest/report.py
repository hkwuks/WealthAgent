"""回测报告生成"""

from typing import List, Dict, Optional
from ..core.models import BacktestResult
from ..risk.metrics import risk_metrics_calculator


class BacktestReport:
    """回测报告生成器"""

    @staticmethod
    def generate(result: BacktestResult) -> dict:
        """生成结构化回测报告"""
        equity = result.equity_curve
        trades = result.trade_log

        # 计算各年度收益
        period_returns = {}
        for p in result.period_returns or {}:
            period_returns[p] = result.period_returns[p]

        return {
            "summary": {
                "strategy": result.config.strategy_name,
                "fund_codes": result.config.fund_codes,
                "period": f"{result.config.start_date} ~ {result.config.end_date}",
                "initial_capital": result.config.initial_capital,
                "status": result.status,
            },
            "performance": {
                "total_return": f"{result.total_return * 100:.2f}%",
                "annual_return": f"{result.annual_return * 100:.2f}%",
                "max_drawdown": f"{result.max_drawdown * 100:.2f}%",
                "sharpe_ratio": round(result.sharpe_ratio, 4),
                "calmar_ratio": round(result.calmar_ratio, 4),
                "win_rate": f"{result.win_rate * 100:.1f}%",
            },
            "trades": {
                "total": result.total_trades,
                "log": trades,
            },
            "equity_curve": equity,
            "period_returns": period_returns,
        }


backtest_report = BacktestReport()
