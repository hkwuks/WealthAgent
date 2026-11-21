"""按 docs/个人量化交易教程.md 第十章的指标表，评估基准与候选组合。

原则（教程第十二章）:
  - 不调参：动量参数一次性写死，不做参数搜索
  - 统一区间/费用/分红再投资口径
  - 必须有样本外区间
输出: reports/benchmark_eval.json + 控制台表格
"""
import difflib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
BENCH_DIR = PROJECT / "data" / "benchmark_nav"
PORT_DIR = PROJECT / "data" / "my_portfolio_nav"
OUT = PROJECT / "reports" / "benchmark_eval.json"

TRADING_DAYS = 244
FEE_BPS = 3  # 单边 0.03%（ETF 佣金+冲击的保守估计）


def load(dirpath: Path, code: str) -> pd.Series | None:
    f = dirpath / f"{code}.json"
    if not f.exists():
        return None
    rows = json.loads(f.read_text(encoding="utf-8"))
    if not rows:
        return None
    pairs = {}
    for r in rows:
        # 优先 adj_nav（累计净值，含分红再投资）；unit_nav 不含分红，会系统性低估收益
        v = r.get("nav")
        if v is None:
            v = r.get("adj_nav")
        if v is None:
            v = r.get("unit_nav")
        if v is not None and float(v) > 0:
            pairs[r["date"]] = float(v)
    s = pd.Series(pairs, dtype="float64").sort_index()
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")]


def to_ret(s: pd.Series) -> pd.Series:
    return s.pct_change().dropna()


def metrics(ret: pd.Series, label: str = "") -> dict:
    if len(ret) < 20:
        return {}
    nav = (1 + ret).cumprod()
    years = len(ret) / TRADING_DAYS
    cagr = nav.iloc[-1] ** (1 / years) - 1
    vol = ret.std() * np.sqrt(TRADING_DAYS)
    dd = (nav / nav.cummax() - 1).min()
    sharpe = (cagr - 0.015) / vol if vol > 0 else np.nan
    calmar = cagr / abs(dd) if dd < 0 else np.nan
    yearly = (nav.resample("YE").last() / nav.resample("YE").last().shift(1) - 1).dropna()
    win_years = (yearly > 0).mean() if len(yearly) else np.nan
    return {
        "label": label,
        "years": round(years, 2),
        "cagr": round(cagr, 4),
        "vol": round(vol, 4),
        "max_dd": round(dd, 4),
        "sharpe": round(sharpe, 3),
        "calmar": round(calmar, 3),
        "win_year_rate": round(win_years, 3),
        "worst_year": round(yearly.min(), 4) if len(yearly) else None,
        "best_year": round(yearly.max(), 4) if len(yearly) else None,
        "total_ret": round(nav.iloc[-1] - 1, 4),
    }


def bench(code, name):
    s = load(BENCH_DIR, code)
    return (name, s) if s is not None else (None, None)


def build_portfolio_series(weights: dict, sources: dict) -> pd.Series | None:
    """weights: code -> weight; sources: code -> nav Series. 日度再平衡到目标权重。"""
    frame = pd.DataFrame({c: sources[c] for c in weights if c in sources})
    if frame.empty:
        return None
    frame = frame.ffill().dropna()
    rets = frame.pct_change().dropna()
    w = np.array([weights[c] for c in frame.columns])
    w = w / w.sum()
    port = (rets * w).sum(axis=1) - FEE_BPS / 1e4 * 12 / 244  # 月度再平衡的年化摩擦按日摊
    return port


def momentum_rotation(pool: dict, lookback=25, top_n=2, hold=20, cost_bps=FEE_BPS):
    """固定参数动量轮动（教程 §5.1 流程）。

    - 信号在 T 日收盘后生成，持仓从 T+1 日收益起算（无未来函数）
    - 评分 = 区间收益 × R²；只买动量为正者，否则空仓
    - 换仓成本按双边计
    """
    frame = pd.DataFrame(pool).ffill()
    rets = frame.pct_change()
    idx = frame.index
    out = pd.Series(0.0, index=idx)
    held: list[str] = []
    last_rebal = -10**9
    cost = cost_bps / 1e4

    for i, _ in enumerate(idx):
        if i < lookback + 1:
            continue
        if i - last_rebal >= hold:
            scores = {}
            for c in frame.columns:
                w = frame[c].iloc[i - lookback : i + 1].dropna()
                if len(w) < lookback + 1:
                    continue
                mom = w.iloc[-1] / w.iloc[0] - 1
                logr = np.log(w / w.shift(1)).dropna()
                if len(logr) < 3:
                    continue
                r2 = np.corrcoef(logr.values, np.arange(len(logr)))[0, 1] ** 2
                scores[c] = mom * r2
            ranked = sorted(scores.items(), key=lambda x: -x[1])
            new_held = [c for c, sc in ranked[:top_n] if sc > 0]
            if set(new_held) != set(held):
                out.iloc[i] -= cost * 2
            held = new_held
            last_rebal = i
        # 信号用 i 日收盘算出，只能吃到 i+1 日的收益（否则是未来函数）
        if held and i + 1 < len(idx):
            out.iloc[i + 1] = rets.iloc[i + 1][held].mean()
    return out


