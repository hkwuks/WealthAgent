from backend.gold.strategy.base import StrategyBase, StrategyRegistry, StrategyContext
from backend.gold.core.models import GoldBarData, SignalDirection


@StrategyRegistry.register("mean_reversion")
class MeanReversionStrategy(StrategyBase):
    """布林带回归 + RSI确认"""

    strategy_name = "mean_reversion"
    strategy_type = "mean_reversion"
    description = "BB下轨+RSI超卖做多 / BB上轨+RSI超买做空"
    default_params = {
        "boll_period": 20,
        "boll_dev": 2.0,
        "rsi_period": 14,
        "rsi_overbought": 70,
        "rsi_oversold": 30,
        "atr_stop_multiplier": 2.0,
        "position_size": 1,
        "target_vol_pct": 0.10,
    }
    param_ranges = {
        "boll_period": [10, 15, 20, 25, 30, 40, 50],
        "boll_dev": [1.5, 2.0, 2.5, 3.0],
        "rsi_overbought": [60, 65, 70, 75, 80, 85],
        "rsi_oversold": [15, 20, 25, 30, 35, 40],
    }

    def on_init(self, context: StrategyContext):
        self._bars: list[GoldBarData] = []
        self._position: int = 0
        self._entry_price: float = 0

    def on_bar(self, bar: GoldBarData):
        self._bars.append(bar)
        if len(self._bars) > self.boll_period + 20:
            self._bars = self._bars[-(self.boll_period + 20):]

        bb_upper, bb_middle, bb_lower = self._calc_bollinger()
        rsi = self._calc_rsi()
        atr = self._calc_atr()

        if bb_upper is None or rsi is None:
            return

        price = bar.close
        dt = bar.datetime

        if self._position == 0:
            if price <= bb_lower and rsi < self.rsi_oversold:
                sl = price - atr * self.atr_stop_multiplier
                self.emit_signal(SignalDirection.LONG, bar.symbol, price,
                                 self.position_size, stop_loss=sl,
                                 confidence=0.6,
                                 reason=f"BB下轨+RSI超卖({rsi:.1f})",
                                 bar_datetime=dt)
                self._position = 1
                self._entry_price = price

            elif price >= bb_upper and rsi > self.rsi_overbought:
                sl = price + atr * self.atr_stop_multiplier
                self.emit_signal(SignalDirection.SHORT, bar.symbol, price,
                                 self.position_size, stop_loss=sl,
                                 confidence=0.6,
                                 reason=f"BB上轨+RSI超买({rsi:.1f})",
                                 bar_datetime=dt)
                self._position = -1
                self._entry_price = price

        elif self._position == 1:
            if price >= bb_middle:
                self.emit_signal(SignalDirection.CLOSE_LONG, bar.symbol, price,
                                 self.position_size, reason="回归中轨", bar_datetime=dt)
                self._position = 0
            elif atr > 0 and price < self._entry_price - atr * self.atr_stop_multiplier:
                self.emit_signal(SignalDirection.CLOSE_LONG, bar.symbol, price,
                                 self.position_size, reason="ATR止损", bar_datetime=dt)
                self._position = 0

        elif self._position == -1:
            if price <= bb_middle:
                self.emit_signal(SignalDirection.CLOSE_SHORT, bar.symbol, price,
                                 self.position_size, reason="回归中轨", bar_datetime=dt)
                self._position = 0
            elif atr > 0 and price > self._entry_price + atr * self.atr_stop_multiplier:
                self.emit_signal(SignalDirection.CLOSE_SHORT, bar.symbol, price,
                                 self.position_size, reason="ATR止损", bar_datetime=dt)
                self._position = 0

    def _calc_bollinger(self):
        if len(self._bars) < self.boll_period:
            return None, None, None
        closes = [b.close for b in self._bars]
        recent = closes[-self.boll_period:]
        middle = sum(recent) / len(recent)
        variance = sum((x - middle) ** 2 for x in recent) / len(recent)
        std = variance ** 0.5
        return middle + self.boll_dev * std, middle, middle - self.boll_dev * std

    def _calc_rsi(self):
        if len(self._bars) < self.rsi_period + 1:
            return None
        closes = [b.close for b in self._bars]
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        if len(gains) < self.rsi_period:
            return None
        avg_gain = sum(gains[-self.rsi_period:]) / self.rsi_period
        avg_loss = sum(losses[-self.rsi_period:]) / self.rsi_period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - 100 / (1 + rs)

    def _calc_atr(self):
        if len(self._bars) < 14 + 1:
            return 0
        trs = []
        for i in range(1, len(self._bars)):
            bar, prev = self._bars[i], self._bars[i - 1]
            tr = max(bar.high - bar.low,
                     abs(bar.high - prev.close),
                     abs(bar.low - prev.close))
            trs.append(tr)
        return sum(trs[-14:]) / 14
