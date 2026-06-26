from backend.gold.strategy.base import StrategyBase, StrategyRegistry

# 导入策略模块以触发注册
import backend.gold.strategy.trend_following
import backend.gold.strategy.mean_reversion
import backend.gold.strategy.ml_predictor

__all__ = ["StrategyBase", "StrategyRegistry"]
