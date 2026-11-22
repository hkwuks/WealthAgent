"""多因子选基策略 — 对接因子分析引擎，动态IC权重"""
from datetime import date, timedelta
from typing import Optional

from loguru import logger

from ..base import FundStrategyBase, StrategyRegistry
from ...core.enums import SignalType, Direction, FundType
from ...core.models import FundSignal, Portfolio, InformationSet
from ...factors.nav_feed import feed_from_storage

# ── verdict 等级顺序 ──
_VERDICT_ORDER = {"strong": 0, "usable": 1, "weak": 2, "noise": 3}


def _verdict_ge(v: str, min_v: str) -> bool:
    """判断因子等级 >= 最低要求"""
    return _VERDICT_ORDER.get(v, 3) <= _VERDICT_ORDER.get(min_v, 3)


class MultiFactorSelection(FundStrategyBase):
    """多因子选基策略: 基于因子分析引擎的动态多因子评分"""
    strategy_name = "multi_factor"
    strategy_type = "selection"
    description = "基于因子评价引擎(IC_IR加权)的动态多因子评分"
    default_params = {
        "lookback_years": 3,
        "min_history_years": 1,
        "top_n": 5,
        "corr_threshold": 0.7,
        "weight_method": "ic_weighted",  # ic_weighted/equal/significant_only
        "custom_weights": None,
        "min_factor_verdict": "usable",
    }
    param_ranges = {
        "lookback_years": {"min": 1, "max": 5},
        "top_n": {"min": 3, "max": 20},
        "min_factor_verdict": {"options": [{"label": "可用", "value": "usable"}, {"label": "强信号", "value": "strong"}]},
        "weight_method": {"options": [{"label": "IC加权", "value": "ic_weighted"}, {"label": "等权", "value": "equal"}]},
        "min_history_years": {"min": 0.5, "max": 3},
    }
    formula_description = "基于IC_IR加权动态权重的多因子评分选基策略"
    applicable_fund_types = ["stock", "hybrid", "bond", "index"]
    min_history_days = 365

    def on_evaluate(self, portfolio: Optional[Portfolio],
                    info_set: Optional[InformationSet]) -> list[FundSignal]:
        return []

    def screen(self, fund_type: str = "stock", top_n: int = 10,
               params: Optional[dict] = None,
               fund_data: Optional[list] = None,
               factors: Optional[list] = None) -> dict:
        """筛选基金 — 使用因子引擎（真实 NAV 前瞻收益评价）

        Args:
            fund_type / top_n / params: 同前
            fund_data: 可选。调用方预装载的候选基金截面（每项含 nav_values + meta 字段）。
                注入后跳过 storage 读取（消除全库未来读取）；不传则回退 storage 全库读取（现有行为）。
            factors: 仅注入路径使用。调用方已按 as-of 日期算好的 active 因子列表
                [(factor, report), ...]；为空/缺省时按 legacy 语义回退为全部注册基金因子等权打分
                （storage-free，不做因子引擎前瞻评价）。
        """
        from ...data.storage import get_all_fund_codes

        if params:
            self.params.update(params)

        top_n = self.params.get("top_n", top_n)

        # ── 注入路径：候选截面 + 因子集均由调用方提供，不触碰 storage ──
        if fund_data is not None:
            pre = []
            for item in fund_data:
                code = item.get("fund_code")
                if not code:
                    continue
                ft = item.get("fund_type")
                if ft and ft != fund_type and fund_type != "all":
                    continue
                navs = [{"nav": float(v)} for v in (item.get("nav_values") or [])
                        if v is not None and v > 0]
                pre.append((code, item, navs))

            factor_list = factors if factors is not None else []
            if not factor_list:
                factor_list = self._registered_fund_factors()

            evaluated = [(f, r) for f, r in factor_list if r is not None]
            weights = self.params.get("custom_weights")
            if weights is None:
                if evaluated:
                    weights = self._compute_weights(evaluated)
                elif factor_list:
                    weights = {f.meta.name: 1.0 / len(factor_list)
                               for f, _ in factor_list}
                else:
                    # 连因子都不可注册：空结果
                    return {"strategy": self.strategy_name, "fund_type": fund_type,
                            "top_n": top_n, "rankings": [], "total_candidates": 0}

            fund_scores = self._score_funds(fund_type, factor_list, weights,
                                            preloaded=pre)
            return self._finalize_screen(fund_type, top_n, fund_scores,
                                         fallback="equal_weight" if not evaluated else None)

        candidates = get_all_fund_codes()
        if not candidates:
            return {"strategy": self.strategy_name, "fund_type": fund_type,
                    "top_n": top_n, "rankings": [], "total_candidates": 0}

        # 1. 获取因子评价结果
        active = self._load_active_factors(candidates)
        if not active:
            # 无通过显著性评价的因子：诚实降级为等权多因子（非规模排序）
            logger.warning("没有通过评价的可用因子，回退等权多因子评分")
            return self._fallback_screen(fund_type, top_n)

        # 2. 动态权重
        weights = self.params.get("custom_weights")
        if weights is None:
            weights = self._compute_weights(active)

        # 3. 计算每只基金评分
        fund_scores = self._score_funds(fund_type, active, weights)

        return self._finalize_screen(fund_type, top_n, fund_scores)

    def _finalize_screen(self, fund_type: str, top_n: int,
                         fund_scores: list[dict], *,
                         fallback: Optional[str] = None) -> dict:
        """Z-score 标准化 + 排序 + 结果组装（legacy 收尾逻辑，注入/回退共用）"""
        if not fund_scores:
            return {"strategy": self.strategy_name, "fund_type": fund_type,
                    "top_n": top_n, "rankings": [], "total_candidates": 0}

        if len(fund_scores) > 1:
            scores = [fs["total_score"] for fs in fund_scores]
            mean = __import__('numpy').mean(scores)
            std = max(__import__('numpy').std(scores, ddof=1), 1e-8)
            for fs in fund_scores:
                fs["total_score"] = (fs["total_score"] - mean) / std

        fund_scores.sort(key=lambda x: x["total_score"], reverse=True)

        rankings = []
        for i, fs in enumerate(fund_scores[:top_n]):
            meta_name = fs["meta"].get("fund_name") if fs["meta"] else ""
            rankings.append({
                "rank": i + 1,
                "fund_code": fs["fund_code"],
                "fund_name": fs.get("fund_name") or meta_name,
                "total_score": round(fs["total_score"], 4),
                "factors": fs["factors"],
            })

        self._state["last_rankings"] = fund_scores[:top_n]

        result = {
            "strategy": self.strategy_name,
            "fund_type": fund_type,
            "top_n": top_n,
            "total_candidates": len(fund_scores),
            "rankings": rankings,
        }
        if fallback:
            result["fallback"] = fallback
        return result

    def _score_funds(self, fund_type: str, factors: list,
                     weights: dict[str, float],
                     preloaded: Optional[list] = None,
                     as_of: Optional[date] = None) -> list[dict]:
        """对候选基金计算多因子总分（共享给 active / fallback / 注入 三条路径）

        preloaded: 可选 [(code, item, navs)] — 注入路径跳过 storage 读取。
        as_of: 计算基准日；注入路径必须给，否则会用到未来数据。
        """
        from ...data.storage import get_all_fund_codes, get_fund_meta, get_nav_history

        as_of = as_of or date.today()

        # 基金名兜底：fund_metadata 表可能为空，从 funds.json 解析
        names = {}
        try:
            import json, os
            # multi_factor.py → selection → strategy → fund_quant → backend → 项目根
            fp = os.path.abspath(os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "..",
                "data", "backend", "funds.json"))
            if os.path.exists(fp):
                for f in json.load(open(fp, encoding="utf-8")) or []:
                    if f.get("fund_code"):
                        names[f["fund_code"]] = f.get("fund_name", "")
        except Exception:
            pass

        fund_scores = []
        if preloaded is not None:
            sources = [(code, item, navs) for code, item, navs in preloaded]
        else:
            sources = []
            for code in get_all_fund_codes() or []:
                meta = get_fund_meta(code)
                if meta and meta.get("fund_type") != fund_type and fund_type != "all":
                    continue
                sources.append((code, meta, get_nav_history(code)))

        for code, meta, navs in sources:
            if len(navs) < 60:
                continue
            if meta and meta.get("fund_type") != fund_type and fund_type != "all":
                continue

            # 走引擎统一计算：_compute_factor_simple 只认 10 个硬编码因子名，
            # 28 个 tech_* 会全部返回 0.0。
            total = 0.0
            factor_values = {}
            feed = feed_from_storage(code, rows=navs)
            if feed is None:
                continue
            for f, report in factors:
                try:
                    meta_f = f.meta
                    raw = f.compute([code], as_of, meta_f.params.get("lookback", 60), feed)
                    val = raw.get(code)
                    if val is None:
                        continue
                    factor_values[meta_f.name] = val
                    w = weights.get(meta_f.name, 0)
                    total += w * val * meta_f.direction
                except Exception:
                    continue

            if factor_values:
                fund_scores.append({
                    "fund_code": code,
                    "fund_name": (meta.get("fund_name") or names.get(code, ""))
                                 if meta else names.get(code, ""),
                    "total_score": total,
                    "factors": {k: round(v, 4) for k, v in factor_values.items()},
                    "meta": meta,
                })
        return fund_scores

    def _registered_fund_factors(self) -> list[tuple]:
        """注册并返回全部基金域因子 (f, None) 对（不读 NAV / storage）"""
        from backend.core.factor import FactorRegistry

        if FactorRegistry.count() == 0:
            try:
                from backend.fund_quant.adapter import FundDomainAdapter
                FundDomainAdapter().register_factors()
            except Exception:
                pass
        return [(FactorRegistry.get(m.name)(), None)
                for m in (FactorRegistry.list(domain="fund") or [])]

    def _load_active_factors(self, symbols: list[str],
                             start: date | None = None,
                             end: date | None = None) -> list[tuple]:
        """加载经过 IC 评价的可用因子（基于真实净值数据）。

        评价用 NavFactorFeed：它同时提供 as_of 截断后的净值序列和真实前瞻收益，
        与离线研究报告（reports/factor_rolling_ic.json）的口径一致。
        早前这里喂的是 _DummyFeed（forward_returns 恒为 0.01），算出的 IC 是噪声。

        返回 [(factor_instance, report)]。
        """
        from backend.core.factor import FactorRegistry, EvaluationEngine, EvalConfig
        from backend.fund_quant.factors import load_all
        from ...data.feed import NavFactorFeed

        load_all()

        if start is None or end is None:
            start = date.today() - timedelta(days=365 * self.params.get("lookback_years", 3))
            end = date.today()

        # forward_periods=[21] 与 feed.horizon 一致（约 1 个月前瞻）
        # min_stocks_per_period=5 适配基金池规模（远小于股票截面）
        feed = NavFactorFeed(horizon=21)
        ee = EvaluationEngine(feed, EvalConfig(
            forward_periods=[21],
            min_stocks_per_period=5,
        ))

        active = []
        for meta in FactorRegistry.list(domain="fund") or []:
            try:
                f = FactorRegistry.get(meta.name)()
                report = ee.run(f, symbols[:max(10, len(symbols))], start, end)
            except Exception:
                continue
            if report.n_periods > 0 and _verdict_ge(report.verdict, self.params.get(
                    "min_factor_verdict", "usable")):
                active.append((f, report))

        return active

    def _compute_weights(self, active_factors: list[tuple],
                         method: str | None = None) -> dict[str, float]:
        """按 EvaluationEngine 的 IC_IR 分权（数据来自 NavFactorFeed 的真实前瞻收益）。

        active_factors: [(factor_instance, FactorEvaluationReport), ...]
        """
        if not active_factors:
            return {}
        method = method or self.params.get("weight_method", "ic_weighted")
        if method == "ic_weighted":
            total_ir = sum(abs(r.ic_ir) for _, r in active_factors)
            if total_ir < 1e-10:
                return {f.meta.name: 1.0 / len(active_factors) for f, _ in active_factors}
            return {f.meta.name: abs(r.ic_ir) / total_ir for f, r in active_factors}
        if method == "significant_only":
            sig = [(f, r) for f, r in active_factors if getattr(r, "fm_beta_p_value", 1.0) < 0.05]
            sig = sig or active_factors
            return {f.meta.name: 1.0 / len(sig) for f, _ in sig}
        return {f.meta.name: 1.0 / len(active_factors) for f, _ in active_factors}

    def _fallback_screen(self, fund_type: str, top_n: int) -> dict:
        """等权多因子回退：无因子通过显著性评价时的诚实降级

        用全部注册因子、等权打分（而非只按规模排序），产出真实的多因子评分。
        """
        from backend.core.factor import FactorRegistry
        from ...data.feed import NavFactorFeed  # noqa: F401 确保注册路径

        # 确保因子已注册
        if FactorRegistry.count() == 0:
            try:
                from backend.fund_quant.adapter import FundDomainAdapter
                FundDomainAdapter().register_factors()
            except Exception:
                pass

        metas = FactorRegistry.list(domain="fund") or []
        if not metas:
            # 连因子都不可用：空结果（不假装按规模排序）
            return self._empty_result(fund_type, top_n)

        all_factors = []
        for meta in metas:
            try:
                all_factors.append((FactorRegistry.get(meta.name)(), None))
            except Exception:
                continue

        weights = {f.meta.name: 1.0 / len(all_factors) for f, _ in all_factors}
        fund_scores = self._score_funds(fund_type, all_factors, weights)
        fund_scores.sort(key=lambda x: x["total_score"], reverse=True)

        rankings = [{
            "rank": i + 1,
            "fund_code": fs["fund_code"],
            "fund_name": fs.get("fund_name") or (fs["meta"].get("fund_name") if fs["meta"] else ""),
            "total_score": round(fs["total_score"], 4),
            "factors": fs["factors"],
        } for i, fs in enumerate(fund_scores[:top_n])]

        return {"strategy": self.strategy_name, "fund_type": fund_type,
                "top_n": top_n, "total_candidates": len(fund_scores),
                "rankings": rankings, "fallback": "equal_weight"}

    @staticmethod
    def _empty_result(fund_type: str, top_n: int) -> dict:
        return {"strategy": "multi_factor", "fund_type": fund_type,
                "top_n": top_n, "rankings": [], "total_candidates": 0}

    def score(self, fund_type: str = "stock",
              params: Optional[dict] = None) -> dict:
        """基金评分"""
        if params:
            self.params.update(params)
        result = self.screen(fund_type=fund_type, top_n=1000)
        return {
            "strategy": self.strategy_name,
            "fund_type": fund_type,
            "scores": {r["fund_code"]: r["total_score"]
                       for r in result.get("rankings", [])},
        }


StrategyRegistry.register(MultiFactorSelection)
