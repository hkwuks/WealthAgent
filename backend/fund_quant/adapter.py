"""基金领域适配 — FundDomainAdapter + FundCostModel"""
from __future__ import annotations

from datetime import date
from typing import Optional

from core import (
    DomainAdapter, ExecutionEngine, CostModel,
    RiskCheck, Strategy, StrategyRegistry,
    T1ExecutionEngine, NoSlippage,
    MaxDrawdownCheck, DailyLossCheck, SignalFrequencyCheck,
    ConsecutiveLossCheck, PositionLimitCheck,
    Signal, Direction, Fill,
    DataFeed, FundNavPoint, Bar,
)


class FundCostModel(CostModel):
    """基金费率模型

    申购费按金额比例，赎回费按持有天数阶梯，管理费+托管费年化日提。
    简化版：申购×申购费率 + 赎回×赎回费率。
    """

    def __init__(self, fund_type: str = "stock",
                 subscription_rate: Optional[float] = None,
                 redemption_rate: Optional[float] = None,
                 management_rate: float = 0.015,
                 custody_rate: float = 0.0025):
        self.fund_type = fund_type
        # 默认费率表 — 与 fund_quant 原有配置一致
        self._sub_rates = {
            "stock": 0.015, "hybrid": 0.015, "bond": 0.008,
            "index": 0.010, "qdii": 0.015, "money": 0.0, "fof": 0.012,
        }
        self._sub_rate = subscription_rate or self._sub_rates.get(fund_type, 0.015)
        self._redemption_rate = redemption_rate or 0.005  # 默认持有 < 1年赎回费率
        self._management_rate = management_rate  # 年化管理费
        self._custody_rate = custody_rate        # 年化托管费

    def calc(self, signal: Signal, fill: Fill) -> float:
        """计算单笔成本 = 申购费 + 赎回费（毛估，不区分 A/C 类）
        Returns:
            float: 交易成本（正数）
        """
        amount = fill.price * fill.volume
        sub_cost = amount * self._sub_rate          # 申购费
        red_cost = amount * self._redemption_rate    # 赎回费（毛估最短持有期费率）
        return round(sub_cost + red_cost, 4)


class FundDomainAdapter(DomainAdapter):
    """基金领域适配器"""

    @property
    def name(self) -> str:
        return "fund"

    def create_data_feed(self, config: dict) -> DataFeed:
        raise NotImplementedError("使用 fund_quant 现有数据层，Phase 3 迁移")

    def create_executor(self, config: dict) -> ExecutionEngine:
        return T1ExecutionEngine(confirmation_delay=config.get("confirmation_delay", 1))

    def create_cost_model(self, config: dict) -> CostModel:
        return FundCostModel(
            fund_type=config.get("fund_type", "stock"),
        )

    def default_risk_checks(self) -> list[RiskCheck]:
        from .risk.risk_checks import (
            ConfidenceCheck, CooldownCheck, MinHoldingCheck,
            FundPositionLimitCheck, ConcentrationCheck,
            LiquidityCheck, CashReserveCheck,
            RelatedFundConcentrationCheck, ScaleDropCheck,
            StyleDriftCheck, FundTypeCheck, BondDrawdownCheck,
            QdiiFxRiskCheck, FofUnderlyingCheck, ClosedEndCheck,
        )
        return [
            # 通用检查
            MaxDrawdownCheck(drawdown_limit=0.20),
            DailyLossCheck(limit=0.05),
            SignalFrequencyCheck(max_per_day=5),
            ConsecutiveLossCheck(max_losses=7),
            PositionLimitCheck(max_positions=20),
            # 基金特有统计层
            ConfidenceCheck(min_confidence=0.6),
            CooldownCheck(cooldown_days=5),
            MinHoldingCheck(min_days=7),
            FundPositionLimitCheck(max_position_pct=0.3),
            # 基金特有组合层
            ConcentrationCheck(max_pct=0.4),
            LiquidityCheck(max_redemption_pct=0.2),
            CashReserveCheck(min_cash_pct=0.05),
            RelatedFundConcentrationCheck(max_pct=0.5),
            ScaleDropCheck(min_scale=10_000_000),
            # 风格漂移（组合外部分析器）
            StyleDriftCheck(),
            # 基金类型差异化规则
            FundTypeCheck(),
            BondDrawdownCheck(limit=0.05),
            QdiiFxRiskCheck(fx_vol_limit=0.05),
            FofUnderlyingCheck(),
            ClosedEndCheck(),
        ]

    def get_available_strategies(self) -> dict[str, type[Strategy]]:
        return {
            "momentum_fund": AdpatedMomentumFund,
        }


