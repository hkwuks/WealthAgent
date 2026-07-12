"""FundQuant 风险度量 - VaR/CVaR/波动率/夏普比率"""

import math
import numpy as np
from typing import List, Optional
from ..core.models import RiskMetrics


class RiskMetricsCalculator:
    """风险度量计算器"""

    @staticmethod
    def calculate(returns: List[float], risk_free_rate: float = 0.02) -> RiskMetrics:
        """计算风险指标"""
        if not returns or len(returns) < 5:
            return RiskMetrics()

        arr = np.array(returns, dtype=np.float64)
        n = len(arr)
        mean = np.mean(arr)
        std = np.std(arr, ddof=1)

        # VaR 95%
        sorted_returns = np.sort(arr)
        var_idx = max(0, int(n * 0.05) - 1)
        var_95 = abs(sorted_returns[var_idx])

        # CVaR 95%
        cvar_95 = abs(sorted_returns[:var_idx + 1].mean()) if var_idx > 0 else var_95 * 1.5

        # 年化波动率
        ann_factor = math.sqrt(252)
        volatility = float(std * ann_factor)

        # 最大回撤
        cum = np.cumprod(1 + arr)
        peak = np.maximum.accumulate(cum)
        drawdown = (cum - peak) / peak
        max_drawdown = float(abs(drawdown.min())) if len(drawdown) > 0 else 0.0

        # 夏普比率
        ann_return = float(mean * 252)
        sharpe = (ann_return - risk_free_rate) / volatility if volatility > 0 else None

        # Sortino比率
        downside = arr[arr < 0]
        downside_std = np.std(downside, ddof=1) * ann_factor if len(downside) > 1 else 1.0
        sortino = (ann_return - risk_free_rate) / downside_std if downside_std > 0 else None

        # 卡尔玛比率
        calmar = ann_return / max_drawdown if max_drawdown > 0 else None

        return RiskMetrics(
            var_95=round(var_95, 6),
            cvar_95=round(cvar_95, 6),
            max_drawdown=round(max_drawdown, 6),
            volatility=round(volatility, 6),
            sharpe_ratio=round(sharpe, 4) if sharpe is not None else None,
            sortino_ratio=round(sortino, 4) if sortino is not None else None,
            calmar_ratio=round(calmar, 4) if calmar is not None else None,
        )


risk_metrics_calculator = RiskMetricsCalculator()
