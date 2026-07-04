"""
Triple-Barrier Labeler 测试
"""

import pytest
import numpy as np
from datetime import datetime, timedelta

from backend.gold.data.labeling import TripleBarrierLabeler
from backend.gold.core.models import GoldBarData


def _make_bars(n: int, close_start: float = 400.0,
               volatility: float = 2.0, seed: int = 42) -> list[GoldBarData]:
    """生成模拟K线"""
    rng = np.random.RandomState(seed)
    bars = []
    dt = datetime(2024, 1, 1)
    prev_close = close_start
    for i in range(n):
        change = rng.normal(0, volatility)
        close = prev_close + change
        high = max(close, prev_close) + abs(rng.normal(0, volatility * 0.5))
        low = min(close, prev_close) - abs(rng.normal(0, volatility * 0.5))
        bars.append(GoldBarData(
            symbol="AU0", datetime=dt + timedelta(days=i),
            open=prev_close, high=high, low=low, close=close,
            volume=1000,
        ))
        prev_close = close
    return bars


class TestTripleBarrierLabeler:
    def test_init_defaults(self):
        labeler = TripleBarrierLabeler()
        assert labeler.atr_window == 20
        assert labeler.tp_multiplier == 1.5
        assert labeler.sl_multiplier == 1.0
        assert labeler.max_holding_days == 5

    def test_label_bars_returns_correct_shape(self):
        bars = _make_bars(100)
        labeler = TripleBarrierLabeler()
        labels = labeler.label_bars(bars)
        assert len(labels) == len(bars)
        assert all("bar_index" in l for l in labels)
        assert all("label" in l for l in labels)

    def test_label_values_are_valid(self):
        bars = _make_bars(100)
        labeler = TripleBarrierLabeler()
        labels = labeler.label_bars(bars)
        for l in labels:
            assert l["label"] in (1, -1, 0)

    def test_long_data_has_fewer_neutral(self):
        bars = _make_bars(300)
        labeler = TripleBarrierLabeler()
        labels = labeler.label_bars(bars)
        neutral = sum(1 for l in labels if l["label"] == 0)
        # 尾部数据不应为0
        assert neutral < len(bars) * 0.5

    def test_distribution_stats(self):
        bars = _make_bars(100)
        labeler = TripleBarrierLabeler()
        labels = labeler.label_bars(bars)
        dist = labeler.label_distribution(labels)
        assert dist["total"] == 100
        assert "bull" in dist
        assert "bear" in dist
        assert "by_barrier" in dist

    def test_label_dataframe_consistency(self):
        import pandas as pd
        bars = _make_bars(100)
        labeler = TripleBarrierLabeler()

        # bars接口
        bar_labels = labeler.label_bars(bars)

        # DataFrame接口
        df = pd.DataFrame([{
            "open": b.open, "high": b.high, "low": b.low,
            "close": b.close, "volume": b.volume,
        } for b in bars])
        df_labeled = labeler.label_dataframe(df)

        assert "tb_label" in df_labeled.columns
        assert "tb_barrier_type" in df_labeled.columns
        assert len(df_labeled) == len(bar_labels)

    def test_insufficient_data_returns_empty(self):
        bars = _make_bars(5)
        labeler = TripleBarrierLabeler()
        labels = labeler.label_bars(bars)
        # 数据不足 ATR 窗口 (20) + 2 时返回空
        assert len(labels) == 0

    def test_barrier_types_are_plausible(self):
        """在波动较大的数据中，应出现 tp/sl/time 类型"""
        bars = _make_bars(200, volatility=3.0, seed=99)
        labeler = TripleBarrierLabeler(tp_multiplier=2.0, sl_multiplier=2.0)
        labels = labeler.label_bars(bars)
        types = set(l["barrier_type"] for l in labels if l["label"] != 0)
        assert "time" in types or "tp" in types or "sl" in types
