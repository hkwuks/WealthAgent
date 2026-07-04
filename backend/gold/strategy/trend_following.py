from backend.gold.strategy.base import StrategyBase, StrategyRegistry, StrategyContext
from backend.gold.core.models import GoldBarData, SignalDirection


@StrategyRegistry.register("trend_following")
class TrendFollowingStrategy(StrategyBase):
    """多周期均线突破 + Donchian通道 + ATR止损"""

    strategy_name = "trend_following"
    strategy_type = "trend_following"
    description = "MA排列 + Donchian突破 + ATR止损"
    default_params = {
        "ma_periods": [5, 20, 60],
        "atr_period": 14,
        "atr_stop_multiplier": 2.0,
        "donchian_entry": 20,
        "donchian_exit": 10,
        "position_size": 1,
        "target_vol_pct": 0.10,
    }
    param_ranges = {
        "atr_stop_multiplier": [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
        "donchian_entry": [10, 15, 20, 25, 30, 40, 55],
        "donchian_exit": [5, 8, 10, 12, 15, 20],
    }

    def on_init(self, context: StrategyContext):
        self._bars: list[GoldBarData] = []
        self._ma_values: dict[int, float] = {}
        self._atr_value: float = 0
        self._donchian_high: float = 0
        self._donchian_low: float = 0
        self._position: int = 0
        self._entry_price: float = 0

    def on_bar(self, bar: GoldBarData):
        self._bars.append(bar)
        max_period = max(self.ma_periods) + 10
        if len(self._bars) > max_period:
            self._bars = self._bars[-max_period:]

        self._calculate_indicators()

        if len(self._bars) < max(self.ma_periods):
            return

        self._check_signals(bar)

    def _calculate_indicators(self):
        closes = [b.close for b in self._bars]

        for period in self.ma_periods:
            if len(closes) >= period:
                self._ma_values[period] = sum(closes[-period:]) / period

        if len(self._bars) >= self.atr_period + 1:
            trs = []
            for i in range(1, len(self._bars)):
                bar, prev = self._bars[i], self._bars[i - 1]
                tr = max(bar.high - bar.low,
                         abs(bar.high - prev.close),
                         abs(bar.low - prev.close))
                trs.append(tr)
            self._atr_value = sum(trs[-self.atr_period:]) / self.atr_period

        # Donchian用前N-1根bar计算（不含当前bar），这样当前bar可突破
        if len(self._bars) >= self.donchian_entry:
            prior = self._bars[-(self.donchian_entry):-1] if len(self._bars) > self.donchian_entry else self._bars[:-1]
            self._donchian_high = max(b.high for b in prior) if prior else 0
            self._donchian_low = min(b.low for b in prior) if prior else 0

    def _check_signals(self, bar: GoldBarData):
        # 用索引而非硬编码，支持自定义ma_periods
        ma_fast = self._ma_values.get(self.ma_periods[0])
        ma_mid = self._ma_values.get(self.ma_periods[1])
        ma_slow = self._ma_values.get(self.ma_periods[2])
        if ma_fast is None or ma_mid is None or ma_slow is None:
            return

        price = bar.close
        dt = bar.datetime

        if self._position == 0:
            if ma_fast > ma_mid > ma_slow and bar.high > self._donchian_high:
                sl = price - self._atr_value * self.atr_stop_multiplier
                self.emit_signal(SignalDirection.LONG, bar.symbol, price,
                                 self.position_size, stop_loss=sl,
                                 confidence=0.7,
                                 reason=f"MA多头排列+Donchian突破 ATR={self._atr_value:.2f}",
                                 bar_datetime=dt)
                self._position = 1
                self._entry_price = price

            elif ma_fast < ma_mid < ma_slow and bar.low < self._donchian_low:
                sl = price + self._atr_value * self.atr_stop_multiplier
                self.emit_signal(SignalDirection.SHORT, bar.symbol, price,
                                 self.position_size, stop_loss=sl,
                                 confidence=0.7,
                                 reason=f"MA空头排列+Donchian突破 ATR={self._atr_value:.2f}",
                                 bar_datetime=dt)
                self._position = -1
                self._entry_price = price

        elif self._position == 1:
            sl = self._entry_price - self._atr_value * self.atr_stop_multiplier
            if price < sl:
                self.emit_signal(SignalDirection.CLOSE_LONG, bar.symbol, price,
                                 self.position_size, reason="ATR止损", bar_datetime=dt)
                self._position = 0
            elif price < self._donchian_low:
                self.emit_signal(SignalDirection.CLOSE_LONG, bar.symbol, price,
                                 self.position_size, reason="Donchian出场", bar_datetime=dt)
                self._position = 0
            elif ma_fast < ma_mid:
                self.emit_signal(SignalDirection.CLOSE_LONG, bar.symbol, price,
                                 self.position_size, reason="MA死叉", bar_datetime=dt)
                self._position = 0

        elif self._position == -1:
            sl = self._entry_price + self._atr_value * self.atr_stop_multiplier
            if price > sl:
                self.emit_signal(SignalDirection.CLOSE_SHORT, bar.symbol, price,
                                 self.position_size, reason="ATR止损", bar_datetime=dt)
                self._position = 0
            elif price > self._donchian_high:
                self.emit_signal(SignalDirection.CLOSE_SHORT, bar.symbol, price,
                                 self.position_size, reason="Donchian出场", bar_datetime=dt)
                self._position = 0
            elif ma_fast > ma_mid:
                self.emit_signal(SignalDirection.CLOSE_SHORT, bar.symbol, price,
                                 self.position_size, reason="MA金叉", bar_datetime=dt)
                self._position = 0

    def reset_for_signal(self):
        """重置持仓状态 — 信号生成模式只看当前bar是否满足入场条件
        保留已计算的K线和指标历史，仅清空持仓状态和信号列表。
        """
        self._position = 0
        self._entry_price = 0
        self._signals = []
