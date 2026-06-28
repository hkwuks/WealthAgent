"""
Tick → Bar 合成器

CTP 提供逐笔 Tick，合成为 1 分钟 Bar，再聚合成多周期 Bar。
"""
from datetime import datetime
from typing import Callable, Optional

from backend.gold.core.models import GoldTickData, GoldBarData
from loguru import logger


class BarAssembler:
    """Tick → 1分钟 → N分钟 OHLCV 合成"""

    def __init__(self, on_bar: Callable[[GoldBarData], None] = None):
        self.on_bar = on_bar
        self._minute_bar: Optional[GoldBarData] = None
        self._bars_1m: list[GoldBarData] = []  # 用于多周期合成

    def update_tick(self, tick: GoldTickData):
        """Tick 更新 → 合成 1 分钟 Bar"""
        ts = tick.datetime
        minute_key = ts.replace(second=0, microsecond=0)

        if self._minute_bar is None:
            self._minute_bar = GoldBarData(
                symbol=tick.symbol, exchange=tick.exchange,
                period="1m", datetime=minute_key,
                open=tick.last_price, high=tick.last_price,
                low=tick.last_price, close=tick.last_price,
                volume=tick.last_volume,
            )
            return

        # 新的一分钟
        if tick.datetime >= self._minute_bar.datetime.replace(second=0) + 60:
            self._finish_bar()
            self._minute_bar = GoldBarData(
                symbol=tick.symbol, exchange=tick.exchange,
                period="1m", datetime=minute_key,
                open=tick.last_price, high=tick.last_price,
                low=tick.last_price, close=tick.last_price,
                volume=tick.last_volume,
            )
            return

        # 更新当前分钟
        b = self._minute_bar
        if tick.last_price > b.high:
            b.high = tick.last_price
        if tick.last_price < b.low:
            b.low = tick.last_price
        b.close = tick.last_price
        b.volume += tick.last_volume

    def _finish_bar(self):
        """完成当前 1 分钟 Bar"""
        if self._minute_bar is None:
            return
        bar = self._minute_bar
        self._bars_1m.append(bar)
        # 保持最近 300 根
        if len(self._bars_1m) > 300:
            self._bars_1m = self._bars_1m[-300:]
        if self.on_bar:
            try:
                self.on_bar(bar)
            except Exception as e:
                logger.debug(f"BarAssembler on_bar error: {e}")

    def get_latest_bar(self, period: str = "1m") -> Optional[GoldBarData]:
        """获取最新 Bar"""
        if period == "1m":
            return self._minute_bar
        # N 分钟 Bar：从 1m bars 中合成
        try:
            window = int(period.replace("m", ""))
        except ValueError:
            return None
        if len(self._bars_1m) < window:
            return None
        recent = self._bars_1m[-window:]
        return GoldBarData(
            symbol=recent[0].symbol, exchange=recent[0].exchange,
            period=period, datetime=recent[0].datetime,
            open=recent[0].open,
            high=max(b.high for b in recent),
            low=min(b.low for b in recent),
            close=recent[-1].close,
            volume=sum(b.volume for b in recent),
        )

    def reset(self):
        self._minute_bar = None
        self._bars_1m.clear()
