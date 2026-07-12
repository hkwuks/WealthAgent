"""FactorEngine 自定义异常"""


class FactorError(Exception):
    """因子引擎基础异常"""


class FactorNotFound(FactorError):
    """因子未注册"""


class EvaluationError(FactorError):
    """因子评价过程异常"""


class ConfigError(FactorError):
    """配置参数异常"""


def demo():
    """异常类自检"""
    assert issubclass(FactorNotFound, FactorError)
    assert issubclass(EvaluationError, FactorError)
    assert issubclass(ConfigError, FactorError)
    print("[exceptions] ✅ 异常层次通过")


if __name__ == "__main__":
    demo()
