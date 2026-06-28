"""
内部模拟账户 — 补偿 SimNow 的乐观成交

SimNow 市价单永远以对手价成交（无滑点），限价单到价必成交。
此模块模拟真实市场的滑点和部分成交。
"""
import random
from typing import Optional

from backend.gold.core.models import GoldSignal, GoldTrade, SignalDirection
from backend.gold.core.config import gold_settings


class InternalSimAccount:
    """内部模拟账户 — 在 SimNow 成交基础上叠加滑点补偿"""

    def __init__(self, slippage_ticks: int = 1, fill_ratio: float = 0.95):
        """
        Args:
            slippage_ticks: 市价单滑点跳数（默认 1 跳 = 0.02）
            fill_ratio: 限价单成交概率（默认 95%）
        """
        self.slippage_ticks = slippage_ticks
        self.fill_ratio = fill_ratio
        self.price_tick = gold_settings.au_price_tick

    def simulate_fill(self, signal: GoldSignal,
                      market_price: float) -> Optional[GoldTrade]:
        """
        模拟成交

        Args:
            signal: 交易信号
            market_price: 当前市场价（SimNow Tick 最新价）

        Returns:
            GoldTrade 或 None（未成交）
        """
        # 限价单部分成交概率
        if random.random() > self.fill_ratio:
            return None  # 未成交

        # 计算滑点补偿后的成交价
        slippage = self.price_tick * self.slippage_ticks * random.uniform(0.5, 1.0)

        if signal.direction == SignalDirection.LONG:
            # 买：滑点对买方不利 → 成交价更高
            fill_price = market_price + slippage
            fill_volume = signal.volume
        elif signal.direction == SignalDirection.SHORT:
            fill_price = market_price - slippage
            fill_volume = signal.volume
        elif signal.direction == SignalDirection.CLOSE_LONG:
            fill_price = market_price - slippage
            fill_volume = signal.volume
        elif signal.direction == SignalDirection.CLOSE_SHORT:
            fill_price = market_price + slippage
            fill_volume = signal.volume
        else:
            return None

        # 大单额外滑点（> 5 手）
        if signal.volume > 5:
            extra = self.price_tick * 0.5 * (signal.volume / 5)
            fill_price += extra if signal.direction in (SignalDirection.LONG, SignalDirection.CLOSE_SHORT) else -extra

        from datetime import datetime
        return GoldTrade(
            trade_id=f"sim_{datetime.now().strftime('%Y%m%d%H%M%S')}_{random.randint(1000, 9999)}",
            order_id=f"ORD_{signal.signal_id}",
            symbol=signal.symbol,
            direction=signal.direction,
            price=round(fill_price, 2),
            volume=fill_volume,
            commission=gold_settings.backtest_commission_per_lot * fill_volume,
            slippage=round(abs(fill_price - market_price) * gold_settings.au_multiplier * fill_volume, 2),
            trade_time=datetime.now(),
        )
