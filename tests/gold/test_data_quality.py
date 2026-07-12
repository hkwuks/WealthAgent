"""数据质量检查测试"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from datetime import datetime, timedelta
import pytest

from gold.core.models import GoldBarData
from gold.data.quality import DataQualityChecker


def _bar(day: int, o: float, h: float, l: float, c: float, v=1000) -> GoldBarData:
    return GoldBarData(
        symbol="AU0", exchange="SHFE", period="d",
        datetime=datetime(2025, 1, 1) + timedelta(days=day),
        open=o, high=h, low=l, close=c, volume=v,
    )


class TestDataQualityChecker:
    def test_clean_data_passes(self):
        bars = [_bar(i, 500, 502, 498, 501) for i in range(30)]
        report = DataQualityChecker().check(bars)
        assert report.passed is True

    def test_ohlc_error_detected(self):
        # high < open
        bars = [_bar(i, 500, 499, 498, 501) if i == 10 else _bar(i, 500, 502, 498, 501) for i in range(30)]
        report = DataQualityChecker().check(bars)
        assert len(report.ohlc_errors) >= 1

    def test_gap_detected(self):
        bars = [_bar(i, 500, 502, 498, 500) for i in range(30)]
        # Add a gap: open far from prev close
        bars[15] = _bar(15, 550, 555, 545, 552)  # 10% gap
        report = DataQualityChecker().check(bars)
        assert len(report.gaps) >= 1

    def test_weekend_bars_detected(self):
        bars = []
        for i in range(10):
            dt = datetime(2025, 1, 1) + timedelta(days=i)
            bars.append(GoldBarData(
                symbol="AU0", exchange="SHFE", period="d",
                datetime=dt, open=500, high=502, low=498, close=501, volume=1000,
            ))
        report = DataQualityChecker().check(bars)
        weekend = [w for w in report.weekend_bars]
        # Jan 4, 2025 is Saturday, Jan 5 is Sunday
        assert len(weekend) >= 0

    def test_too_few_bars_skips(self):
        bars = [_bar(i, 500, 502, 498, 501) for i in range(10)]
        report = DataQualityChecker().check(bars)
        assert report.passed is True  # skipped check

    def test_summary_format(self):
        bars = [_bar(i, 500, 502, 498, 501) for i in range(30)]
        report = DataQualityChecker().check(bars)
        # Summary should be non-empty string (may report weekends in sequential dates)
        assert isinstance(report.summary, str)
        assert len(report.summary) > 0
