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
    A/C份额区分，FOF双重费率穿透，分红税。
    """

    # ── 费率表 ──
    SUB_RATES = {
        "stock": 0.015, "hybrid": 0.015, "bond": 0.008,
        "index": 0.010, "qdii": 0.015, "money": 0.0, "fof": 0.012,
    }
    MGMT_RATES = {
        "stock": 0.015, "hybrid": 0.012, "bond": 0.006,
        "index": 0.005, "qdii": 0.015, "money": 0.003, "fof": 0.010,
    }
    CUSTODY_RATES = {
        "stock": 0.0025, "hybrid": 0.0020, "bond": 0.0015,
        "index": 0.0010, "qdii": 0.0025, "money": 0.0005, "fof": 0.0020,
    }
    # 赎回费率阶梯: {持有天数上限: 费率%}
    REDEMPTION_TIERS = {
        7: 1.50,       # <7天: 1.5%
        30: 0.75,      # 7-30天: 0.75%
        365: 0.50,     # 30天-1年: 0.5%
        730: 0.25,     # 1-2年: 0.25%
        999999: 0.0,   # >2年: 0%
    }

    def __init__(self, fund_type: str = "stock",
                 subscription_rate: Optional[float] = None,
                 management_rate: Optional[float] = None,
                 custody_rate: Optional[float] = None,
                 is_c_class: bool = False,
                 fof_underlying_fee: float = 0.0,
                 dividend_tax_short: float = 0.10,
                 dividend_tax_long: float = 0.0):
        self.fund_type = fund_type
        self._sub_rate = subscription_rate or self.SUB_RATES.get(fund_type, 0.015)
        self._mgmt_rate = management_rate or self.MGMT_RATES.get(fund_type, 0.015)
        self._custody_rate = custody_rate or self.CUSTODY_RATES.get(fund_type, 0.0025)
        self._is_c_class = is_c_class
        self._fof_underlying_fee = fof_underlying_fee  # FOF底层基金费率穿透
        self._div_tax_short = dividend_tax_short
        self._div_tax_long = dividend_tax_long

    def calc(self, signal: Signal, fill: Fill) -> float:
        """计算单笔交易综合成本

        开仓: 申购费 + 管理费+托管费（按180日估计）
        平仓: 赎回费 + 分红税 + 管理费+托管费（按180日估计）
        FOF: 额外穿透底层费率
        """
        amount = fill.price * fill.volume
        est_days = 180  # 估计持有期

        if signal.direction in (Direction.LONG, Direction.SHORT):
            # 开仓: 申购费 + 管理/托管费（前半段）
            sub = self._get_subscription(amount)
            daily = self._get_annual_carry(amount) * est_days / 365 / 2
            return round(sub + daily, 4)
        else:
            # 平仓: 赎回费 + 管理/托管费（后半段）+ 分红税
            red = self._get_redemption(amount, est_days)
            daily = self._get_annual_carry(amount) * est_days / 365 / 2
            div_tax = self._get_dividend_tax(amount, est_days)
            return round(red + daily + div_tax, 4)

    def _get_subscription(self, amount: float) -> float:
        """申购费"""
        fee = amount * self._sub_rate
        # FOF穿透
        if self.fund_type == "fof" and self._fof_underlying_fee > 0:
            fee += amount * self._fof_underlying_fee
        return fee

    def _get_redemption(self, amount: float, holding_days: int) -> float:
        """赎回费（含A/C类区分）"""
        if self._is_c_class:
            # C类持有超过阈值免赎回费
            return 0.0 if holding_days >= 30 else amount * 0.005
        for limit, pct in sorted(self.REDEMPTION_TIERS.items()):
            if holding_days < limit:
                return amount * (pct / 100)
        return 0.0

    def _get_annual_carry(self, amount: float) -> float:
        """年化管理+托管费"""
        mgmt = amount * self._mgmt_rate
        custody = amount * self._custody_rate
        if self._is_c_class:
            mgmt += amount * 0.008  # C类销售服务费 ~0.8%/年
        if self.fund_type == "fof":
            mgmt += amount * self._fof_underlying_fee  # FOF穿透
        return mgmt + custody

    def _get_dividend_tax(self, amount: float, holding_days: int) -> float:
        """分红税"""
        rate = self._div_tax_long if holding_days >= 365 else self._div_tax_short
        return amount * rate * 0.01  # 假设1%分红率


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
