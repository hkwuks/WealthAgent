"""因子评价引擎"""
from __future__ import annotations

import sys
from datetime import date
from typing import Any

import numpy as np
from scipy.stats import spearmanr, ttest_ind, t as t_dist

try:
    from .config import EvalConfig
    from .models import (
        FactorSnapshot, FactorEvaluationReport,
        ICSnapshot, GroupReturnResult, FamaMacBethResult,
    )
except ImportError:
    sys.path.insert(0, 'backend/..')
    from backend.core.factor.config import EvalConfig
    from backend.core.factor.models import (
        FactorSnapshot, FactorEvaluationReport,
        ICSnapshot, GroupReturnResult, FamaMacBethResult,
    )


class Neutralizer:
    """因子中性化——剥离风格/行业/极端值影响"""

    @staticmethod
    def industry_neutralize(factor_values: dict[str, float],
                            industry_map: dict[str, str]) -> dict[str, float]:
        """行业市值中性化：因子值 - 行业均值"""
        industries: dict[str, list[tuple[str, float]]] = {}
        for symbol, val in factor_values.items():
            ind = industry_map.get(symbol, "unknown")
            industries.setdefault(ind, []).append((symbol, val))

        result: dict[str, float] = {}
        for ind, vals in industries.items():
            vals_arr = np.array([v for _, v in vals])
            mean = float(np.mean(vals_arr)) if len(vals_arr) > 0 else 0.0
            for symbol, val in vals:
                result[symbol] = val - mean
        return result

    @staticmethod
    def style_neutralize(factor_values: dict[str, float],
                         style_exposures: dict[str, dict[str, float]],
                         style_names: list[str]) -> dict[str, float]:
        """风格中性化：因子值对风格因子回归 → 取残差"""
        symbols = list(factor_values.keys())
        f = np.array([factor_values[s] for s in symbols])
        X = np.column_stack([
            np.array([style_exposures[s][st] for s in symbols])
            for st in style_names
        ])
        X = np.column_stack([np.ones(len(symbols)), X])
        beta = np.linalg.lstsq(X, f, rcond=None)[0]
        resid = f - X @ beta
        return {s: float(resid[i]) for i, s in enumerate(symbols)}

    @staticmethod
    def winsorize(factor_values: dict[str, float],
                  limits: float = 0.01) -> dict[str, float]:
        """MAD 去极值"""
        vals = np.array(list(factor_values.values()))
        median = float(np.median(vals))
        mad = float(np.median(np.abs(vals - median)))
        if mad < 1e-10:
            return factor_values
        clipped = np.clip(vals,
                          median - 3 * mad / 0.6745,
                          median + 3 * mad / 0.6745)
        return dict(zip(factor_values.keys(), clipped))