def resolve_holdings(holdings: list[dict], idx: dict) -> tuple[dict, list, dict]:
    """持仓名 -> 净值代码。

    显式覆盖优先于模糊匹配，否则会静默用错标的（如场内黄金 ETF 被当成联接基金）。
    """
    EXPLICIT = {
        "黄金ETF(场内)": "518880",           # 场内实物黄金，净值源在 benchmark_nav
        "中银增利债券A": "163806",           # 官方名；_index 里记成"中银稳健增利债券A"
        "中银稳健增利债券A": "163806",
    }
    def norm(s: str) -> str:
        s = re.sub(r"[（）()]", "", s)
        for suffix in ("股票", "混合", "债券", "指数", "联接", "发起", "基金"):
            s = s.replace(suffix, "")
        return s
    cands = {k: norm(v["name"]) for k, v in idx.items()}
    code_by_name: dict[str, str] = {}
    missing: list[str] = []
    proxies: dict[str, str] = {}
    for h in holdings:
        nm = h["fund_name"]
        if nm in EXPLICIT:
            code_by_name[nm] = EXPLICIT[nm]
            continue
        n = norm(nm)
        # 先查子串：持仓名通常比 _index 的简写更长
        sub_hits = [k for k, v in cands.items() if v and v in n]
        if len(sub_hits) == 1:
            code_by_name[nm] = sub_hits[0]
            if cands[sub_hits[0]] != n:
                proxies[nm] = f"{sub_hits[0]} ({idx[sub_hits[0]]['name']})"
            continue
        best = difflib.get_close_matches(n, list(cands.values()), n=1, cutoff=0.5)
        if not best:
            missing.append(nm)
            continue
        c = next(k for k, v in cands.items() if v == best[0])
        if cands[c] != n:
            proxies[nm] = f"{c} ({idx[c]['name']})"
        code_by_name[nm] = c
    return code_by_name, missing, proxies


