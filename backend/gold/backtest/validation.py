"""
In/Out样本验证 + 场景验证 + Walk-Forward + CPCV

1. SampleSplitter:  70/30分割，对比In/Out样本指标
2. ScenarioValidator: 3个验证场景（2020暴跌/2022加息/2024新高）
3. WalkForwardValidator: 滚动窗口（Purging + Embargo）
4. CPCVValidator: Combinatorial Purged Cross-Validation + PBO
"""

from backend.gold.strategy.base import StrategyBase, StrategyRegistry
from backend.gold.backtest.engine import Backtester
from backend.gold.backtest.walk_forward import WalkForwardValidator, CPCVValidator
from backend.gold.core.models import GoldBarData
from backend.gold.core.config import GoldSettings
from loguru import logger


class SampleSplitter:
    """In-sample/Out-sample分割验证"""

    def split(self, bars: list[GoldBarData],
              in_sample_ratio: float = 0.7) -> tuple[list, list]:
        split_idx = int(len(bars) * in_sample_ratio)
        return bars[:split_idx], bars[split_idx:]

    def validate(self, strategy: StrategyBase, bars: list[GoldBarData],
                 capital: float = 1_000_000,
                 in_sample_ratio: float = 0.7) -> dict:
        in_bars, out_bars = self.split(bars, in_sample_ratio)
        if not in_bars or not out_bars:
            return {"error": "Insufficient data for split"}

        backtester = Backtester()
        in_result = backtester.run(strategy, in_bars, capital=capital)
        out_result = backtester.run(strategy, out_bars, capital=capital)

        in_sharpe = in_result["report"]["performance"]["sharpe_ratio"]
        out_sharpe = out_result["report"]["performance"]["sharpe_ratio"]
        degradation = (in_sharpe - out_sharpe) / abs(in_sharpe) if in_sharpe != 0 else float("inf")

        if degradation > 0.5:
            risk = "高"
        elif degradation > 0.3:
            risk = "中"
        else:
            risk = "低"

        return {
            "in_sample": in_result["report"],
            "out_sample": out_result["report"],
            "in_bars": len(in_bars),
            "out_bars": len(out_bars),
            "sharpe_degradation_pct": round(degradation * 100, 2),
            "overfitting_risk": risk,
        }


class ScenarioValidator:
    """PRD §17.3 场景验证"""

    SCENARIOS = {
        "2020_crash": {
            "start": "2020-02-15", "end": "2020-03-31",
            "description": "2020年3月暴跌",
            "expected": "趋势策略Sharpe>0.5",
            "check": lambda r: r["performance"]["sharpe_ratio"] > 0.5,
        },
        "2022_rate_hike": {
            "start": "2022-08-01", "end": "2022-10-31",
            "description": "2022年9月加息",
            "expected": "最大回撤<15%",
            "check": lambda r: abs(r["risk"]["max_drawdown"]) < 15,
        },
        "2024_high": {
            "start": "2024-01-01", "end": "2024-12-31",
            "description": "2024年创新高",
            "expected": "趋势策略正收益",
            "check": lambda r: r["performance"]["total_return"] > 0,
        },
    }

    def validate(self, strategy_name: str, bars: list[GoldBarData],
                 capital: float = 1_000_000,
                 scenario_name: str = None) -> dict:
        strategy_class = StrategyRegistry.get(strategy_name)
        if not strategy_class:
            return {"error": f"Strategy '{strategy_name}' not found"}

        scenarios = {scenario_name: self.SCENARIOS[scenario_name]} \
            if scenario_name else self.SCENARIOS

        results = []
        backtester = Backtester()

        for name, config in scenarios.items():
            scenario_bars = [
                b for b in bars
                if config["start"] <= b.datetime.strftime("%Y-%m-%d") <= config["end"]
            ]
            if len(scenario_bars) < 20:
                results.append({
                    "scenario": name, "description": config["description"],
                    "expected": config["expected"], "status": "数据不足",
                    "bars": len(scenario_bars),
                })
                continue

            strategy = strategy_class()
            result = backtester.run(strategy, scenario_bars, capital=capital)
            report = result["report"]
            try:
                passed = config["check"](report)
            except Exception:
                passed = False

            results.append({
                "scenario": name, "description": config["description"],
                "expected": config["expected"],
                "status": "通过" if passed else "未通过",
                "bars": len(scenario_bars),
                "report": {
                    "sharpe": report["performance"]["sharpe_ratio"],
                    "total_return": report["performance"]["total_return"],
                    "max_drawdown": report["risk"]["max_drawdown"],
                    "win_rate": report["performance"]["win_rate"],
                },
            })

        return {
            "strategy": strategy_name,
            "results": results,
            "all_passed": all(r.get("status") == "通过" for r in results),
        }


class WalkForwardValidatorAdapter:
    """适配器 — 将 WalkForwardValidator 包装为 validation.py 风格接口"""

    def __init__(self, train_window: int = 252, test_window: int = 20,
                 embargo_days: int = 20, purge_days: int = 1,
                 capital: float = 1_000_000, config: GoldSettings = None):
        self._inner = WalkForwardValidator(
            train_window=train_window, test_window=test_window,
            embargo_days=embargo_days, purge_days=purge_days,
            capital=capital, config=config,
        )

    def validate(self, strategy_name: str, bars: list[GoldBarData],
                 params: dict = None) -> dict:
        strategy_class = StrategyRegistry.get(strategy_name)
        if not strategy_class:
            return {"error": f"Strategy '{strategy_name}' not found"}
        return self._inner.validate(strategy_class, bars, params=params)


class CPCVValidatorAdapter:
    """适配器 — 将 CPCVValidator 包装为 validation.py 风格接口"""

    def __init__(self, n_groups: int = 6, k_test: int = 2,
                 embargo_days: int = 20, purge_days: int = 1,
                 capital: float = 1_000_000, config: GoldSettings = None):
        self._inner = CPCVValidator(
            n_groups=n_groups, k_test=k_test,
            embargo_days=embargo_days, purge_days=purge_days,
            capital=capital, config=config,
        )

    def validate(self, strategy_name: str, bars: list[GoldBarData],
                 params: dict = None) -> dict:
        strategy_class = StrategyRegistry.get(strategy_name)
        if not strategy_class:
            return {"error": f"Strategy '{strategy_name}' not found"}
        return self._inner.validate(strategy_class, bars, params=params)
