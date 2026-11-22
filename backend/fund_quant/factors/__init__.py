"""Fund 域因子实现与注册。

两类来源：
  FUND_FACTORS  —— 10 个基本面/风险因子（sharpe/max_drawdown/...），本模块导入时即注册
  technical     —— 28 个量价因子（算子 × 窗口），需显式调 load_all() 注册

load_all() 是统一的幂等入口，供 API 与脚本调用。
"""
import sys as _sys
from pathlib import Path as _Path

from backend.core.factor.registry import FactorRegistry

from .behavioral import CalendarReturnFactor
from .concentration import HoldingConcentrationFactor
from .flow import FundFlowFactor
from .manager import ManagerTenureFactor
from .risk import MaxDrawdownFactor
from .risk_adjusted import CaptureRatioFactor, InfoRatioFactor, SharpeRatioFactor
from .structural import FeeRateFactor, FundScaleFactor

# adapter.py 与 risk_checks.py 用的是 `from core import ...`（项目既有约定），
# 只有 backend/ 在 sys.path 上才解析得到。uvicorn 由 main.py 注入，脚本没有。
_BACKEND_DIR = str(_Path(__file__).resolve().parents[2])
if _BACKEND_DIR not in _sys.path:
    _sys.path.insert(0, _BACKEND_DIR)

FUND_FACTORS = (
    CalendarReturnFactor,
    HoldingConcentrationFactor,
    FundFlowFactor,
    ManagerTenureFactor,
    MaxDrawdownFactor,
    CaptureRatioFactor,
    InfoRatioFactor,
    SharpeRatioFactor,
    FeeRateFactor,
    FundScaleFactor,
)

_LOADED = False


def register_fund_factors() -> None:
    """注册基金因子；重复调用安全，便于 API 和测试显式初始化。"""
    registered = {meta.name for meta in FactorRegistry.list(domain="fund")}
    for factor_cls in FUND_FACTORS:
        if factor_cls.meta.name not in registered:
            FactorRegistry.register(factor_cls, factor_cls.meta)


def load_all() -> int:
    """注册全部 fund 域因子（基本面 + 量价）。幂等，返回注册总数。"""
    global _LOADED
    if _LOADED:
        return FactorRegistry.count()

    register_fund_factors()

    from . import technical
    technical.register_all()

    _LOADED = True
    return FactorRegistry.count()


register_fund_factors()

__all__ = ["load_all", "register_fund_factors", "FUND_FACTORS", "FactorRegistry"]
