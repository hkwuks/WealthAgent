import pandas as pd
from datetime import datetime
from loguru import logger

from backend.gold.core.models import GoldBarData
from backend.gold.data.storage import GoldDataStore


class GoldDataGateway:
    """黄金数据网关 — AkShare + yFinance + SQLite"""

    def __init__(self, db_path: str = "data/gold/gold.db"):
        self.db_path = db_path
        self.store = GoldDataStore(db_path)

    async def get_bars(self, symbol: str = "AU0", period: str = "d",
                       start: str = None, end: str = None,
                       limit: int = None) -> list[GoldBarData]:
        """获取K线数据 — 优先SQLite，miss时从AkShare拉取"""
        bars = self.store.get_bars(symbol, period, start, end, limit)
        if bars:
            return bars

        bars = await self._fetch_from_akshare(symbol, period, start, end)
        if not bars:
            bars = await self._fetch_from_yfinance(start, end, period)

        if bars:
            self.store.save_bars(bars, period)
        return bars

    async def _fetch_from_akshare(self, symbol: str, period: str,
                                   start: str = None, end: str = None) -> list[GoldBarData]:
        """从AkShare获取SHFE黄金数据"""
        try:
            import akshare as ak
        except ImportError:
            logger.warning("akshare not installed, skip AkShare fetch")
            return []

        try:
            if period == "d":
                df = ak.futures_main_sina(symbol=symbol, start_date=start, end_date=end)
            else:
                period_map = {"1m": "1", "5m": "5", "15m": "15", "60m": "60"}
                ak_period = period_map.get(period, "1")
                df = ak.futures_zh_minute_sina(symbol=symbol, period=ak_period)

            return self._df_to_bars(df, symbol, period)
        except Exception as e:
            logger.warning(f"AkShare数据获取失败: {symbol} {period}, {e}")
            return []

    async def _fetch_from_yfinance(self, start: str, end: str,
                                    period: str = "d") -> list[GoldBarData]:
        """Fallback: yFinance COMEX黄金（GC=F）"""
        try:
            import yfinance as yf
        except ImportError:
            return []

        try:
            ticker = yf.Ticker("GC=F")
            df = ticker.history(start=start, end=end)
            if df.empty:
                return []
            bars = []
            for idx, row in df.iterrows():
                bars.append(GoldBarData(
                    symbol="GC=F", exchange="COMEX", period=period,
                    datetime=idx.to_pydatetime(),
                    open=float(row["Open"]), high=float(row["High"]),
                    low=float(row["Low"]), close=float(row["Close"]),
                    volume=float(row.get("Volume", 0)),
                ))
            return bars
        except Exception as e:
            logger.warning(f"yFinance数据获取失败: {e}")
            return []

    def _df_to_bars(self, df: pd.DataFrame, symbol: str,
                     period: str) -> list[GoldBarData]:
        """AkShare DataFrame → GoldBarData列表"""
        if df is None or df.empty:
            return []

        bars = []
        for _, row in df.iterrows():
            dt = row.get("日期") or row.get("时间") or row.get("datetime")
            if isinstance(dt, str):
                dt = pd.to_datetime(dt)
            elif hasattr(dt, 'to_pydatetime'):
                dt = dt.to_pydatetime()
            if dt is None:
                continue

            bar = GoldBarData(
                symbol=symbol, exchange="SHFE", period=period,
                datetime=dt,
                open=float(row.get("开盘价", row.get("open", 0))),
                high=float(row.get("最高价", row.get("high", 0))),
                low=float(row.get("最低价", row.get("low", 0))),
                close=float(row.get("收盘价", row.get("close", 0))),
                volume=float(row.get("成交量", row.get("volume", 0))),
                turnover=float(row.get("成交额", row.get("turnover", 0))),
                open_interest=float(row.get("持仓量", row.get("open_interest", 0))),
            )
            bars.append(bar)
        return bars

    async def get_gold_etf_price(self, code: str = "518880") -> dict:
        """获取黄金ETF实时价格 — 复用现有market_data.py"""
        from backend.market_data import market_data_service
        return await market_data_service.get_etf_price(code)

    async def get_training_data(self, symbol: str = 'GC',
                                 lookback_days: int = 2520) -> pd.DataFrame:
        """获取ML预测训练数据 — 复用现有data_sync.py"""
        from backend.data_sync import get_gold_training_data
        return get_gold_training_data(symbol, lookback_days)
