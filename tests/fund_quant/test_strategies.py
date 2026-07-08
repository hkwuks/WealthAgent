"""策略引擎测试：注册表 + 9个策略 + 信号融合"""

import sys; sys.path.insert(0, 'backend/..')
import pytest
import numpy as np
from backend.fund_quant.strategy.base import FundStrategyBase, StrategyRegistry
from backend.fund_quant.strategy.fusion import SignalFusion
from backend.fund_quant.core.enums import SignalType, Direction
from backend.fund_quant.core.models import FundSignal, FusionSignal


class TestStrategyRegistry:
    def setup_method(self):
        self.registry = StrategyRegistry()

    def test_all_9_strategies_registered(self):
        strategies = self.registry.list_strategies()
        names = {s["name"] for s in strategies}
        expected = {
            "valuation_deviation", "momentum", "interest_rate",
            "fx_momentum", "smart_dca", "multi_factor",
            "rating_enhanced", "risk_parity", "black_litterman",
        }
        assert names == expected, f"缺失: {expected - names}, 多余: {names - expected}"

    def test_strategy_types(self):
        strategies = self.registry.list_strategies()
        by_type = {}
        for s in strategies:
            by_type.setdefault(s["type"], []).append(s["name"])
        assert len(by_type.get("timing", [])) == 5, "择时策略应为5个"
        assert len(by_type.get("selection", [])) == 2, "选基策略应为2个"
        assert len(by_type.get("allocation", [])) == 2, "配置策略应为2个"

    def test_get_strategy_returns_instance(self):
        s = self.registry.get_strategy("momentum")
        assert s is not None
        assert s.strategy_name == "momentum"
        assert s.strategy_type == "timing"

    def test_get_nonexistent_returns_none(self):
        assert self.registry.get_strategy("nonexistent") is None

    def test_strategy_params_available(self):
        strategies = self.registry.list_strategies()
        for s in strategies:
            assert "default_params" in s, f"{s['name']} 缺少 default_params"
            assert isinstance(s["default_params"], dict)

    def test_each_strategy_has_description(self):
        strategies = self.registry.list_strategies()
        for s in strategies:
            assert s["description"], f"{s['name']} 缺少 description"

    def test_strategy_base_abc(self):
        """验证抽象类不可直接实例化"""
        with pytest.raises(TypeError):
            FundStrategyBase()  # abstractmethod on_evaluate


class TestStrategies:
    """验证每个策略的 on_evaluate 能正常返回信号 (无需实盘数据)"""

    @pytest.fixture
    def nav_data(self):
        """模拟180天净值序列"""
        np.random.seed(42)
        base = 1.0
        values = [base]
        for _ in range(180):
            base *= 1 + np.random.normal(0.0005, 0.008)
            values.append(base)
        return values

    @pytest.fixture
    def setup_strategy(self, nav_data):
        def _setup(name):
            registry = StrategyRegistry()
            s = registry.get_strategy(name)
            s._state.update({
                "fund_code": "000001",
                "nav_values": nav_data,
                "nav_dates": [f"2024-{i//30+1:02d}-{(i%30)+1:02d}" for i in range(len(nav_data))],
            })
            return s
        return _setup

    def test_valuation_deviation(self, setup_strategy):
        s = setup_strategy("valuation_deviation")
        signals = s.on_evaluate(None, None)
        assert len(signals) >= 1
        sig = signals[0]
        assert sig.signal_type == SignalType.TIMING

    def test_momentum(self, setup_strategy):
        s = setup_strategy("momentum")
        signals = s.on_evaluate(None, None)
        assert len(signals) >= 1
        assert signals[0].strategy_name == "momentum"

    def test_interest_rate(self, setup_strategy):
        s = setup_strategy("interest_rate")
        signals = s.on_evaluate(None, None)
        assert len(signals) >= 1

    def test_fx_momentum(self, setup_strategy):
        s = setup_strategy("fx_momentum")
        signals = s.on_evaluate(None, None)
        assert len(signals) >= 1
        # 无汇率数据时应返回 hold
        assert signals[0].direction == Direction.HOLD

    def test_fx_momentum_with_fx_data(self, setup_strategy):
        s = setup_strategy("fx_momentum")
        # 注入汇率数据
        fx_data = {f"USDCNY": [7.0 + i * 0.001 for i in range(30)]}
        s._state["fx_rates_history"] = fx_data
        signals = s.on_evaluate(None, None)
        assert len(signals) >= 1

    def test_smart_dca(self, setup_strategy):
        """智能定投需要特定z-score触发信号, 使用下行趋势数据"""
        s = setup_strategy("smart_dca")
        # 构建下行趋势数据使z-score明显为负(低估)
        np.random.seed(1)
        vals = [1.0]
        for _ in range(180):
            vals.append(vals[-1] * (1 - abs(np.random.normal(0.001, 0.005))))
        s._state["nav_values"] = vals
        signals = s.on_evaluate(None, None)
        assert len(signals) >= 1

    def test_multi_factor(self):
        registry = StrategyRegistry()
        s = registry.get_strategy("multi_factor")
        result = s.screen(fund_type="stock", top_n=5)
        assert "rankings" in result
        assert "total_candidates" in result

    def test_risk_parity(self):
        registry = StrategyRegistry()
        s = registry.get_strategy("risk_parity")
        result = s.optimize(fund_codes=["000001", "110011"])
        assert "weights" in result
        assert "status" in result

    def test_black_litterman(self, setup_strategy):
        s = setup_strategy("black_litterman")
        signals = s.on_evaluate(None, None)
        assert isinstance(signals, list)  # V1降级, 仅返回空列表

    def test_rating_enhanced(self, setup_strategy):
        s = setup_strategy("rating_enhanced")
        signals = s.on_evaluate(None, None)
        assert isinstance(signals, list)

    def test_long_history_strategies_return_signals(self, setup_strategy):
        """验证有足够数据时策略返回非空信号"""
        for name in ["valuation_deviation", "momentum"]:
            s = setup_strategy(name)
            signals = s.on_evaluate(None, None)
            assert len(signals) >= 1, f"{name} 未能生成信号"


