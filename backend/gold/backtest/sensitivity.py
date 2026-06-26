"""
参数敏感性分析 — 邻域扫描 + 稳健性评估
"""

from backend.gold.strategy.base import StrategyRegistry
from backend.gold.backtest.engine import Backtester
from backend.gold.core.models import GoldBarData
from loguru import logger


class SensitivityAnalyzer:
    """参数敏感性分析"""

    def __init__(self, capital: float = 1_000_000):
        self.capital = capital

    def analyze(self, strategy_name: str, base_params: dict,
                param_ranges: dict, bars: list[GoldBarData]) -> dict:
        """
        对策略参数进行邻域扫描

        Args:
            strategy_name: 策略名称
            base_params: 基准参数
            param_ranges: 参数扫描范围 {"param_name": [v1, v2, ...]}
            bars: K线数据

        Returns: 每组参数的回测指标 + 稳健性评估
        """
        results = []
        backtester = Backtester()
        strategy_class = StrategyRegistry.get(strategy_name)

        if not strategy_class:
            return {"error": f"Strategy '{strategy_name}' not found"}

        for param_name, values in param_ranges.items():
            for value in values:
                params = {**base_params, param_name: value}
                strategy = strategy_class(**params)
                try:
                    result = backtester.run(strategy, bars, capital=self.capital)
                    report = result["report"]
                    results.append({
                        "param_name": param_name,
                        "param_value": value,
                        "sharpe": report["performance"]["sharpe_ratio"],
                        "max_dd": report["risk"]["max_drawdown"],
                        "total_return": report["performance"]["total_return"],
                        "win_rate": report["performance"]["win_rate"],
                    })
                except Exception as e:
                    logger.debug(f"Sensitivity scan failed for {param_name}={value}: {e}")
                    results.append({
                        "param_name": param_name,
                        "param_value": value,
                        "sharpe": None,
                        "max_dd": None,
                        "total_return": None,
                        "win_rate": None,
                    })

        return {
            "strategy": strategy_name,
            "base_params": base_params,
            "sensitivity_data": results,
            "conclusion": self._assess_robustness(results),
        }

    def _assess_robustness(self, results: list) -> dict:
        """评估策略稳健性"""
        by_param: dict[str, list] = {}
        for r in results:
            by_param.setdefault(r["param_name"], []).append(r)

        assessments = {}
        for param, items in by_param.items():
            sharpes = [i["sharpe"] for i in items if i["sharpe"] is not None]
            if len(sharpes) < 2:
                assessments[param] = {"status": "数据不足", "detail": ""}
                continue

            sharpe_range = max(sharpes) - min(sharpes)
            base_sharpe = sorted(sharpes)[len(sharpes) // 2]
            change_pct = sharpe_range / abs(base_sharpe) if base_sharpe != 0 else float('inf')

            if change_pct < 0.3:
                status = "稳健"
            elif change_pct < 0.5:
                status = "中等"
            else:
                status = "不稳健"

            assessments[param] = {
                "status": status,
                "sharpe_range": round(sharpe_range, 4),
                "change_pct": round(change_pct * 100, 1),
                "detail": f"Sharpe变化{change_pct*100:.1f}%",
            }

        return assessments
