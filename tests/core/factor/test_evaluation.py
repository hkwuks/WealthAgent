# tests/core/factor/test_evaluation.py
import sys; sys.path.insert(0, 'backend/..')
from datetime import date
import numpy as np
from backend.core.factor.evaluation import EvaluationEngine, Neutralizer
from backend.core.factor.models import FactorEvaluationReport


class DummyFeed:
    def get_forward_returns(self, symbols, from_date, to_date):
        return {s: 0.01 for s in symbols}
    def get_factor_input(self, symbols, as_of, lookback):
        return {s: 1.0 for s in symbols}


class TestNeutralizer:
    def test_industry_neutralize(self):
        fv = {"A": 1.0, "B": 3.0, "C": 2.0, "D": 0.0}
        ind = {"A": "t", "B": "t", "C": "h", "D": "h"}
        result = Neutralizer.industry_neutralize(fv, ind)
        assert abs(result["A"] + result["B"]) < 1e-10

    def test_winsorize_no_change(self):
        fv = {"A": 1.0, "B": 1.1, "C": 0.9, "D": 1.05}
        result = Neutralizer.winsorize(fv)
        assert len(result) == 4

    def test_winsorize_extreme(self):
        fv = {"A": 1.0, "B": 1.1, "C": 0.9, "D": 1000.0}
        result = Neutralizer.winsorize(fv)
        assert result["D"] < 1000

    def test_style_neutralize(self):
        fv = {"A": 1.0, "B": 2.0, "C": 3.0}
        exposures = {"A": {"size": 0.5}, "B": {"size": 1.0}, "C": {"size": 1.5}}
        result = Neutralizer.style_neutralize(fv, exposures, ["size"])
        assert len(result) == 3


class TestEvaluationEngine:
    def test_ic_random_data(self):
        fv = {"A": 0.1, "B": 0.2, "C": 0.3, "D": 0.4, "E": 0.5}
        fr = {"A": 0.01, "B": -0.02, "C": 0.03, "D": -0.01, "E": 0.02}
        ic = EvaluationEngine._calc_ic(fv, fr)
        assert -1.0 <= ic.rank_ic <= 1.0

    def test_ic_perfect_correlation(self):
        fv = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}
        fr = {"A": 0.01, "B": 0.02, "C": 0.03, "D": 0.04, "E": 0.05}
        ic = EvaluationEngine._calc_ic(fv, fr)
        assert ic.rank_ic > 0.9

    def test_ic_inverse_correlation(self):
        fv = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1}
        fr = {"A": 0.01, "B": 0.02, "C": 0.03, "D": 0.04, "E": 0.05}
        ic = EvaluationEngine._calc_ic(fv, fr)
        assert ic.rank_ic < -0.9

    def test_group_returns_monotonic(self):
        fv = {s: v for v, s in enumerate([chr(65+i) for i in range(30)])}
        fr = {s: v/100 for v, s in enumerate([chr(65+i) for i in range(30)])}
        gr = EvaluationEngine._calc_group_returns(fv, fr, n_groups=5)
        assert gr.monotonicity_score >= 0.8

    def test_turnover_zero(self):
        hist = [
            {"A": 1.0, "B": 0.5, "C": 0.0},
            {"A": 1.0, "B": 0.5, "C": 0.0},
        ]
        to = EvaluationEngine._calc_turnover(hist)
        assert to["total"] == 0.0

    def test_turnover_full(self):
        hist = [
            {"A": 1.0, "B": 0.5, "C": 0.0},
            {"A": 0.0, "B": 0.5, "C": 1.0},
        ]
        to = EvaluationEngine._calc_turnover(hist)
        assert to["total"] > 0.5

    def test_verdict_noise(self):
        r = FactorEvaluationReport(rank_ic_mean=0.01, ic_ir=0.05,
                                    long_short_t_stat=0.5,
                                    monotonicity_score=0.3,
                                    factor_turnover=0.5)
        assert EvaluationEngine._verdict(r) == "noise"

    def test_verdict_usable(self):
        r = FactorEvaluationReport(rank_ic_mean=0.05, ic_ir=0.6,
                                    long_short_t_stat=2.5,
                                    monotonicity_score=0.7,
                                    factor_turnover=0.25)
        assert EvaluationEngine._verdict(r) == "usable"

    def test_verdict_strong(self):
        r = FactorEvaluationReport(rank_ic_mean=0.10, ic_ir=0.9,
                                    long_short_t_stat=3.5,
                                    monotonicity_score=0.9,
                                    factor_turnover=0.15)
        assert EvaluationEngine._verdict(r) == "strong"