# ── 适配后的基金动量策略 ──

@StrategyRegistry.register("momentum_fund")
class AdpatedMomentumFund(Strategy):
    """动量择时策略 — 移植自 fund_quant.strategy.timing.momentum.MomentumStrategy
    TSMOM 多周期融合 + 反转修正
    """
    name = "momentum_fund"
    strategy_type = "timing"
    description = "基于净值时间序列动量的择时策略"
    default_params = {
        "momentum_periods": [20, 60, 120],
        "weights": [0.5, 0.3, 0.2],
        "skip_days": 5,
        "buy_threshold": 0.02,
        "sell_threshold": -0.02,
    }
    min_history_days = 120

    def __init__(self):
        super().__init__()
        self._nav_history: list[float] = []
        self._fund_code = ""

    def on_data(self, data):
        """接收 FundNavPoint 或 Bar，提取净值"""
        nav = data.nav if hasattr(data, "nav") else data.close
        if not self._fund_code:
            self._fund_code = getattr(data, "fund_code", "") or getattr(data, "symbol", "")
        self._nav_history.append(nav)

        max_period = max(self.params.get("momentum_periods", [120]))
        if len(self._nav_history) < max_period + self.params.get("skip_days", 5):
            return

        arr = self._nav_history[:]
        returns = [(arr[i] - arr[i - 1]) / arr[i - 1] for i in range(1, len(arr))]

        skip = self.params.get("skip_days", 5)
        periods = self.params.get("momentum_periods", [20, 60, 120])
        weights = self.params.get("weights", [0.5, 0.3, 0.2])

        scores = []
        for n, w in zip(periods, weights):
            if len(returns) < n + skip:
                scores.append(0.0)
                continue
            period_rets = returns[-(n + skip):-skip] if skip > 0 else returns[-n:]
            scores.append(sum(period_rets))

        total_w = sum(weights[:len(scores)])
        if total_w <= 0:
            return

        weighted = sum(w * s for w, s in zip(weights, scores)) / total_w
        buy_th = self.params.get("buy_threshold", 0.02)
        sell_th = self.params.get("sell_threshold", -0.02)

        if weighted > buy_th:
            self.ctx.emit(Signal(
                id="", strategy=self.name, symbol=self._fund_code,
                direction=Direction.LONG,
                price=nav, volume=1,
                confidence=min(abs(weighted) / (buy_th * 2), 1.0),
                reason=f"动量得分 {weighted:.4f} > {buy_th}",
            ))
        elif weighted < sell_th:
            # ponytail: 基金做空用 CLOSE_LONG 表示减仓，Phase 3 完善语义
            self.ctx.emit(Signal(
                id="", strategy=self.name, symbol=self._fund_code,
                direction=Direction.CLOSE_LONG,
                price=nav, volume=1,
                confidence=min(abs(weighted) / (abs(sell_th) * 2), 1.0),
                reason=f"动量得分 {weighted:.4f} < {sell_th}",
            ))


def demo():
    """基金领域适配自检"""
    from core import BacktestEngine, BacktestConfig

    adapter = FundDomainAdapter()
    assert adapter.name == "fund"
    cost = adapter.create_cost_model({"fund_type": "stock"})
    signal = Signal(id="", strategy="test", symbol="000001",
                    direction=Direction.LONG, price=1.5, volume=10000)
    fill = Fill(order_id="o1", price=1.5, volume=10000)
    c = cost.calc(signal, fill)
    assert c > 0, f"expected cost > 0, got {c}"
    print(f"[fund_adapter] ✅ FundCostModel: 申购1万份@1.5元 = {c} 元")

    adapter.get_available_strategies()
    assert len(adapter.default_risk_checks()) == 5
    print("[fund_adapter] ✅ FundDomainAdapter 接口通过")


if __name__ == "__main__":
    demo()
