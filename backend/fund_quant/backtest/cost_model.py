"""费率模型 - 按基金类型差异化"""

from typing import Dict, Optional
from ..core.models import CostModelConfig


class FundCostModel:
    """基金费率模型"""

    def __init__(self, config: Optional[CostModelConfig] = None):
        self.config = config or CostModelConfig()

    def get_subscription_fee(self, fund_type: str, amount: float = 100000.0) -> float:
        """获取申购费率"""
        tiers = self.config.subscription_fee_tiers
        return tiers.get(fund_type, 0.015) * amount

    def get_redemption_fee(self, fund_type: str, holding_days: int) -> float:
        """获取赎回费率（按持有期）"""
        discounts = self.config.holding_period_discount
        sorted_periods = sorted(discounts.keys())
        for period in sorted_periods:
            if holding_days < period:
                return discounts[period] / 100.0
        return discounts.get(9999, 0.0)

    def get_management_fee(self, fund_type: str) -> float:
        """获取管理费率（年化）"""
        fees = self.config.management_fee_rate
        return fees.get(fund_type, 0.015)

    def estimate_trade_cost(self, fund_type: str, amount: float,
                            holding_days: int) -> Dict[str, float]:
        """估算一次交易的综合成本"""
        sub_fee = self.get_subscription_fee(fund_type, amount)
        red_fee = self.get_redemption_fee(fund_type, holding_days) * amount
        return {
            "subscription_fee": round(sub_fee, 2),
            "redemption_fee": round(red_fee, 2),
            "total_cost": round(sub_fee + red_fee, 2),
            "cost_pct": round((sub_fee + red_fee) / amount * 100, 4) if amount > 0 else 0,
        }

    @staticmethod
    def should_use_c_class(holding_days: int) -> bool:
        """判断是否应使用C类份额"""
        return holding_days < 547  # 1.5年


fund_cost_model = FundCostModel()
