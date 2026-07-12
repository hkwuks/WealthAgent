"""数据抽象层 — Bar / FundNavPoint / DataFeed 接口"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class Bar:
    """通用 K 线（期货/股票/ETF）"""
    symbol: str
    exchange: str
    timeframe: str          # 1m / 5m / 1d / 1w
    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    open_interest: float = 0
    extra: dict = field(default_factory=dict)


@dataclass
class FundNavPoint:
    """基金净值点（非 K 线）"""
    fund_code: str
    date: date
    nav: float
    adjusted_nav: float | None = None
    estimated_nav: float | None = None
    valuation_deviation: float | None = None


class DataFeed(ABC):
    """数据源接口 — 无论 Bar 还是 NavPoint，都通过此接口获取"""

    @abstractmethod
    def get_bars(self, symbol: str, since: date, until: date) -> list[Bar]:
        """获取历史 K 线"""
        ...

    @abstractmethod
    def get_latest(self, symbol: str) -> Bar | None:
        """获取最新数据点"""
        ...


class FundDataFeed(ABC):
    """基金数据源接口"""

    @abstractmethod
    def get_nav(self, fund_code: str, since: date, until: date) -> list[FundNavPoint]:
        ...


def demo():
    """数据模型自检"""
    from datetime import datetime

    bar = Bar(
        symbol="AU0", exchange="SHFE", timeframe="1d",
        datetime=datetime(2026, 7, 11),
        open=600.0, high=605.0, low=599.0, close=603.5, volume=10000,
    )
    assert bar.symbol == "AU0"
    assert bar.close == 603.5

    nav = FundNavPoint(fund_code="000001", date=date(2026, 7, 11), nav=1.2345)
    assert nav.nav == 1.2345

    print("[data] ✅ 数据模型通过")


if __name__ == "__main__":
    demo()
