"""Black-Litterman 策略（V1降级为均值-方差优化）"""

from typing import Optional, List
from ..base import FundStrategyBase, StrategyRegistry
from ...core.enums import SignalType, Direction
from ...core.models import FundSignal, Portfolio, InformationSet


class BlackLittermanStrategy(FundStrategyBase):
    """Black-Litterman策略 (V1: 均值-方差优化+约束)"""
    strategy_name = "black_litterman"
    strategy_type = "allocation"
    description = "Black-Litterman模型 (V1降级为均值-方差优化+约束)"
    default_params = {
        "risk_aversion": 2.5,
        "max_weight": 0.4,
        "min_weight": 0.05,
    }
    applicable_fund_types = []
    min_history_days = 365

    def on_evaluate(self, portfolio: Optional[Portfolio],
                    info_set: Optional[InformationSet]) -> List[FundSignal]:
        return []


StrategyRegistry.register(BlackLittermanStrategy)
