# tests/core/factor/test_registry.py
import sys; sys.path.insert(0, 'backend/..')
import pytest
from datetime import date
from backend.core.factor.registry import FactorRegistry
from backend.core.factor.factor import Factor
from backend.core.factor.models import FactorMeta
from backend.core.factor.exceptions import FactorNotFound


class DummyFactor(Factor):
    meta = FactorMeta(name="dummy", display_name="哑变量", category="risk",
                      domain="fund", description="测试", direction=1)
    def compute(self, symbols, as_of, lookback, data):
        return {}


class TestFactorRegistry:
    def setup_method(self):
        FactorRegistry.clear()

    def test_register_and_get(self):
        FactorRegistry.register(DummyFactor, DummyFactor.meta)
        assert FactorRegistry.get("dummy") is DummyFactor

    def test_get_meta(self):
        FactorRegistry.register(DummyFactor, DummyFactor.meta)
        meta = FactorRegistry.get_meta("dummy")
        assert meta.name == "dummy"

    def test_get_not_found(self):
        with pytest.raises(FactorNotFound):
            FactorRegistry.get("nonexistent")

    def test_register_twice_raises(self):
        FactorRegistry.register(DummyFactor, DummyFactor.meta)
        with pytest.raises(ValueError, match="已注册"):
            FactorRegistry.register(DummyFactor, DummyFactor.meta)

    def test_list_by_domain(self):
        FactorRegistry.register(DummyFactor, DummyFactor.meta)
        metas = FactorRegistry.list(domain="fund")
        assert len(metas) == 1
        metas = FactorRegistry.list(domain="gold")
        assert len(metas) == 0

    def test_list_by_category(self):
        FactorRegistry.register(DummyFactor, DummyFactor.meta)
        metas = FactorRegistry.list(category="risk")
        assert len(metas) == 1
        metas = FactorRegistry.list(category="momentum")
        assert len(metas) == 0

    def test_summary_dataframe(self):
        FactorRegistry.register(DummyFactor, DummyFactor.meta)
        df = FactorRegistry.summary()
        assert len(df) == 1
        assert "dummy" in df["name"].values

    def test_count(self):
        assert FactorRegistry.count() == 0
        FactorRegistry.register(DummyFactor, DummyFactor.meta)
        assert FactorRegistry.count() == 1

    def test_batch_register(self):
        class F2(Factor):
            meta = FactorMeta(name="f2", display_name="F2", category="q",
                              domain="gold", description="", direction=1)
            def compute(self, symbols, as_of, lookback, data): return {}
        FactorRegistry.register_factors([(DummyFactor, DummyFactor.meta),
                                          (F2, F2.meta)])
        assert FactorRegistry.count() == 2
