"""因子评价配置"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalConfig:
    """评价参数配置"""
    forward_periods: list[int] = field(default_factory=lambda: [1, 5, 20, 60])
    n_groups: int = 5
    min_stocks_per_period: int = 30
    decay_warmup_days: int = 252
    turnover_warmup_days: int = 60
    fm_add_controls: bool = False
    ic_rank: bool = True
    significance_level: float = 0.05

    # 通过阈值（strong/usable/weak → 各指标下限）
    thresholds: dict = field(default_factory=lambda: {
        "strong": {"rank_ic": 0.08, "ic_ir": 0.8, "spread_t": 3.0,
                   "monotonicity": 0.8, "turnover": 0.2},
        "usable": {"rank_ic": 0.04, "ic_ir": 0.5, "spread_t": 2.0,
                   "monotonicity": 0.6, "turnover": 0.3},
        "weak":   {"rank_ic": 0.02, "ic_ir": 0.1, "spread_t": 1.5,
                   "monotonicity": 0.4, "turnover": 0.4},
    })


def demo():
    cfg = EvalConfig()
    assert cfg.forward_periods == [1, 5, 20, 60]
    assert cfg.n_groups == 5
    assert cfg.thresholds["strong"]["ic_ir"] == 0.8
    assert cfg.thresholds["usable"]["ic_ir"] == 0.5
    print("[config] ✅ EvalConfig 默认值通过")


if __name__ == "__main__":
    demo()
