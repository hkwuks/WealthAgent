"""配置层 — 通用回测配置"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class BacktestConfig:
    """回测配置 — 通用"""
    initial_capital: float = 1_000_000
    start_date: date | None = None
    end_date: date | None = None
    data_feed: str = "local"       # local / api / file
    timeframe: str = "1d"           # 1m / 5m / 1d

    # 风控通用阈值
    max_drawdown_pct: float = 0.15
    max_daily_loss_pct: float = 0.03
    max_daily_signals: int = 10
    max_consecutive_losses: int = 5
    max_position_lots: int = 10
    max_margin_ratio: float = 0.3
    max_position_pct: float = 0.3   # 单标的最大仓位占比

    # 领域特有配置（由 DomainAdapter 填充）
    domain_params: dict = field(default_factory=dict)


def demo():
    cfg = BacktestConfig(initial_capital=500_000, timeframe="1d")
    assert cfg.initial_capital == 500_000
    assert cfg.timeframe == "1d"
    assert cfg.max_drawdown_pct == 0.15
    print("[config] ✅ BacktestConfig 通过")


if __name__ == "__main__":
    demo()
