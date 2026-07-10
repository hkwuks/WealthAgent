"""数据质量检查测试"""

import sys; sys.path.insert(0, 'backend/..')
import pytest
from backend.fund_quant.data.quality import DataQualityChecker
from backend.fund_quant.core.enums import DataQuality


class TestQualityChecks:
    """数据质量检查单元测试"""

    def setup_method(self):
        self.checker = DataQualityChecker()

    def test_no_data_returns_critical(self):
        issues = self.checker.check_nav_quality("nonexistent")
        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"
        assert issues[0]["issue"] == "no_data"

    def test_missing_holdings_empty_db(self):
        """无持仓数据时告警"""
        issue = self.checker._check_missing_holdings("nonexistent")
        assert issue is not None
        assert "持仓" in issue["test"]

    def test_scale_drop_no_meta(self):
        """无元数据时返回None"""
        issue = self.checker._check_scale_drop("nonexistent")
        assert issue is None

    def test_scale_drop_tiny(self, monkeypatch):
        """小规模(<1000万)告警"""
        monkeypatch.setattr(
            "backend.fund_quant.data.storage.get_fund_meta",
            lambda c: {"fund_code": c, "scale": 5_000_000},
        )
        issue = self.checker._check_scale_drop("tiny")
        assert issue is not None
        assert issue["severity"] == "critical"
        assert "清盘" in issue["issue"]

    def test_scale_drop_normal(self, monkeypatch):
        """正常规模不放行"""
        monkeypatch.setattr(
            "backend.fund_quant.data.storage.get_fund_meta",
            lambda c: {"fund_code": c, "scale": 500_000_000},
        )
        issue = self.checker._check_scale_drop("normal")
        assert issue is None

    def test_quality_estimate_error(self):
        quality = self.checker.estimate_nav_quality("nonexistent")
        assert quality == DataQuality.ERROR

    def test_mad_outlier_detection(self):
        """MAD应能在连续数据中工作"""
        records = []
        for i in range(100):
            records.append({"date": f"2024-{(i//30)+1:02d}-{(i%30)+1:02d}", "nav": 1.0 + i * 0.001,
                           "fund_code": "test"})
        issues = self.checker._check_outliers_mad(records)
        assert isinstance(issues, list)

    def test_data_delay_recent(self):
        today = __import__('datetime').date.today()
        records = [{"date": today.isoformat(), "nav": 1.0, "fund_code": "test"}]
        issue = self.checker._check_data_delay(records)
        assert issue is None

    def test_data_delay_stale(self):
        old_date = "2020-01-01"
        records = [{"date": old_date, "nav": 1.0, "fund_code": "test"}]
        issue = self.checker._check_data_delay(records)
        assert issue is not None
        assert "延迟" in issue["issue"]
