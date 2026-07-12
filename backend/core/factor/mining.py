"""因子挖掘管道"""
from __future__ import annotations

from datetime import date
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
import itertools

import numpy as np

from .factor import Factor
from .models import FactorMeta
from .registry import FactorRegistry

if TYPE_CHECKING:
    from .evaluation import EvaluationEngine


@dataclass
class ComboCandidate:
    """组合因子候选"""
    factor_cls: type[Factor]
    formula: str
    report: Any


class CombinatorialSearch:
    """组合因子搜索——对基础因子做二元运算"""

    OPERATORS = ["+", "-", "*", "/", "ortho"]

    def search(self, base_factors: list[type[Factor]],
               symbols: list[str],
               period: tuple[date, date],
               eval_engine: EvaluationEngine,
               min_ic: float = 0.04,
               max_turnover: float = 0.4,
               max_correlation: float = 0.7) -> list[ComboCandidate]:
        candidates: list[ComboCandidate] = []

        for fa, fb in itertools.combinations(base_factors, 2):
            for op in self.OPERATORS:
                combo_cls = self._build_combo_factor(fa, fb, op)
                try:
                    report = eval_engine.run(combo_cls(), symbols,
                                             period[0], period[1])
                except Exception:
                    continue

                if abs(report.rank_ic_mean) < min_ic:
                    continue
                if report.factor_turnover > max_turnover:
                    continue
                if report.n_periods < 12:
                    continue

                candidates.append(ComboCandidate(
                    factor_cls=combo_cls,
                    formula=f"{fa.meta.name} {op} {fb.meta.name}",
                    report=report,
                ))

        candidates.sort(key=lambda c: -abs(c.report.rank_ic_mean))
        return self._dedup_by_correlation(candidates, max_correlation)

    def _build_combo_factor(self, fa: type[Factor], fb: type[Factor],
                            op: str) -> type[Factor]:
        name = f"{fa.meta.name}_{op}_{fb.meta.name}"
        meta = FactorMeta(
            name=name,
            display_name=f"{fa.meta.display_name} {op} {fb.meta.display_name}",
            category="combo",
            domain=fa.meta.domain,
            description=f"组合因子: {fa.meta.name} {op} {fb.meta.name}",
            direction=fa.meta.direction,
        )

        class ComboFactor(Factor):
            meta = meta

            def compute(self, symbols, as_of, lookback, data):
                fa_val = fa().compute(symbols, as_of, lookback, data)
                fb_val = fb().compute(symbols, as_of, lookback, data)
                common = set(fa_val.keys()) & set(fb_val.keys())
                result = {}
                for s in common:
                    a, b = fa_val[s], fb_val[s]
                    if op == "+":
                        result[s] = a + b
                    elif op == "-":
                        result[s] = a - b
                    elif op == "*":
                        result[s] = a * b
                    elif op == "/":
                        result[s] = a / max(abs(b), 1e-10)
                    elif op == "ortho":
                        if abs(b) < 1e-10:
                            result[s] = a
                        else:
                            result[s] = a - (a * b) / (b * b) * b
                return result

        return ComboFactor

    @staticmethod
    def _dedup_by_correlation(candidates: list[ComboCandidate],
                               max_corr: float = 0.7) -> list[ComboCandidate]:
        if not candidates:
            return []
        keep = [candidates[0]]
        for c in candidates[1:]:
            corr = CombinatorialSearch._approx_corr(c, keep)
            if corr < max_corr:
                keep.append(c)
        return keep

    @staticmethod
    def _approx_corr(c1: ComboCandidate,
                      existing: list[ComboCandidate]) -> float:
        for e in existing:
            parts_c1 = set(c1.formula.replace(" ", "").split("+")[0].split("-")[0].split("*")[0].split("/")[0])
            parts_e = set(e.formula.replace(" ", "").split("+")[0].split("-")[0].split("*")[0].split("/")[0])
            shared = parts_c1 & parts_e
            if len(shared) >= 2:
                return 0.8
        return 0.0


class FormulaSearch:
    """公式化因子搜索——轻量级遗传规划"""

    def __init__(self, pop_size: int = 50, generations: int = 5):
        self.pop_size = pop_size
        self.generations = generations
        self._rng = np.random.RandomState(42)

    def search(self, base_factors: list[type[Factor]],
               symbols: list[str],
               period: tuple[date, date],
               eval_engine: EvaluationEngine) -> list[ComboCandidate]:
        pop = list(base_factors)
        for gen in range(self.generations):
            offspring = []
            for _ in range(self.pop_size - len(pop)):
                p1 = pop[self._rng.randint(len(pop))]
                p2 = pop[self._rng.randint(len(pop))]
                child = self._crossover(p1, p2)
                offspring.append(child)
            mutated = [self._mutate(p) for p in pop[:self.pop_size // 4]]
            pop = pop + offspring + mutated
            pop = pop[:self.pop_size]

        candidates = []
        for f_cls in pop:
            try:
                report = eval_engine.run(f_cls(), symbols, period[0], period[1])
            except Exception:
                continue
            if abs(report.rank_ic_mean) >= 0.04:
                candidates.append(ComboCandidate(f_cls, f_cls.meta.name, report))

        candidates.sort(key=lambda c: -abs(c.report.rank_ic_mean))
        return candidates[:10]

    def _crossover(self, f1: type[Factor], f2: type[Factor]) -> type[Factor]:
        name = f"gp_{f1.meta.name}_{f2.meta.name}_{self._rng.randint(1000)}"
        meta = FactorMeta(
            name=name, display_name=name, category="gp",
            domain=f1.meta.domain, description="GP 生成", direction=1,
        )
        class GpFactor(Factor):
            meta = meta
            def compute(self, symbols, as_of, lookback, data):
                v1 = f1().compute(symbols, as_of, lookback, data)
                v2 = f2().compute(symbols, as_of, lookback, data)
                common = set(v1.keys()) & set(v2.keys())
                return {s: 0.5 * v1[s] + 0.5 * v2[s] for s in common}
        return GpFactor

    def _mutate(self, f: type[Factor]) -> type[Factor]:
        name = f"gp_mut_{f.meta.name}_{self._rng.randint(1000)}"
        meta = FactorMeta(
            name=name, display_name=name, category="gp_mut",
            domain=f.meta.domain, description="GP 变异", direction=1,
        )
        class MutFactor(Factor):
            meta = meta
            def compute(self, symbols, as_of, lookback, data):
                raw = f().compute(symbols, as_of, lookback, data)
                return {s: -v for s, v in raw.items()}
        return MutFactor
