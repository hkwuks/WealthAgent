"""申购费打折测试"""

import pytest
from backend.fund_quant.backtest.cost_model import FundCostModel
from backend.fund_quant.core.models import CostModelConfig


class TestSubscriptionDiscount:
    def test_default_discount_slash_cost(self):
        """默认 1 折 (0.10), 1.5% 申购费按 1 万计算应为 15 元 (非 150 元)"""
        config = CostModelConfig(subscription_fee_tiers={"stock": 0.015})
        model = FundCostModel(config)
        model.set_discount(0.10)
        fee = model.get_subscription_fee("stock", amount=10000)
        assert fee == 15.0  # 10000 * 0.015 * 0.1

    def test_no_discount_full_rate(self):
        """discount=1.0 时恢复全额费率"""
        config = CostModelConfig(subscription_fee_tiers={"stock": 0.015})
        model = FundCostModel(config)
        model.set_discount(1.0)
        fee = model.get_subscription_fee("stock", amount=10000)
        assert fee == 150.0  # 10000 * 0.015 * 1.0

    def test_discount_default_on_instance(self):
        """未 set_discount 时默认 0.10"""
        config = CostModelConfig(subscription_fee_tiers={"stock": 0.015})
        model = FundCostModel(config)
        fee = model.get_subscription_fee("stock", amount=10000)
        assert fee == 15.0
