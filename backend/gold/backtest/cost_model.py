"""
SHFE AU期货交易成本模型

改进:
- 动态滑点: ATR × 系数，区分开平
- 平今/平昨手续费区分
- 可接策略自定义手续费率
"""

from typing import Optional


class CostModel:
    """
    SHFE AU期货交易成本模型

    - 开仓手续费: 10元/手
    - 平仓手续费: 10元/手
    - 平今手续费: 0元/手（SHFE AU平今免费）
    - 动态滑点: ATR × slippage_atr_ratio（默认 0.5 × ATR点值）
    """

    def __init__(self, open_commission_per_lot: float = 10.0,
                 close_commission_per_lot: float = 10.0,
                 close_today_commission_per_lot: float = 0.0,
                 slippage_per_lot: float = 20.0,
                 dynamic_slippage: bool = True,
                 slippage_atr_ratio: float = 0.5,
                 multiplier: int = 1000):
        self.open_commission_per_lot = open_commission_per_lot
        self.close_commission_per_lot = close_commission_per_lot
        self.close_today_commission_per_lot = close_today_commission_per_lot
        self._fixed_slippage_per_lot = slippage_per_lot
        self.dynamic_slippage = dynamic_slippage
        self.slippage_atr_ratio = slippage_atr_ratio
        self.multiplier = multiplier

    def open_cost(self, volume: int = 1, atr_value: float = None) -> float:
        """开仓成本 = 开仓手续费 + 滑点"""
        slip = self._slippage(volume, atr_value)
        return self.open_commission_per_lot * volume + slip

    def close_cost(self, volume: int = 1, is_close_today: bool = False,
                   atr_value: float = None) -> float:
        """平仓成本 = 平仓手续费 + 滑点"""
        commission = self.close_today_commission_per_lot if is_close_today else self.close_commission_per_lot
        slip = self._slippage(volume, atr_value)
        return commission * volume + slip

    def round_trip_cost(self, volume: int = 1, atr_value: float = None) -> float:
        """往返总成本"""
        return self.open_cost(volume, atr_value) + self.close_cost(volume, atr_value=atr_value)

    def _slippage(self, volume: int, atr_value: float = None) -> float:
        """计算滑点成本"""
        if self.dynamic_slippage and atr_value and atr_value > 0:
            # ATR点值(元/克) × 合约乘数 × 比率 × 手数
            return self.slippage_atr_ratio * atr_value * self.multiplier * volume
        return self._fixed_slippage_per_lot * volume
