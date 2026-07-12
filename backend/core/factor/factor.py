"""因子抽象基类"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import FactorMeta


class Factor(ABC):
    """因子基类——所有因子的统一接口"""

    meta: FactorMeta  # 子类定义

    @abstractmethod
    def compute(self, symbols: list[str], as_of: date,
                lookback: int, data: Any) -> dict[str, float]:
        """截面因子值计算

        Args:
            symbols: 标的代码列表
            as_of: 计算基准日
            lookback: 回溯窗口（天）
            data: 数据源（DataFeed 或领域数据）

        Returns:
            {symbol: factor_value}，无效标的排除
        """

    def get_lookback(self, as_of: date) -> date:
        """需要的起始历史日期"""
        lb = self.meta.params.get("lookback", self.meta.min_history_days)
        return as_of - timedelta(days=int(lb) * 2)

    def validate(self) -> bool:
        """自检：参数合法性"""
        return bool(self.meta.name and self.meta.domain)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}[{self.meta.name}]>"


def demo():
    """抽象基类自检"""
    import sys
    sys.path.insert(0, 'backend/..')
    from backend.core.factor.models import FactorMeta

    class DummyFactor(Factor):
        meta = FactorMeta(
            name="dummy", display_name="哑变量", category="risk",
            domain="fund", description="测试", direction=1,
        )

        def compute(self, symbols, as_of, lookback, data):
            return {s: 1.0 for s in symbols}

    f = DummyFactor()
    assert f.meta.name == "dummy"
    assert f.validate()
    result = f.compute(["A", "B"], date(2026, 7, 1), 60, None)
    assert result == {"A": 1.0, "B": 1.0}
    assert f.get_lookback(date(2026, 7, 1)) <= date(2026, 7, 1)
    print("[factor] ✅ Factor 基类通过")


if __name__ == "__main__":
    demo()
