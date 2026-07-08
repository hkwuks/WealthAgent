"""评级增强选基策略"""

from typing import Optional, List
from ..base import FundStrategyBase, StrategyRegistry
from ...core.enums import SignalType, Direction
from ...core.models import FundSignal, Portfolio, InformationSet


class RatingEnhancedSelection(FundStrategyBase):
    """评级增强选基策略"""
    strategy_name = "rating_enhanced"
    strategy_type = "selection"
    description = "晨星评级 + 量化因子 + 估值偏差的基金评分策略"
    default_params = {
        "rating_weight": 0.35,
        "quant_weight": 0.45,
        "deviation_weight": 0.20,
    }
    applicable_fund_types = ["stock", "hybrid", "bond", "index"]
    min_history_days = 365

    def on_evaluate(self, portfolio: Optional[Portfolio],
                    info_set: Optional[InformationSet]) -> List[FundSignal]:
        return []


StrategyRegistry.register(RatingEnhancedSelection)
