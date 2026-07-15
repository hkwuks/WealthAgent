"""PositionEstimator tests"""
import numpy as np
from backend.fund_quant.analysis.position_estimator import estimate_position_ols


def test_estimate_position_ols_equity_dominated():
    """高权益仓位估算"""
    np.random.seed(42)
    n = 60
    equity_ret = np.random.normal(0.001, 0.01, n)
    bond_ret = np.random.normal(0.0002, 0.003, n)
    true_equity = 0.8
    nav_ret = true_equity * equity_ret + (1 - true_equity) * bond_ret
    result = estimate_position_ols(
        nav_ret.tolist(),
        {"csi300": equity_ret.tolist(), "cbi": bond_ret.tolist()},
        window=n,
    )
    assert "equity_ratio" in result
    assert "bond_ratio" in result
    assert result["equity_ratio"] > result["bond_ratio"]
    assert abs(result["equity_ratio"] - true_equity) < 0.15, \
        f"equity_ratio {result['equity_ratio']:.3f} != expected {true_equity}"


def test_estimate_position_ols_bond_dominated():
    """高固收仓位估算"""
    np.random.seed(42)
    n = 60
    equity_ret = np.random.normal(0.001, 0.01, n)
    bond_ret = np.random.normal(0.0002, 0.003, n)
    nav_ret = 0.3 * equity_ret + 0.7 * bond_ret
    result = estimate_position_ols(
        nav_ret.tolist(),
        {"csi300": equity_ret.tolist(), "cbi": bond_ret.tolist()},
        window=n,
    )
    assert result["bond_ratio"] > result["equity_ratio"]


def test_estimate_position_ols_caps_range():
    """结果应在 [0,1] 范围内"""
    np.random.seed(42)
    n = 60
    equity_ret = np.random.normal(0.001, 0.01, n)
    bond_ret = np.random.normal(0.0002, 0.003, n)
    nav_ret = 1.5 * equity_ret + (-0.5) * bond_ret  # 极端值测试裁剪
    result = estimate_position_ols(
        nav_ret.tolist(),
        {"csi300": equity_ret.tolist(), "cbi": bond_ret.tolist()},
        window=n,
    )
    assert 0 <= result["equity_ratio"] <= 1
    assert 0 <= result["bond_ratio"] <= 1
    assert abs(result["equity_ratio"] + result["bond_ratio"] - 1) < 0.2


def test_estimate_position_insufficient_data():
    """数据不足 20 天时返回 None"""
    result = estimate_position_ols(
        [0.01] * 10,
        {"csi300": [0.01] * 10, "cbi": [0.005] * 10},
        window=60,
    )
    assert result is None


def test_estimate_position_default_window():
    """默认 window=60"""
    np.random.seed(42)
    n = 80
    equity_ret = np.random.normal(0.001, 0.01, n)
    bond_ret = np.random.normal(0.0002, 0.003, n)
    nav_ret = 0.6 * equity_ret + 0.4 * bond_ret
    result = estimate_position_ols(
        nav_ret.tolist(),
        {"csi300": equity_ret.tolist(), "cbi": bond_ret.tolist()},
    )
    assert result is not None
