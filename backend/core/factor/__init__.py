"""FactorEngine — 跨域因子分析引擎"""

from .config import EvalConfig
from .exceptions import FactorError, FactorNotFound, EvaluationError, ConfigError
from .factor import Factor
from .models import (
    FactorMeta, FactorSnapshot, FactorEvaluationReport,
    ICSnapshot, GroupReturnResult, FamaMacBethResult, EvalCache,
)
from .registry import FactorRegistry
from .evaluation import EvaluationEngine, Neutralizer
from .report import FactorReport, FactorAudit
from .mining import CombinatorialSearch, FormulaSearch

__all__ = [
    "EvalConfig", "FactorError", "FactorNotFound", "EvaluationError",
    "ConfigError", "Factor", "FactorMeta", "FactorSnapshot",
    "FactorEvaluationReport", "ICSnapshot", "GroupReturnResult",
    "FamaMacBethResult", "EvalCache", "FactorRegistry",
    "EvaluationEngine", "Neutralizer", "FactorReport", "FactorAudit",
    "CombinatorialSearch", "FormulaSearch",
]
