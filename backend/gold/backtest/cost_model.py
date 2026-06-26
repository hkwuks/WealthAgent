class CostModel:
    """
    SHFE AU期货交易成本模型

    - 开仓手续费: 10元/手
    - 平仓手续费: 10元/手
    - 平今手续费: 0元/手（SHFE AU平今免费）
    - 滑点: 1跳 = 0.02元/克 × 1000克/手 = 20元/手
    """

    def __init__(self, open_commission_per_lot: float = 10.0,
                 close_commission_per_lot: float = 10.0,
                 close_today_commission_per_lot: float = 0.0,
                 slippage_per_lot: float = 20.0):
        self.open_commission_per_lot = open_commission_per_lot
        self.close_commission_per_lot = close_commission_per_lot
        self.close_today_commission_per_lot = close_today_commission_per_lot
        self.slippage_per_lot = slippage_per_lot

    def open_cost(self, volume: int = 1) -> float:
        """开仓成本 = 开仓手续费 + 滑点"""
        return (self.open_commission_per_lot + self.slippage_per_lot) * volume

    def close_cost(self, volume: int = 1, is_close_today: bool = False) -> float:
        """平仓成本 = 平仓手续费 + 滑点"""
        commission = self.close_today_commission_per_lot if is_close_today else self.close_commission_per_lot
        return (commission + self.slippage_per_lot) * volume

    def round_trip_cost(self, volume: int = 1) -> float:
        """往返总成本"""
        return self.open_cost(volume) + self.close_cost(volume)
