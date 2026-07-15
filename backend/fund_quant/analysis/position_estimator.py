"""仓位估算 — 基于 OLS 回归分解平衡混合基金资产比例"""
from typing import Optional
import numpy as np
from sklearn.linear_model import LinearRegression


def estimate_position_ols(
    nav_returns: list[float],
    index_returns: dict[str, list[float]],
    window: int = 60,
) -> Optional[dict]:
    """使用 OLS 回归估算权益/固收仓位

    model: nav_return = β₁ × equity_index + β₂ × bond_index + ε

    Args:
        nav_returns: 基金日收益率序列
        index_returns: {"csi300": [...], "cbi": [...]} 沪深300和中债指数收益率
        window: 滚动窗口（默认 60 交易日）

    Returns:
        {"equity_ratio": float, "bond_ratio": float, "r_squared": float}
        或 None（数据不足）
    """
    min_window = 20
    actual_window = min(window, len(nav_returns),
                        len(next(iter(index_returns.values()))))
    if actual_window < min_window:
        return None

    eq_rets = np.array(index_returns.get("csi300", []))[-actual_window:]
    bd_rets = np.array(index_returns.get("cbi", []))[-actual_window:]
    nav = np.array(nav_returns)[-actual_window:]

    if len(nav) < min_window or len(eq_rets) < min_window or len(bd_rets) < min_window:
        return None

    X = np.column_stack([eq_rets, bd_rets])
    model = LinearRegression(fit_intercept=True)
    model.fit(X, nav)

    equity_ratio = float(np.clip(model.coef_[0], 0, 1))
    bond_ratio = float(np.clip(model.coef_[1], 0, 1))

    # 归一化到 1
    total = equity_ratio + bond_ratio
    if total > 0:
        equity_ratio /= total
        bond_ratio /= total

    r_squared = float(model.score(X, nav))

    return {
        "equity_ratio": round(equity_ratio, 4),
        "bond_ratio": round(bond_ratio, 4),
        "r_squared": round(r_squared, 4),
    }
