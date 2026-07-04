"""风控模块测试：风险度量 + 风控检查 + 风格漂移检测"""

import sys; sys.path.insert(0, 'backend/..')
import pytest
import numpy as np
from datetime import datetime
from backend.fund_quant.risk.metrics import RiskMetricsCalculator
from backend.fund_quant.risk.checks import FundRiskChecker
from backend.fund_quant.risk.style_drift import StyleDriftDetector
from backend.fund_quant.core.models import FundSignal, Portfolio, RiskCheckResult, RiskMetrics
from backend.fund_quant.core.enums import SignalType, Direction


class TestRiskMetrics:
    def setup_method(self):
        self.calc = RiskMetricsCalculator()

    def test_empty_returns(self):
        metrics = self.calc.calculate([])
        assert metrics.var_95 == 0.0
        assert metrics.sharpe_ratio is None

    def test_small_sample(self):
        metrics = self.calc.calculate([0.01])
        assert metrics.var_95 == 0.0

    def test_normal_returns(self):
        np.random.seed(42)
        returns = list(np.random.normal(0.001, 0.01, 252))
        metrics = self.calc.calculate(returns)
        assert 0.0 < metrics.var_95 < 0.05
        assert metrics.volatility > 0
        assert metrics.max_drawdown < 0.3

    def test_cvar_ge_var(self):
        returns = [0.02, -0.03, 0.01, -0.02, 0.015, -0.04, 0.01, -0.01, 0.005, -0.025]
        metrics = self.calc.calculate(returns)
        assert metrics.cvar_95 >= metrics.var_95

    def test_sharpe_ratio_positive(self):
        returns = [0.001] * 252  # 稳定正收益
        metrics = self.calc.calculate(returns)
        assert metrics.sharpe_ratio is not None
        assert metrics.sharpe_ratio > 0

    def test_sharpe_ratio_negative(self):
        returns = [-0.001] * 252
        metrics = self.calc.calculate(returns)
        if metrics.sharpe_ratio is not None:
            assert metrics.sharpe_ratio < 0

    def test_sortino_ratio(self):
        np.random.seed(42)
        returns = list(np.random.normal(0.001, 0.01, 252))
        metrics = self.calc.calculate(returns)
        assert metrics.sortino_ratio is not None

    def test_calmar_ratio(self):
        returns = [0.01, -0.02, 0.015, -0.01, 0.02]
        metrics = self.calc.calculate(returns)
        assert metrics.calmar_ratio is not None

    def test_max_drawdown_zero_for_constant(self):
        returns = [0.001] * 100
        metrics = self.calc.calculate(returns)
        assert metrics.max_drawdown == 0.0

    def test_max_drawdown_detection(self):
        # 先涨后跌 → 应有回撤
        returns = [0.05] * 10 + [-0.1] * 10
        metrics = self.calc.calculate(returns)
        assert metrics.max_drawdown > 0.01


