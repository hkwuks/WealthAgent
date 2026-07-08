"""回测引擎测试：事件驱动 + T+1确认 + 费率 + 报告 + Walk-forward"""

import sys; sys.path.insert(0, 'backend/..')
import pytest
from datetime import date, datetime
from backend.fund_quant.backtest.engine import FundBacktester, SimPosition, PendingOrder
from backend.fund_quant.backtest.cost_model import FundCostModel
from backend.fund_quant.backtest.dividend import DividendHandler
from backend.fund_quant.backtest.report import BacktestReport
from backend.fund_quant.backtest.validation import WalkForwardValidator
from backend.fund_quant.core.models import BacktestConfig, BacktestResult, CostModelConfig


class TestBacktestEngine:
    def test_empty_nav_returns_failed(self):
        cfg = BacktestConfig(strategy_name="test", fund_codes=["000001"],
                             start_date="2020-01-01", end_date="2020-12-31")
        engine = FundBacktester()
        result = engine.run(cfg)
        assert result.status == "failed"

    def test_run_with_mock_nav(self):
        cfg = BacktestConfig(strategy_name="test", fund_codes=["000001"],
                             start_date="2020-01-01", end_date="2020-12-31")
        navs = {
            "000001": [
                {"date": "2020-01-02", "nav": 1.0},
                {"date": "2020-01-03", "nav": 1.01},
                {"date": "2020-01-06", "nav": 1.02},
                {"date": "2020-01-07", "nav": 1.015},
                {"date": "2020-01-08", "nav": 1.03},
            ]
        }
        engine = FundBacktester()
        result = engine.run(cfg, nav_data=navs)
        assert result.status == "completed"
        assert result.equity_curve is not None
        assert len(result.equity_curve) >= 1

    def test_submit_and_confirm_order(self):
        """验证T+1申赎确认逻辑"""
        cfg = BacktestConfig(strategy_name="test", fund_codes=["000001"],
                             start_date="2020-01-01", end_date="2020-01-10",
                             initial_capital=100000)
        navs = {
            "000001": [
                {"date": "2020-01-02", "nav": 1.0},
                {"date": "2020-01-03", "nav": 1.02},
            ]
        }
        engine = FundBacktester()
        engine._config = cfg
        engine._cash = 100000
        engine.submit_order("000001", "buy", 1000, date(2020, 1, 2))
        assert len(engine._pending_orders) == 1

    def test_multi_fund_backtest(self):
        cfg = BacktestConfig(strategy_name="multi", fund_codes=["000001", "000002"],
                             start_date="2020-01-01", end_date="2020-01-10")
        navs = {
            "000001": [{"date": "2020-01-02", "nav": 1.0}, {"date": "2020-01-03", "nav": 1.02}],
            "000002": [{"date": "2020-01-02", "nav": 2.0}, {"date": "2020-01-03", "nav": 2.01}],
        }
        engine = FundBacktester()
        result = engine.run(cfg, nav_data=navs)
        assert result.status == "completed"

    def test_equity_curve_recorded(self):
        cfg = BacktestConfig(strategy_name="test", fund_codes=["000001"],
                             start_date="2020-01-01", end_date="2020-01-10")
        navs = {
            "000001": [
                {"date": "2020-01-02", "nav": 1.0},
                {"date": "2020-01-03", "nav": 1.02},
                {"date": "2020-01-06", "nav": 1.03},
            ]
        }
        engine = FundBacktester()
        result = engine.run(cfg, nav_data=navs)
        assert len(result.equity_curve) > 0
        assert "date" in result.equity_curve[0]
        assert "total_value" in result.equity_curve[0]

    def test_period_returns(self):
        cfg = BacktestConfig(strategy_name="test", fund_codes=["000001"],
                             start_date="2020-01-01", end_date="2021-12-31")
        navs = {
            "000001": [
                {"date": "2020-06-01", "nav": 1.0},
                {"date": "2021-06-01", "nav": 1.10},
                {"date": "2021-12-01", "nav": 1.15},
            ]
        }
        engine = FundBacktester()
        result = engine.run(cfg, nav_data=navs)
        # 至少应该有 equity_curve
        assert len(result.equity_curve) >= 1

    def test_trade_log(self):
        engine = FundBacktester()
        engine._config = BacktestConfig(strategy_name="test", fund_codes=["000001"],
                                        start_date="2020-01-01", end_date="2020-12-31")
        engine._cash = 100000
        engine.submit_order("000001", "buy", 1000, date(2020, 1, 2))
        assert len(engine._trade_log) == 0  # 订单还未确认


class TestSimPosition:
    def test_position_value(self):
        pos = SimPosition("000001", 1000, date(2024, 1, 1), 1.0)
        assert pos.current_value(1.05) == 1050.0

    def test_holding_days(self):
        pos = SimPosition("000001", 1000, date(2024, 1, 1), 1.0)
        assert pos.holding_days(date(2024, 1, 10)) == 9

    def test_pnl_positive(self):
        pos = SimPosition("000001", 1000, date(2024, 1, 1), 1.0)
        assert pos.pnl(1.1) == pytest.approx(100.0)

    def test_pnl_negative(self):
        pos = SimPosition("000001", 1000, date(2024, 1, 1), 1.0)
        assert pos.pnl(0.9) == pytest.approx(-100.0)

    def test_cost(self):
        pos = SimPosition("000001", 500, date(2024, 1, 1), 2.0)
        assert pos.cost == 1000.0


