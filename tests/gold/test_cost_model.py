"""回测成本模型测试"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from gold.backtest.cost_model import CostModel


class TestCostModel:
    def test_default_cost_model(self):
        cm = CostModel()
        assert cm.open_commission_per_lot == 10.0
        assert cm.close_commission_per_lot == 10.0
        assert cm.close_today_commission_per_lot == 0.0
        assert cm.dynamic_slippage is True

    def test_fixed_slippage_when_no_atr(self):
        cm = CostModel(dynamic_slippage=False, slippage_per_lot=20)
        assert cm.open_cost(1) == 30  # 10 + 20
        assert cm.close_cost(1) == 30  # 10 + 20
        assert cm.round_trip_cost(1) == 60

    def test_open_cost_with_atr(self):
        cm = CostModel(slippage_atr_ratio=0.5, multiplier=1000)
        cost = cm.open_cost(1, atr_value=2.0)
        # 手续费 10 + 滑点 0.5*2.0*1000 = 1000
        assert cost == 10 + 0.5 * 2.0 * 1000

    def test_close_cost_is_close_today(self):
        cm = CostModel(open_commission_per_lot=10, close_commission_per_lot=10,
                       close_today_commission_per_lot=0)
        # 平今
        c = cm.close_cost(1, is_close_today=True, atr_value=None)
        assert c == 0 + 20  # 平今免费 + 固定滑点
        # 平昨
        c2 = cm.close_cost(1, is_close_today=False, atr_value=None)
        assert c2 == 10 + 20  # 平仓手续费 + 固定滑点

    def test_round_trip_cost(self):
        cm = CostModel(dynamic_slippage=False)
        assert cm.round_trip_cost(2) == 2 * (10 + 20) + 2 * (10 + 20)

    def test_zero_volume(self):
        cm = CostModel(dynamic_slippage=False)
        assert cm.open_cost(0) == 0
        assert cm.close_cost(0) == 0

    def test_dynamic_slippage_disabled_uses_fixed(self):
        cm = CostModel(dynamic_slippage=False, slippage_per_lot=15)
        assert cm._slippage(1, atr_value=5.0) == 15
        assert cm._slippage(2, atr_value=5.0) == 30