class TestStrategyState:
    def test_save_load_state(self):
        registry = StrategyRegistry()
        s = registry.get_strategy("momentum")
        s._state = {"test_key": "test_value"}
        state = s.save_state()
        assert state["test_key"] == "test_value"

        s2 = registry.get_strategy("momentum")
        s2.load_state({"new_key": 42})
        assert s2._state["new_key"] == 42


class TestSignalFusion:
    def setup_method(self):
        self.fusion = SignalFusion()

    def test_no_signals(self):
        assert self.fusion.fuse([]) is None

    def test_single_buy_signal(self):
        s = FundSignal(signal_id="s1", fund_code="000001", fund_name="Test",
                       signal_type=SignalType.TIMING, direction=Direction.BUY,
                       confidence=0.8, reason="测试")
        result = self.fusion.fuse([s])
        assert result is not None
        assert result.direction == Direction.BUY
        assert result.confidence > 0

    def test_two_buy_signals(self):
        sigs = [
            FundSignal(signal_id="s1", fund_code="000001", fund_name="Test",
                       signal_type=SignalType.TIMING, direction=Direction.BUY,
                       confidence=0.8, reason="a"),
            FundSignal(signal_id="s2", fund_code="000001", fund_name="Test",
                       signal_type=SignalType.SELECTION, direction=Direction.BUY,
                       confidence=0.6, reason="b"),
        ]
        result = self.fusion.fuse(sigs)
        assert result.direction == Direction.BUY
        assert result.conflict is False

    def test_conflict_signals(self):
        sigs = [
            FundSignal(signal_id="s1", fund_code="000001", fund_name="Test",
                       signal_type=SignalType.TIMING, direction=Direction.BUY,
                       confidence=0.8, reason="a"),
            FundSignal(signal_id="s2", fund_code="000001", fund_name="Test",
                       signal_type=SignalType.ALLOCATION, direction=Direction.SELL,
                       confidence=0.7, reason="b"),
        ]
        result = self.fusion.fuse(sigs)
        assert result.conflict is True
        assert len(result.contributing_strategies) >= 2

    def test_all_hold(self):
        sigs = [
            FundSignal(signal_id="s1", fund_code="000001", fund_name="Test",
                       signal_type=SignalType.TIMING, direction=Direction.HOLD,
                       confidence=0.5, reason="a"),
        ]
        result = self.fusion.fuse(sigs)
        assert result is not None
        assert result.direction == Direction.HOLD

    def test_confidence_never_exceeds_1(self):
        sigs = [
            FundSignal(signal_id="s1", fund_code="000001", fund_name="Test",
                       signal_type=SignalType.TIMING, direction=Direction.BUY,
                       confidence=1.0, reason="a"),
            FundSignal(signal_id="s2", fund_code="000001", fund_name="Test",
                       signal_type=SignalType.SELECTION, direction=Direction.BUY,
                       confidence=1.0, reason="b"),
        ]
        result = self.fusion.fuse(sigs)
        assert result.confidence <= 1.0

    def test_timing_override(self):
        """择时置信度>0.9时覆盖配置信号"""
        # 构造: 择时=BUY(0.95), 选基=SELL(1.0), 配置=SELL(1.0)
        # 融合方向应为SELL, 但择时>0.9覆盖为BUY
        sigs = [
            FundSignal(signal_id="s1", fund_code="000001", fund_name="Test",
                       signal_type=SignalType.TIMING, direction=Direction.BUY,
                       confidence=0.95, reason="高置信度买"),
            FundSignal(signal_id="s2", fund_code="000001", fund_name="Test",
                       signal_type=SignalType.SELECTION, direction=Direction.SELL,
                       confidence=1.0, reason="选基卖"),
            FundSignal(signal_id="s3", fund_code="000001", fund_name="Test",
                       signal_type=SignalType.ALLOCATION, direction=Direction.SELL,
                       confidence=1.0, reason="配置卖"),
        ]
        result = self.fusion.fuse(sigs)
        assert result.direction == Direction.BUY  # 择时覆盖
        assert result.override_reason is not None