class TestPendingOrder:
    def test_default_confirmation(self):
        order = PendingOrder("000001", "buy", 1000, date(2024, 1, 1))
        assert order.confirmation_date is None

    def test_ready_after_submit(self):
        order = PendingOrder("000001", "buy", 1000, date(2024, 1, 1))
        assert order.is_ready(date(2024, 1, 2))  # T+1

    def test_not_ready_same_day(self):
        order = PendingOrder("000001", "buy", 1000, date(2024, 1, 1))
        assert not order.is_ready(date(2024, 1, 1))

    def test_confirm(self):
        order = PendingOrder("000001", "buy", 1000, date(2024, 1, 1))
        order.confirm(date(2024, 1, 2))
        assert order.confirmation_date == date(2024, 1, 2)


class TestCostModel:
    def setup_method(self):
        self.model = FundCostModel()

    def test_subscription_fee_stock(self):
        fee = self.model.get_subscription_fee("stock", 100000)
        assert fee == 1500.0  # 1.5%

    def test_subscription_fee_money(self):
        fee = self.model.get_subscription_fee("money", 100000)
        assert fee == 0.0

    def test_redemption_fee_under_7_days(self):
        fee = self.model.get_redemption_fee("stock", 5)
        assert fee == 0.015  # 1.5%

    def test_redemption_fee_over_730_days(self):
        fee = self.model.get_redemption_fee("stock", 800)
        assert fee == 0.0

    def test_management_fee_stock(self):
        fee = self.model.get_management_fee("stock")
        assert fee == 0.015

    def test_estimate_trade_cost(self):
        cost = self.model.estimate_trade_cost("stock", 100000, 20)
        assert "subscription_fee" in cost
        assert "redemption_fee" in cost
        assert "total_cost" in cost
        assert cost["subscription_fee"] == 1500.0
        assert cost["total_cost"] == 2250.0

    def test_c_class_selection(self):
        assert FundCostModel.should_use_c_class(100) is True   # <1.5年
        assert FundCostModel.should_use_c_class(600) is False  # >1.5年

    def test_custom_config(self):
        config = CostModelConfig(fund_type="bond")
        model = FundCostModel(config)
        assert model.config.fund_type == "bond"


class TestDividendHandler:
    def setup_method(self):
        self.handler = DividendHandler()

    def test_dividend_tax_under_1y(self):
        result = self.handler.process_dividend(1.5, 0.1, 1000, 180)
        # 持有<1年, 10%红利税
        assert result["tax_rate"] == 0.10
        assert result["gross_amount"] == 100.0
        assert result["net_amount"] == 90.0

    def test_dividend_no_tax_over_1y(self):
        result = self.handler.process_dividend(1.5, 0.1, 1000, 400)
        assert result["tax_rate"] == 0.0
        assert result["net_amount"] == 100.0

    def test_dividend_keys(self):
        result = self.handler.process_dividend(1.5, 0.05, 500, 200)
        expected_keys = {"dividend_per_share", "shares", "gross_amount",
                         "tax", "tax_rate", "net_amount", "reinvested_shares"}
        assert set(result.keys()) == expected_keys


class TestBacktestReport:
    def test_generate_empty(self):
        config = BacktestConfig(strategy_name="test", fund_codes=["000001"],
                                start_date="2020-01-01", end_date="2020-12-31")
        result = BacktestResult(backtest_id="test", config=config)
        report = BacktestReport.generate(result)
        assert "summary" in report
        assert "performance" in report
        assert report["summary"]["strategy"] == "test"

    def test_generate_with_data(self):
        config = BacktestConfig(strategy_name="momentum", fund_codes=["000001", "000002"],
                                start_date="2020-01-01", end_date="2020-12-31")
        result = BacktestResult(
            backtest_id="r1", config=config,
            total_return=0.15, sharpe_ratio=1.2, max_drawdown=0.08,
            total_trades=12, win_rate=0.58,
            equity_curve=[{"date": "2020-06-01", "total_value": 100000},
                         {"date": "2020-12-31", "total_value": 115000}],
            trade_log=[{"date": "2020-06-15", "action": "buy"}],
            status="completed",
        )
        report = BacktestReport.generate(result)
        assert report["summary"]["strategy"] == "momentum"
        assert report["performance"]["total_return"] == "15.00%"
        assert report["performance"]["sharpe_ratio"] == 1.2


class TestWalkForward:
    def test_params_defaults(self):
        v = WalkForwardValidator()
        assert v.DEFAULT_PARAMS["train_window_days"] == 1260
        assert v.DEFAULT_PARAMS["test_window_days"] == 126

    def test_validate_short_period(self):
        def mock_backtest(cfg):  # pylint: disable=unused-argument
            return {"total_return": 0.1, "sharpe_ratio": 0.5, "max_drawdown": 0.05, "total_trades": 30}

        v = WalkForwardValidator()
        result = v.validate(mock_backtest, ["000001"], "2023-01-01", "2023-06-01")
        assert result["status"] == "error"  # 数据区间太短

    def test_validate_returns_summary(self):
        def mock_backtest(cfg):  # pylint: disable=unused-argument
            return {"total_return": 0.08, "sharpe_ratio": 0.8, "max_drawdown": 0.06, "total_trades": 25}

        v = WalkForwardValidator()
        result = v.validate(mock_backtest, ["000001"],
                           "2020-01-01", "2024-12-31",
                           {"train_window_days": 30, "test_window_days": 10, "step_size_days": 10})
        assert result["method"] == "walk_forward"
        assert "summary" in result
        assert result["summary"]["total_windows"] > 0