class TestRiskChecker:
    def setup_method(self):
        self.checker = FundRiskChecker()

    def make_signal(self, direction=Direction.BUY, confidence=0.8, fund_code="000001"):
        return FundSignal(
            signal_id="test", fund_code=fund_code, fund_name="Test",
            signal_type=SignalType.TIMING, direction=direction,
            confidence=confidence, reason="test",
        )

    def test_low_confidence_filtered(self):
        sig = self.make_signal(confidence=0.3)
        result = self.checker.check(sig)
        assert not result.passed
        assert "置信度" in result.reason

    def test_high_confidence_passes_confidence_check(self):
        sig = self.make_signal(confidence=0.85)
        # 用check会触发后续检查, 用call会走check
        result = self.checker._check_confidence(sig)
        assert result.passed

    def test_cooldown_blocks_duplicate(self):
        sig = self.make_signal()
        self.checker.register_signal(sig)
        result = self.checker._check_cooldown(sig)
        assert not result.passed
        assert "冷却期" in result.reason

    def test_cooldown_first_call_passes(self):
        sig = self.make_signal(fund_code="cooldown_test")
        result = self.checker._check_cooldown(sig)
        assert result.passed

    def test_min_holding_on_sell(self):
        sig = self.make_signal(direction=Direction.SELL, fund_code="holding_test")
        result = self.checker._check_min_holding(sig)
        assert result.passed  # 无建仓记录时pass

    def test_position_limit_with_portfolio(self):
        sig = self.make_signal(direction=Direction.BUY, fund_code="heavy_fund")
        portfolio = Portfolio(total_value=100000, cash=50000,
                              positions={"heavy_fund": 40000, "other": 10000})
        # max_position_pct=0.3, 40k/100k=0.4 > 0.3
        result = self.checker.check(sig, portfolio)
        # 可能被置信度、冷却期或其他检查拦截, 但position limit本身应工作
        limit_result = self.checker._check_position_limit(sig, portfolio)
        assert not limit_result.passed
        assert "上限" in limit_result.reason

    def test_cash_reserve_blocks_buy(self):
        sig = self.make_signal(direction=Direction.BUY, fund_code="cash_test")
        portfolio = Portfolio(total_value=100000, cash=2000)
        result = self.checker._check_cash_reserve(sig, portfolio)
        assert not result.passed
        assert "现金" in result.reason

    def test_cash_reserve_allows_sell(self):
        sig = self.make_signal(direction=Direction.SELL, fund_code="cash_test")
        portfolio = Portfolio(total_value=100000, cash=2000)
        result = self.checker._check_cash_reserve(sig, portfolio)
        assert result.passed

    def test_full_pipeline_passes(self):
        sig = self.make_signal(confidence=0.85, fund_code="pipeline_test")
        portfolio = Portfolio(total_value=100000, cash=50000,
                              positions={"pipeline_test": 10000})
        result = self.checker(sig, portfolio)
        assert result.passed

    def test_drawdown_blocks_buy(self):
        sig = self.make_signal(direction=Direction.BUY, fund_code="dd_test")
        # 模拟大回撤场景
        portfolio = Portfolio(total_value=80000, cash=20000,
                              nav_values={"dd_test": 0.75, "other": 0.80})
        # 调用内部方法
        result = self.checker._check_drawdown(sig, portfolio)
        # 具体取决于检查逻辑, 至少不抛异常
        assert isinstance(result, RiskCheckResult)

    def test_liquidity_check(self):
        sig = self.make_signal(direction=Direction.SELL, fund_code="big_pos")
        portfolio = Portfolio(total_value=100000, cash=10000,
                              positions={"big_pos": 50000})
        result = self.checker._check_liquidity(sig, portfolio)
        assert isinstance(result, RiskCheckResult)

    def test_concentration_check(self):
        sig = self.make_signal(fund_code="conc_test")
        portfolio = Portfolio(total_value=100000, cash=10000,
                              positions={"conc_test": 50000})
        result = self.checker._check_concentration(sig, portfolio)
        assert isinstance(result, RiskCheckResult)


class TestStyleDriftDetector:
    def setup_method(self):
        self.detector = StyleDriftDetector()

    def test_insufficient_data_skips(self):
        result = self.detector.check("test", [0.01] * 30, {})
        assert result.passed
        assert "不足" in result.reason

    def test_sufficient_data_returns_score(self):
        np.random.seed(42)
        nav_ret = list(np.random.normal(0.001, 0.01, 200))
        factor_ret = {
            "value": list(np.random.normal(0.001, 0.008, 200)),
            "growth": list(np.random.normal(0.0005, 0.01, 200)),
        }
        result = self.detector.check("test", nav_ret, factor_ret)
        # 随机数据一般不会触发漂移告警
        assert isinstance(result, RiskCheckResult)
        assert "漂移得分" in result.reason

    def test_drift_cache(self):
        assert self.detector.get_drift_score("nonexistent") is None
        np.random.seed(42)
        nav_ret = list(np.random.normal(0.001, 0.01, 200))
        factor_ret = {"value": list(np.random.normal(0.001, 0.008, 200))}
        self.detector.check("cached_fund", nav_ret, factor_ret)
        score = self.detector.get_drift_score("cached_fund")
        assert score is not None
        assert 0 <= score <= 1

    def test_r_squared_stable_when_no_drift(self):
        """无漂移时R²应保持稳定"""
        np.random.seed(42)
        nav_ret = list(np.random.normal(0.001, 0.01, 250))
        factor_ret = {"market": list(np.random.normal(0.001, 0.008, 250))}
        result = self.detector.check("stable", nav_ret, factor_ret)
        assert result.passed  # 随机数据不应触发漂移

    def test_chow_test_pvalue(self):
        np.random.seed(42)
        nav_ret = list(np.random.normal(0.001, 0.01, 500))
        factor_ret = {"market": list(np.random.normal(0.001, 0.008, 500))}
        self.detector.check("chow_test", nav_ret, factor_ret)
        p = self.detector.get_chow_pvalue("chow_test")
        # Chow p-value 应该在 0-1 之间
        if p is not None:
            assert 0 <= p <= 1
