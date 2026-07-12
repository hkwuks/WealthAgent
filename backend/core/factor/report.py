"""因子报告生成器"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from .models import FactorEvaluationReport


class FactorReport:
    """因子报告生成器"""

    def to_markdown(self, report: FactorEvaluationReport) -> str:
        """生成 Markdown 报告"""
        lines = [
            f"# 因子评价报告：{report.factor_name}",
            "",
            f"域：{report.domain}  |  类别：{report.category}",
            "",
            "## 基本信息",
            f"- 评价期：{report.evaluation_period[0]} → {report.evaluation_period[1]}"
            f"（{report.n_periods} 期）",
            f"- 平均每期样本数：{report.avg_n_stocks}",
            "",
            "## IC 分析",
            "| 指标 | 值 |",
            "|------|-----|",
            f"| Rank IC 均值 | {report.rank_ic_mean:.4f} |",
            f"| Rank IC 标准差 | {report.rank_ic_std:.4f} |",
            f"| IC_IR | {report.ic_ir:.2f} |",
            f"| IC 正向占比 | {report.ic_positive_ratio:.1%} |",
            "",
        ]

        lines.append("## 分组收益")
        labels = ["Q1(最低)", "Q2", "Q3", "Q4", "Q5(最高)"]
        for i, (lb, ret) in enumerate(zip(labels, report.group_mean_returns)):
            bars = "█" * max(1, int((ret - min(report.group_mean_returns)) /
                                     max(1e-6, max(report.group_mean_returns) -
                                         min(report.group_mean_returns)) * 12))
            lines.append(f"{lb:<10} | {bars:<16} {ret:+.2%}/年")

        lines.extend([
            "─" * 30,
            f"Q5-Q1     | {report.long_short_spread:+.1%}/年  "
            f"[t={report.long_short_t_stat:.2f} p={report.long_short_p_value:.3f}]",
            f"单调性    | {report.monotonicity_score:.2f}",
            "",
        ])

        periods_names = ["D+1", "D+5", "D+20", "D+60"]
        lines.append("## IC 衰减")
        for pn, ic in zip(periods_names, report.ic_decay):
            lines.append(f"  {pn}: {ic:.4f}")
        hl = report.decay_half_life
        lines.append(f"  半衰期：{hl} 天\n" if hl > 0 else "  半衰期：无衰减\n")

        lines.extend([
            "## Fama-MacBeth",
            f"β = {report.fm_beta_mean:.4f}, t = {report.fm_beta_t_stat:.2f}, "
            f"p = {report.fm_beta_p_value:.3f}",
            "",
        ])

        lines.extend([
            "## 换手率",
            f"  总体：{report.factor_turnover:.2f}",
            f"  头部 1/4：{report.top_quarter_turnover:.2f}",
            "",
        ])

        verdict_icon = {"strong": "🟢", "usable": "✅", "weak": "⚠️", "noise": "❌"}
        icon = verdict_icon.get(report.verdict, "❓")
        lines.append(f"## 结论：{icon} {report.verdict}")

        return "\n".join(lines)

    def to_html(self, report: FactorEvaluationReport,
                output_path: str | None = None) -> str:
        """生成 HTML 报告"""
        verdict_colors = {"strong": "#22c55e", "usable": "#3b82f6",
                          "weak": "#f59e0b", "noise": "#ef4444"}
        color = verdict_colors.get(report.verdict, "#6b7280")

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>因子报告: {report.factor_name}</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 40px auto; }}
h1 {{ color: {color}; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background: #f5f5f5; }}
.verdict {{ font-size: 1.2em; font-weight: bold; color: {color}; }}
</style></head><body>
<h1>因子评价报告：{report.factor_name}</h1>
<p>域：{report.domain}  |  类别：{report.category}</p>
<h2>IC 分析</h2>
<table><tr><th>指标</th><th>值</th></tr>
<tr><td>Rank IC 均值</td><td>{report.rank_ic_mean:.4f}</td></tr>
<tr><td>IC_IR</td><td>{report.ic_ir:.2f}</td></tr>
<tr><td>IC 正向占比</td><td>{report.ic_positive_ratio:.1%}</td></tr>
</table>
<h2>分组收益</h2>
<table><tr><th>分组</th><th>年化收益</th></tr>"""
        labels = ["Q1(最低)", "Q2", "Q3", "Q4", "Q5(最高)"]
        for lb, gr in zip(labels, report.group_mean_returns):
            html += f"<tr><td>{lb}</td><td>{gr:+.2%}</td></tr>"
        html += f"""</table>
<p>Q5-Q1: {report.long_short_spread:+.1%}/年
[t={report.long_short_t_stat:.2f}, p={report.long_short_p_value:.3f}]</p>
<h2>结论</h2>
<p class="verdict">{report.verdict}</p>
</body></html>"""

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)
        return html

    def audit_table(self, reports: dict[str, FactorEvaluationReport],
                    style: str = "markdown") -> str | pd.DataFrame:
        """因子全景对比表"""
        rows = []
        for name, r in reports.items():
            rows.append({
                "因子": name, "类别": r.category,
                "Rank IC": f"{r.rank_ic_mean:.4f}",
                "IC_IR": f"{r.ic_ir:.2f}",
                "Spread t": f"{r.long_short_t_stat:.2f}",
                "换手率": f"{r.factor_turnover:.2f}",
                "结论": r.verdict,
            })
        df = pd.DataFrame(rows)
        if style == "dataframe":
            return df
        return df.to_markdown(index=False)


class FactorAudit:
    """因子全景审计"""

    def __init__(self, eval_engine: Any):
        self._engine = eval_engine

    def audit_all(self, domain: str, symbols: list[str],
                  period: tuple[date, date]) -> pd.DataFrame:
        """批量评价指定域所有因子"""
        from .registry import FactorRegistry
        metas = FactorRegistry.list(domain=domain)
        reports = {}
        for meta in metas:
            factor_cls = FactorRegistry.get(meta.name)
            f = factor_cls()
            report = self._engine.run(f, symbols, period[0], period[1])
            reports[meta.name] = report
        rf = FactorReport()
        return rf.audit_table(reports, style="dataframe")