class EvaluationEngine:
    """因子评价引擎"""

    def __init__(self, data_feed: Any, config: EvalConfig | None = None):
        self._feed = data_feed
        self._config = config or EvalConfig()

    def run(self, factor: Any, symbols: list[str],
            start: date, end: date) -> FactorEvaluationReport:
        """完整评价管道"""
        config = self._config
        meta = factor.meta
        report = FactorEvaluationReport(
            factor_name=meta.name, domain=meta.domain,
            category=meta.category,
            evaluation_period=(start, end),
        )

        ic_snapshots: list[ICSnapshot] = []
        group_results: list[GroupReturnResult] = []
        fm_results: list[FamaMacBethResult] = []
        factor_value_history: list[dict[str, float]] = []

        step = 21
        all_dates = self._generate_eval_dates(start, end, step)

        for t_date in all_dates:
            lookback = meta.params.get("lookback", meta.min_history_days)
            try:
                raw_values = factor.compute(symbols, t_date, lookback, self._feed)
            except Exception:
                continue
            if not raw_values:
                continue

            neutralized = Neutralizer.winsorize(raw_values, 0.01)

            for period in config.forward_periods[:1]:
                fwd_returns = self._get_forward_returns(
                    list(neutralized.keys()), t_date, t_date, period)
                if len(fwd_returns) < config.min_stocks_per_period:
                    continue

                ic = self._calc_ic(neutralized, fwd_returns)
                ic_snapshots.append(ic)

                gr = self._calc_group_returns(neutralized, fwd_returns,
                                              config.n_groups)
                group_results.append(gr)

                fm = self._calc_fama_macbeth(neutralized, fwd_returns)
                fm_results.append(fm)

            factor_value_history.append(neutralized)

        if not ic_snapshots:
            return report

        # ── IC 汇总 ──
        ic_arr = np.array([s.rank_ic for s in ic_snapshots])
        report.rank_ic_mean = float(np.mean(ic_arr))
        report.rank_ic_std = float(np.std(ic_arr, ddof=1))
        report.ic_mean = float(np.mean([s.ic for s in ic_snapshots]))
        report.ic_std = float(np.std([s.ic for s in ic_snapshots], ddof=1))
        report.ic_ir = (report.rank_ic_mean / report.rank_ic_std
                        if report.rank_ic_std > 1e-10 else 0.0)
        report.ic_positive_ratio = float(np.mean(ic_arr > 0))
        report.n_periods = len(ic_snapshots)
        report.avg_n_stocks = int(np.mean([s.n for s in ic_snapshots]))

        # ── 分组汇总 ──
        if group_results:
            report.group_mean_returns = [
                float(np.mean([g.group_means[i] for g in group_results]))
                for i in range(config.n_groups)
            ]
            gr_spreads = [g.long_short_spread for g in group_results]
            report.long_short_spread = float(np.mean(gr_spreads))
            report.long_short_t_stat = float(np.mean(
                [g.long_short_t_stat for g in group_results]))
            report.long_short_p_value = float(np.mean(
                [g.long_short_p_value for g in group_results]))
            report.monotonicity_score = float(np.mean(
                [g.monotonicity_score for g in group_results]))

        # ── FM 汇总（Newey-West HAC）──
        if fm_results:
            fm_betas = [f.beta_mean for f in fm_results]
            report.fm_beta_mean = float(np.mean(fm_betas))
            fm_beta_arr = np.array(fm_betas)

            n = len(fm_beta_arr)
            nw_var = np.var(fm_beta_arr, ddof=1) / n
            lag = max(1, int(n ** 0.25))
            for l in range(1, min(lag + 1, n)):
                gamma = np.mean(fm_beta_arr[l:] * fm_beta_arr[:-l]) * (n / (n - l))
                nw_var += 2 * (1 - l / (lag + 1)) * gamma / n
            se_nw = float(np.sqrt(max(nw_var, 1e-10)))
            report.fm_beta_t_stat = report.fm_beta_mean / se_nw if se_nw > 1e-10 else 0.0
            report.fm_beta_p_value = float(
                2 * (1 - t_dist.cdf(abs(report.fm_beta_t_stat), df=n - 1))
            )

        # ── 衰减 ──
        report.ic_decay = self._calc_ic_decay(factor, symbols, all_dates, config)
        report.decay_half_life = self._calc_half_life(report.ic_decay)

        # ── 换手率 ──
        if len(factor_value_history) > 1:
            to = self._calc_turnover(factor_value_history)
            report.factor_turnover = to["total"]
            report.top_quarter_turnover = to["top_q"]

        # ── 结论 ──
        report.verdict = self._verdict(report)

        return report

    def run_batch(self, factor_names: list[str], symbols: list[str],
                  start: date, end: date) -> dict[str, FactorEvaluationReport]:
        """批量评价多个因子"""
        from .registry import FactorRegistry
        results = {}
        for name in factor_names:
            factor_cls = FactorRegistry.get(name)
            f = factor_cls()
            results[name] = self.run(f, symbols, start, end)
        return results

    def rolling_evaluate(self, factor: Any, symbols: list[str],
                         window: int = 756, step: int = 60,
                         start: date = date(2020, 1, 1),
                         end: date = date(2020, 12, 31)
                         ) -> list[FactorEvaluationReport]:
        """滚动窗口评价"""
        from datetime import timedelta
        reports = []
        cur = start
        while cur + timedelta(days=window) <= end:
            win_end = cur + timedelta(days=window)
            report = self.run(factor, symbols, cur, win_end)
            reports.append(report)
            cur += timedelta(days=step)
        return reports

    # ── 内部方法 ──

    @staticmethod
    def _calc_ic(factor_values: dict[str, float],
                 forward_returns: dict[str, float]) -> ICSnapshot:
        symbols = list(factor_values.keys() & forward_returns.keys())
        if len(symbols) < 5:
            return ICSnapshot(ic=0, rank_ic=0, n=0, p_value=1.0)
        f = np.array([factor_values[s] for s in symbols])
        r = np.array([forward_returns[s] for s in symbols])

        ic = 0.0
        if np.std(f) > 1e-10 and np.std(r) > 1e-10:
            ic = float(np.corrcoef(f, r)[0, 1])
        rank_ic_val, p_val = spearmanr(f, r)
        rank_ic_val = float(rank_ic_val) if not np.isnan(rank_ic_val) else 0.0
        sign_acc = float(np.mean(np.sign(f) == np.sign(r)))
        return ICSnapshot(ic=ic, rank_ic=rank_ic_val,
                          p_value=float(p_val), n=len(symbols),
                          sign_accuracy=sign_acc)

    @staticmethod
    def _calc_group_returns(factor_values: dict, forward_returns: dict,
                            n_groups: int = 5) -> GroupReturnResult:
        symbols = list(factor_values.keys() & forward_returns.keys())
        if len(symbols) < n_groups * 5:
            return GroupReturnResult()
        f_vals = np.array([factor_values[s] for s in symbols])
        r_vals = np.array([forward_returns[s] for s in symbols])

        quantiles = np.percentile(f_vals, np.linspace(0, 100, n_groups + 1)[1:-1])
        labels = np.digitize(f_vals, bins=quantiles)
        group_means = [float(np.mean(r_vals[labels == i]))
                       for i in range(n_groups)]

        monotonicity = EvaluationEngine._calc_monotonicity(group_means)

        q5_idx = labels == n_groups - 1
        q1_idx = labels == 0
        spread = float(np.mean(r_vals[q5_idx]) - np.mean(r_vals[q1_idx]))
        t_stat, p_value = ttest_ind(r_vals[q5_idx], r_vals[q1_idx],
                                     equal_var=False)

        return GroupReturnResult(
            group_means=group_means,
            long_short_spread=spread,
            long_short_t_stat=float(t_stat),
            long_short_p_value=float(p_value),
            monotonicity_score=monotonicity,
        )

    @staticmethod
    def _calc_monotonicity(group_means: list[float]) -> float:
        if len(group_means) < 2:
            return 0.0
        diffs = np.diff(group_means)
        return float(np.mean(np.sign(diffs) == np.sign(np.median(diffs))))

    @staticmethod
    def _calc_fama_macbeth(factor_values: dict, forward_returns: dict,
                           add_controls: bool = False,
                           control_exposures: dict | None = None
                           ) -> FamaMacBethResult:
        symbols = list(factor_values.keys() & forward_returns.keys())
        if len(symbols) < 10:
            return FamaMacBethResult()

        f = np.array([factor_values[s] for s in symbols])
        r = np.array([forward_returns[s] for s in symbols])

        X = np.column_stack([np.ones(len(symbols)), f])
        beta = np.linalg.lstsq(X, r, rcond=None)[0]
        beta_f = float(beta[1])

        return FamaMacBethResult(beta_mean=beta_f, se=0.0,
                                 t_stat=0.0, p_value=1.0)

    def _calc_ic_decay(self, factor: Any, symbols: list[str],
                       dates: list[date],
                       config: EvalConfig) -> list[float]:
        if len(dates) < 10:
            return [0.0, 0.0, 0.0, 0.0]
        sample_dates = dates[max(len(dates) // 5 * 4, 1):]
        decay_results: list[list[float]] = [[], [], [], []]

        for t_date in sample_dates:
            try:
                fv = factor.compute(symbols, t_date,
                                    factor.meta.params.get("lookback", 60),
                                    self._feed)
            except Exception:
                continue
            for pi, period in enumerate(config.forward_periods):
                fwd = self._get_forward_returns(list(fv.keys()),
                                                t_date, t_date, period)
                ic = self._calc_ic(fv, fwd)
                if ic.n > 0:
                    decay_results[pi].append(ic.rank_ic)

        return [
            float(np.mean(v)) if v else 0.0
            for v in decay_results
        ]

    @staticmethod
    def _calc_half_life(decay_curve: list[float]) -> int:
        if not decay_curve or decay_curve[0] <= 0:
            return -1
        half = decay_curve[0] / 2
        periods = [1, 5, 20, 60]
        if decay_curve[-1] > half:
            return 60
        for i in range(len(decay_curve) - 1):
            if decay_curve[i] >= half >= decay_curve[i + 1]:
                if decay_curve[i] - decay_curve[i + 1] > 1e-10:
                    ratio = (decay_curve[i] - half) / (decay_curve[i] - decay_curve[i + 1])
                    return int(periods[i] + ratio * (periods[i + 1] - periods[i]))
        return -1

    @staticmethod
    def _calc_turnover(factor_value_history: list[dict[str, float]]) -> dict[str, float]:
        if len(factor_value_history) < 2:
            return {"total": 0.0, "top_q": 0.0}
        positions = []
        for fv in factor_value_history:
            sorted_symbols = sorted(fv.keys(), key=lambda s: fv[s], reverse=True)
            positions.append({s: i for i, s in enumerate(sorted_symbols)})

        changes = []
        top_changes = []
        n = len(positions[0]) if positions else 1
        for i in range(1, len(positions)):
            prev = positions[i - 1]
            curr = positions[i]
            common = prev.keys() & curr.keys()
            abs_changes = [abs(curr[s] - prev[s]) for s in common]
            change = np.mean(abs_changes) / max(n - 1, 1)
            changes.append(float(change))
            top_n = max(1, n // 4)
            top_symbols = set(sorted(prev.keys(), key=lambda s: prev[s])[:top_n])
            top_curr = set(sorted(curr.keys(), key=lambda s: curr[s])[:top_n])
            overlap = len(top_symbols & top_curr)
            top_changes.append(1.0 - overlap / top_n)

        return {
            "total": float(np.mean(changes)) if changes else 0.0,
            "top_q": float(np.mean(top_changes)) if top_changes else 0.0,
        }

    @staticmethod
    def _verdict(report: FactorEvaluationReport) -> str:
        thresholds = EvalConfig().thresholds

        if (abs(report.rank_ic_mean) >= thresholds["strong"]["rank_ic"]
            and report.ic_ir >= thresholds["strong"]["ic_ir"]
            and abs(report.long_short_t_stat) >= thresholds["strong"]["spread_t"]
            and report.monotonicity_score >= thresholds["strong"]["monotonicity"]
                and report.factor_turnover <= thresholds["strong"]["turnover"]):
            return "strong"

        if (abs(report.rank_ic_mean) >= thresholds["usable"]["rank_ic"]
            and report.ic_ir >= thresholds["usable"]["ic_ir"]
                and report.factor_turnover <= thresholds["usable"]["turnover"]):
            return "usable"

        if (abs(report.rank_ic_mean) >= thresholds["weak"]["rank_ic"]
                and report.factor_turnover <= thresholds["weak"]["turnover"]):
            return "weak"

        return "noise"

    def _generate_eval_dates(self, start: date, end: date,
                             step_days: int = 21) -> list[date]:
        from datetime import timedelta
        dates = []
        cur = start
        while cur <= end:
            dates.append(cur)
            cur += timedelta(days=step_days)
        return dates

    def _get_forward_returns(self, symbols: list[str],
                             from_date: date, to_date: date,
                             period: int) -> dict[str, float]:
        if hasattr(self._feed, 'get_forward_returns'):
            result = self._feed.get_forward_returns(symbols, from_date, to_date)
            if result:
                return result
        try:
            data = self._feed.get_factor_input(symbols, to_date, period)
            if isinstance(data, dict):
                return data
        except (AttributeError, NotImplementedError):
            pass
        return {}


def demo_neutralizer():
    fv = {"A": 1.0, "B": 2.0, "C": 1.5, "D": 0.5}
    industry = {"A": "tech", "B": "tech", "C": "health", "D": "health"}
    result = Neutralizer.industry_neutralize(fv, industry)
    assert abs(result["A"] + result["B"]) < 1e-10
    print("[neutralizer] ✅ 行业中性化通过")
    w = Neutralizer.winsorize(fv)
    assert len(w) == 4
    print("[neutralizer] ✅ winsorize 通过")


def demo_evaluation():
    import sys
    sys.path.insert(0, 'backend/..')
    from datetime import date
    from backend.core.factor.factor import Factor
    from backend.core.factor.models import FactorMeta
    from backend.core.factor.registry import FactorRegistry
    from backend.core.factor.config import EvalConfig

    class DummyFeed:
        def get_forward_returns(self, symbols, from_date, to_date):
            return {s: 0.01 + i * 0.0001 for i, s in enumerate(symbols)}
        def get_factor_input(self, symbols, as_of, lookback):
            return {s: 1.0 for s in symbols}

    class TestF(Factor):
        meta = FactorMeta(name="test_f", display_name="测试", category="risk",
                          domain="test", description="测试", direction=1)
        def compute(self, symbols, as_of, lookback, data):
            return {s: 0.5 + i * 0.001 for i, s in enumerate(symbols)}

    symbols_30 = [f"S{i:03d}" for i in range(30)]
    FactorRegistry.clear()
    FactorRegistry.register(TestF, TestF.meta)
    config = EvalConfig(min_stocks_per_period=5)
    ee = EvaluationEngine(DummyFeed(), config)
    report = ee.run(TestF(), symbols_30,
                    date(2023, 1, 1), date(2023, 6, 30))
    assert report.n_periods > 0
    assert report.factor_name == "test_f"
    print(f"[evaluation] ✅ 评价引擎通过: {report.n_periods} 期, verdict={report.verdict}")


if __name__ == "__main__":
    demo_neutralizer()
    demo_evaluation()
