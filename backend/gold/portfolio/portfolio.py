"""
Portfolio 组合层 — 多品种资产组合管理

当前只有单一品种 AU0，但框架预留多合约扩展。

分配策略:
- 等权: EqualWeight (所有品种均分资金)
- 波动率平价: VolatilityParity (风险预算 = 目标波动率 × 资金)
- 风险预算: RiskBudget (基于历史波动率)

用法:
    portfolio = GoldPortfolio(allocation="vol_parity")
    portfolio.add_strategy("trend_following", TrendFollowingStrategy())
    result = portfolio.run(bars_dict={"AU0": bars}, capital=1_000_000)
    print(portfolio.report())
"""

from typing import Optional
from dataclasses import dataclass, field
from loguru import logger

from backend.gold.strategy.base import StrategyBase
from backend.gold.backtest.engine import Backtester


@dataclass
class AllocationResult:
    """分配结果"""
    symbol: str
    weight: float
    capital: float
    strategy: str


class BaseAllocation:
    """分配策略基类"""
    def allocate(self, symbols: list[str], capital: float,
                 atr_values: dict[str, float] = None) -> list[AllocationResult]:
        raise NotImplementedError


class EqualWeightAllocation(BaseAllocation):
    """等权分配"""
    def allocate(self, symbols: list[str], capital: float,
                 atr_values: dict[str, float] = None) -> list[AllocationResult]:
        weight = 1.0 / len(symbols) if symbols else 0
        return [
            AllocationResult(symbol=s, weight=weight, capital=capital * weight, strategy="equal_weight")
            for s in symbols
        ]


class VolatilityParityAllocation(BaseAllocation):
    """波动率平价分配 — 波动率越低权重越高"""
    def __init__(self, target_vol: float = 0.10):
        self.target_vol = target_vol

    def allocate(self, symbols: list[str], capital: float,
                 atr_values: dict[str, float] = None) -> list[AllocationResult]:
        if not atr_values:
            return EqualWeightAllocation().allocate(symbols, capital)

        inv_vol = {s: 1.0 / max(v, 0.001) for s, v in atr_values.items() if s in symbols}
        total_inv = sum(inv_vol.values())
        if total_inv == 0:
            return EqualWeightAllocation().allocate(symbols, capital)

        results = []
        for s in symbols:
            w = inv_vol.get(s, 0) / total_inv
            results.append(AllocationResult(
                symbol=s, weight=w, capital=capital * w,
                strategy="vol_parity"
            ))
        return results


class GoldPortfolio:
    """组合管理器 — 多品种多策略组合"""

    def __init__(self, allocation: str = "equal_weight",
                 target_vol: float = 0.10):
        if allocation == "equal_weight":
            self.allocator = EqualWeightAllocation()
        elif allocation == "vol_parity":
            self.allocator = VolatilityParityAllocation(target_vol)
        else:
            raise ValueError(f"Unknown allocation: {allocation}")

        self._strategies: dict[str, StrategyBase] = {}
        self._results: dict[str, dict] = {}

    def add_strategy(self, symbol: str, strategy: StrategyBase):
        """注册品种和对应的策略"""
        self._strategies[symbol] = strategy

    def run(self, bars_dict: dict[str, list],
            capital: float = 1_000_000,
            params: dict = None) -> dict:
        """运行组合回测

        Args:
            bars_dict: {symbol: [GoldBarData, ...]}
            capital: 总资金
            params: {symbol: {param: value}}

        Returns:
            {symbol: backtest_result}
        """
        symbols = list(bars_dict.keys())
        allocations = self.allocator.allocate(symbols, capital)

        for alloc in allocations:
            bars = bars_dict.get(alloc.symbol, [])
            if not bars:
                logger.warning(f"{alloc.symbol} 无 K 线数据，跳过")
                continue

            strategy = self._strategies.get(alloc.symbol)
            if not strategy:
                logger.warning(f"{alloc.symbol} 无策略注册，跳过")
                continue

            bt = Backtester()
            symbol_params = params.get(alloc.symbol) if params else None
            result = bt.run(strategy, bars, capital=alloc.capital, params=symbol_params)
            self._results[alloc.symbol] = result

            logger.info(f"组合 {alloc.symbol}: 分配资金 {alloc.capital:.0f}, "
                        f"信号 {result['signal_count']}, "
                        f"收益率 {result['report']['performance']['total_return']}%")

        return dict(self._results)

    def report(self) -> dict:
        """组合层面汇总报告"""
        if not self._results:
            return {"status": "no_results"}

        total_capital = sum(
            r["report"]["meta"]["capital"] for r in self._results.values()
        )
        total_pnl = sum(
            r["report"]["cost"]["net_pnl"] for r in self._results.values()
        )

        return {
            "allocation": self.allocator.__class__.__name__,
            "symbols": list(self._results.keys()),
            "total_capital": total_capital,
            "total_pnl": round(total_pnl, 2),
            "total_return_pct": round(total_pnl / total_capital * 100, 2) if total_capital else 0,
            "details": {
                s: {
                    "total_return": r["report"]["performance"]["total_return"],
                    "sharpe": r["report"]["performance"]["sharpe_ratio"],
                    "max_drawdown": r["report"]["risk"]["max_drawdown"],
                    "trade_count": r["report"]["trades"]["total_count"],
                }
                for s, r in self._results.items()
            },
        }
