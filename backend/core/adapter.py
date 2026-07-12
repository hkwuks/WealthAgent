"""领域适配器规范 — DomainAdapter(ABC)"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .data import DataFeed
    from .backtest import ExecutionEngine, CostModel
    from .risk import RiskCheck
    from .strategy import Strategy


class DomainAdapter(ABC):
    """领域适配器——资产类别的唯一入口点

    内核不直接感知领域，领域通过此接口适配。
    新增资产类型（股票/加密货币）只需写一个 DomainAdapter。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """领域名: "fund" / "gold" / "crypto" """
        ...

    @abstractmethod
    def create_data_feed(self, config: dict) -> DataFeed:
        ...

    @abstractmethod
    def create_executor(self, config: dict) -> ExecutionEngine:
        """创建执行引擎（T+1 / 交易所撮合 / 永续合约）"""
        ...

    @abstractmethod
    def create_cost_model(self, config: dict) -> CostModel:
        ...

    @abstractmethod
    def default_risk_checks(self) -> list[RiskCheck]:
        ...

    @abstractmethod
    def get_available_strategies(self) -> dict[str, type[Strategy]]:
        """返回该领域可用的策略类字典"""
        ...


def demo():
    """接口自检"""
    # 验证 DomainAdapter 是抽象类
    try:
        DomainAdapter()
        assert False, "should not instantiate ABC"
    except TypeError:
        pass

    # 验证子类必须实现所有方法
    class FakeAdapter(DomainAdapter):
        @property
        def name(self): return "test"
        def create_data_feed(self, config): pass
        def create_executor(self, config): pass
        def create_cost_model(self, config): pass
        def default_risk_checks(self): return []
        def get_available_strategies(self): return {}

    a = FakeAdapter()
    assert a.name == "test"
    print("[adapter] ✅ DomainAdapter 接口通过")


if __name__ == "__main__":
    demo()
