"""Fund 域因子注册入口。之前没有任何代码触发注册，所有因子都是死代码。"""
from backend.core.factor.registry import FactorRegistry

_LOADED = False


def load_all() -> int:
    """导入并注册全部 fund 域因子。幂等，返回注册总数。"""
    global _LOADED
    from . import technical  # noqa: F401  新增的量价因子

    n = technical.register_all()
    _LOADED = True
    return FactorRegistry.count()


__all__ = ["load_all", "FactorRegistry"]
