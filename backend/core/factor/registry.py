"""因子注册中心"""
from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pandas as pd

try:
    from .exceptions import FactorNotFound
except ImportError:
    # 支持 __main__ 直跑
    sys.path.insert(0, 'backend/..')
    from backend.core.factor.exceptions import FactorNotFound

if TYPE_CHECKING:
    from .factor import Factor
    from .models import FactorMeta


class FactorRegistry:
    """全局因子注册中心——单例"""

    _registry: dict[str, type[Factor]] = {}
    _metas: dict[str, FactorMeta] = {}

    @classmethod
    def register(cls, factor_cls: type[Factor],
                 meta: FactorMeta) -> type[Factor]:
        """注册一个因子类，返回原类（可用作装饰器）"""
        name = meta.name
        if name in cls._registry:
            raise ValueError(f"因子已注册: {name}")
        cls._registry[name] = factor_cls
        cls._metas[name] = meta
        return factor_cls

    @classmethod
    def register_factors(cls,
                         factors: list[tuple[type[Factor], FactorMeta]]):
        """批量注册"""
        for factor_cls, meta in factors:
            cls.register(factor_cls, meta)

    @classmethod
    def get(cls, name: str) -> type[Factor]:
        """按名称查询因子类"""
        if name not in cls._registry:
            raise FactorNotFound(f"因子未注册: {name}")
        return cls._registry[name]

    @classmethod
    def get_meta(cls, name: str) -> FactorMeta:
        """按名称查询因子元数据"""
        if name not in cls._metas:
            raise FactorNotFound(f"因子未注册: {name}")
        return cls._metas[name]

    @classmethod
    def list(cls, domain: str | None = None,
             category: str | None = None) -> list[FactorMeta]:
        """按条件查询因子元数据列表"""
        results = list(cls._metas.values())
        if domain:
            results = [m for m in results if m.domain == domain]
        if category:
            results = [m for m in results if m.category == category]
        return results

    @classmethod
    def summary(cls) -> pd.DataFrame:
        """因子全景表"""
        rows = []
        for name, meta in cls._metas.items():
            rows.append({
                "name": name,
                "display_name": meta.display_name,
                "category": meta.category,
                "domain": meta.domain,
                "direction": meta.direction,
            })
        return pd.DataFrame(rows).sort_values(["domain", "name"])

    @classmethod
    def count(cls) -> int:
        """已注册因子总数"""
        return len(cls._registry)

    @classmethod
    def clear(cls):
        """清空注册（仅测试用）"""
        cls._registry.clear()
        cls._metas.clear()


def demo():
    """注册中心自检"""
    import sys
    sys.path.insert(0, 'backend/..')
    from datetime import date
    from backend.core.factor.factor import Factor
    from backend.core.factor.models import FactorMeta

    class TestFactor(Factor):
        meta = FactorMeta(
            name="demo", display_name="示例", category="risk",
            domain="test", description="测试因子", direction=1,
        )
        def compute(self, symbols, as_of, lookback, data):
            return {}

    FactorRegistry.register(TestFactor, TestFactor.meta)
    assert FactorRegistry.count() >= 1
    cls = FactorRegistry.get("demo")
    assert cls is TestFactor
    meta = FactorRegistry.get_meta("demo")
    assert meta.domain == "test"

    metas = FactorRegistry.list(domain="test")
    assert len(metas) == 1

    df = FactorRegistry.summary()
    assert "demo" in df["name"].values

    try:
        FactorRegistry.register(TestFactor, TestFactor.meta)
        assert False, "应抛出 ValueError"
    except ValueError:
        pass

    FactorRegistry.clear()
    assert FactorRegistry.count() == 0
    print("[registry] ✅ FactorRegistry 通过")


if __name__ == "__main__":
    demo()
