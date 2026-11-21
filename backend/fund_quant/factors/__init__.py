"""Fund 域因子注册入口。之前没有任何代码触发注册，所有因子都是死代码。"""
import sys as _sys
from pathlib import Path as _Path

from backend.core.factor.registry import FactorRegistry

_LOADED = False

# adapter.py 与 risk_checks.py 用的是 `from core import ...`（项目既有约定），
# 只有 backend/ 在 sys.path 上才解析得到。uvicorn 由 main.py 注入，脚本没有。
_BACKEND_DIR = str(_Path(__file__).resolve().parents[2])
if _BACKEND_DIR not in _sys.path:
    _sys.path.insert(0, _BACKEND_DIR)


def load_all() -> int:
    """导入并注册全部 fund 域因子。幂等，返回注册总数。

    两类来源：
      technical   —— 28 个量价因子（算子 × 窗口）
      adapter     —— 10 个基本面/风险因子（sharpe/max_drawdown/...）
    缺了后者，暴露接口只有 28 个因子，而 /factors/list 显示 0 个。
    """
    global _LOADED
    if _LOADED:
        return FactorRegistry.count()

    from . import technical
    technical.register_all()

    from backend.fund_quant.adapter import FundDomainAdapter
    FundDomainAdapter().register_factors()

    _LOADED = True
    return FactorRegistry.count()


__all__ = ["load_all", "FactorRegistry"]