def main():
    names = {
        "510300": "B1 沪深300ETF",
        "515080": "B2 中证红利ETF",
        "512890": "B3 红利低波ETF",
        "515650": "B4 红利质量ETF",
        "563020": "B5 自由现金流ETF",
        "511260": "10年国债ETF",
        "518880": "黄金ETF",
        "513100": "纳指ETF",
        "159915": "创业板ETF",
        "510500": "中证500ETF",
    }
    alls = {c: load(BENCH_DIR, c) for c in names}
    alls = {c: s for c, s in alls.items() if s is not None}

    report = {"benchmarks": {}, "splits": {}, "combos": {}, "rotation": {}}
    start = "2020-01-02"

    print("=" * 84)
    print(f"基准指标（{start} ~ 各基金最新日，日频，含分红再投资的累计净值）")
    print("=" * 84)
    print(f"{'':22} {'年化':>7} {'波动':>7} {'回撤':>8} {'Sharpe':>7} {'Calmar':>7} {'年胜率':>7}")
    for c, nm in names.items():
        s = alls.get(c)
        if s is None:
            continue
        s2 = s[s.index >= start]
        if len(s2) < 250:
            continue
        m = metrics(to_ret(s2), nm)
        report["benchmarks"][c] = m
        print(
            f"{nm:22} {m['cagr']*100:>6.2f}% {m['vol']*100:>6.2f}% "
            f"{m['max_dd']*100:>7.1f}% {m['sharpe']:>7.2f} {m['calmar']:>7.2f} "
            f"{m['win_year_rate']*100:>6.0f}%"
        )

    # ── 样本内/样本外切分（教程 §2.2 / §10）──────────────────────────
    print("\n" + "=" * 84)
    print("样本切分：2020-2023（开发期） vs 2024-2026（样本外）")
    print("=" * 84)
    print(f"{'':22} {'20-23年化':>10} {'20-23回撤':>10} {'24-26年化':>10} {'24-26回撤':>10}")
    for c, nm in names.items():
        s = alls.get(c)
        if s is None:
            continue
        a = s[(s.index >= "2020-01-02") & (s.index < "2024-01-01")]
        b = s[s.index >= "2024-01-01"]
        if len(a) < 250 or len(b) < 250:
            continue
        ma, mb = metrics(to_ret(a)), metrics(to_ret(b))
        report["splits"][c] = {"in": ma, "out": mb}
        print(
            f"{nm:22} {ma['cagr']*100:>9.2f}% {ma['max_dd']*100:>9.1f}% "
            f"{mb['cagr']*100:>9.2f}% {mb['max_dd']*100:>9.1f}%"
        )

    # ── 组合 ───────────────────────────────────────────────────────
    print("\n" + "=" * 84)
    print("候选组合（2020-01-02 起，日度再平衡）")
    print("=" * 84)
    combos = {
        "60%红利低波+40%国债": {"512890": 0.60, "511260": 0.40},
        "50%红利低波+40%国债+10%黄金": {"512890": 0.50, "511260": 0.40, "518880": 0.10},
        "40%红利低波+30%国债+20%纳指+10%黄金": {
            "512890": 0.40, "511260": 0.30, "513100": 0.20, "518880": 0.10,
        },
        "100%沪深300（对照组）": {"510300": 1.0},
        "100%红利低波（对照组）": {"512890": 1.0},
    }
    print(f"{'':38} {'年化':>7} {'波动':>7} {'回撤':>8} {'Sharpe':>7} {'Calmar':>7}")
    for nm, w in combos.items():
        r = build_portfolio_series(w, alls)
        if r is None:
            continue
        r = r[r.index >= start]
        m = metrics(r, nm)
        report["combos"][nm] = m
        print(
            f"{nm:38} {m['cagr']*100:>6.2f}% {m['vol']*100:>6.2f}% "
            f"{m['max_dd']*100:>7.1f}% {m['sharpe']:>7.2f} {m['calmar']:>7.2f}"
        )

    # ── 动量轮动（固定参数，事前写死）────────────────────────────────
    print("\n" + "=" * 84)
    print("动量轮动（固定参数：25日动量×R²，Top2，20日持有，无参数搜索）")
    print("=" * 84)
    pool_codes = ["510300", "510500", "159915", "513100", "518880", "512890"]
    pool = {c: alls[c] for c in pool_codes if c in alls}
    rot = momentum_rotation(pool)
    rot = rot[rot.index >= start]
    m = metrics(rot, "动量轮动")
    report["rotation"]["pool_6"] = m
    print(f"{'动量轮动(6池)':38} {m['cagr']*100:>6.2f}% {m['vol']*100:>6.2f}% "
          f"{m['max_dd']*100:>7.1f}% {m['sharpe']:>7.2f} {m['calmar']:>7.2f}")
    a = rot[rot.index < "2024-01-01"]; b = rot[rot.index >= "2024-01-01"]
    report["rotation"]["split"] = {"in": metrics(a), "out": metrics(b)}
    print(f"  ├ 2020-2023 年化 {metrics(a)['cagr']*100:>6.2f}%  回撤 {metrics(a)['max_dd']*100:>6.1f}%")
    print(f"  └ 2024-2026 年化 {metrics(b)['cagr']*100:>6.2f}%  回撤 {metrics(b)['max_dd']*100:>6.1f}%")

    # ── 用户实际持仓 ────────────────────────────────────────────────
    print("\n" + "=" * 84)
    print("你的实际 41 只持仓（按各基金净值历史加权模拟）")
    print("=" * 84)
    port = json.loads((PROJECT / "data" / "my_portfolio.json").read_text(encoding="utf-8"))
    idx = json.loads((PORT_DIR / "_index.json").read_text(encoding="utf-8"))
    code, missing, proxies = resolve_holdings(port["holdings"], idx)

    weights: dict[str, float] = {}
    for h in port["holdings"]:
        c = code.get(h["fund_name"])
        if c:
            weights[c] = weights.get(c, 0) + h["amount"]
    tot = sum(weights.values())
    weights = {c: v / tot for c, v in weights.items()}
    src = {c: load(PORT_DIR, c) if c != "518880" else load(BENCH_DIR, c) for c in weights}
    src = {c: s for c, s in src.items() if s is not None}
    r = build_portfolio_series(weights, src)
    if r is not None:
        r = r[r.index >= start]
        m = metrics(r, "实际持仓")
        report["actual"] = m
        report["actual_covered_pct"] = round(tot / port["meta"]["total_asset"] * 100, 2)
        report["actual_missing"] = missing
        report["actual_proxies"] = proxies
        print(f"{'你的41只持仓(按真实权重还原)':38} {m['cagr']*100:>6.2f}% {m['vol']*100:>6.2f}% "
              f"{m['max_dd']*100:>7.1f}% {m['sharpe']:>7.2f} {m['calmar']:>7.2f}")
        print(f"  净值覆盖: {tot:,.2f} / {port['meta']['total_asset']:,.2f} "
              f"= {tot/port['meta']['total_asset']*100:.1f}%")
        if proxies:
            print(f"  份额借用（同基金 A/C 级用同一净值）: {len(proxies)} 处")
            for k, v in proxies.items():
                print(f"    {k} -> {v}")
        if missing:
            print(f"  无净值、已剔除: {len(missing)} 只")
            for x in missing:
                print(f"    - {x}")
        sp = report["actual_split"] = {}
        a = r[r.index < "2024-01-01"]; b = r[r.index >= "2024-01-01"]
        if len(a) > 200 and len(b) > 200:
            print(f"  ├ 2020-2023 年化 {metrics(a)['cagr']*100:>6.2f}%  回撤 {metrics(a)['max_dd']*100:>6.1f}%")
            print(f"  └ 2024-2026 年化 {metrics(b)['cagr']*100:>6.2f}%  回撤 {metrics(b)['max_dd']*100:>6.1f}%")
            sp["in"] = metrics(a); sp["out"] = metrics(b)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
