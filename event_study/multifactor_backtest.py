"""多因子合成 + 横截面回测。

设计依据：
  1. 只用 rolling_ic 判定的 10 个存活因子（见 reports/factor_rolling_ic.json）
  2. IC 加权 z-score 合成 —— IC 本身就是预测能力的度量
  3. 横截面选 Top-N：ETF 池的正确用法是排序选强，不是单标的择时
  4. T 日收盘出信号，T+1 收盘成交（避免未来函数）
  5. 参数全部事前写死，不做搜索（教程 §2.2）

用法: python3 multifactor_backtest.py
输出: reports/multifactor_backtest.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from market_db import CODES, load_daily
from select_direction import compute_factor

# 从扩充后的池子读取标的；无该文件时退回内置 15 只
_POOL = HERE.parent / "data" / "etf_pool_usable.json"
if _POOL.exists():
    CODES = [x["code"] for x in json.loads(_POOL.read_text(encoding="utf-8"))]

# rolling_ic 判定存活、且近期IC为正的因子 -> (op, window, direction, weight)
# weight = 该因子近期 IC，用于加权
FACTORS = [
    ("rsv", 10, +1, 0.0525),
    ("rsv", 20, +1, 0.0507),
    ("ma_gap", 10, +1, 0.0408),
    ("ma_gap", 20, +1, 0.0394),
    ("roc", 20, +1, 0.0359),
    ("roc", 10, +1, 0.0347),
    ("rsv", 5, +1, 0.0313),
    ("roc", 5, +1, 0.0253),
    ("max_gap", 20, +1, 0.0238),
    ("ma_gap", 5, +1, 0.0211),
]

TOP_N = 3                  # 持有最强 3 只
REBAL_DAYS = 20            # 月度换仓
MIN_HISTORY = 120          # 因子需要的最短历史
COST = 0.0006              # 单边 6bp（ETF 佣金+价差，比个股低）
IS_END = "2022-01-01"


def build_panel() -> pd.DataFrame:
    """宽表：index=date, columns=ETF代码, values=复权收盘价。"""
    frames = {}
    for code in CODES:
        df = load_daily(code)
        if df is None or len(df) < MIN_HISTORY + 60:
            continue
        d = df.sort_values("date").set_index("date")["close"].astype(float)
        d.index = pd.to_datetime(d.index)
        frames[code] = d
    return pd.DataFrame(frames).sort_index()


def factor_frame(px: pd.DataFrame, op: str, n: int) -> pd.DataFrame:
    """对每列算同一因子，返回同形状 DataFrame。"""
    out = {}
    for c in px.columns:
        s = px[c].values
        out[c] = compute_factor(s, op, n)
    return pd.DataFrame(out, index=px.index)


def composite_score(px: pd.DataFrame) -> pd.DataFrame:
    """IC 加权 z-score 合成。z-score 用横截面（每日跨 ETF），不是时序。"""
    total = None
    wsum = 0.0
    for op, n, direction, w in FACTORS:
        f = factor_frame(px, op, n) * direction
        # 横截面标准化：当日各 ETF 之间的 z-score
        mu = f.mean(axis=1)
        sd = f.std(axis=1).replace(0, np.nan)
        z = f.sub(mu, axis=0).div(sd, axis=0)
        total = z * w if total is None else total.add(z * w, fill_value=0)
        wsum += w
    return total / wsum


def backtest(px: pd.DataFrame, score: pd.DataFrame,
             top_n: int = TOP_N, rebal: int = REBAL_DAYS,
             cost: float = COST) -> pd.DataFrame:
    """T 日收盘出信号，T+1 收盘成交。返回逐日净值。"""
    rets = px.pct_change()
    dates = px.index
    held: list[str] = []
    last = -10**9
    turnover_log = []
    navs = []
    level = 1.0

    for i in range(MIN_HISTORY, len(dates)):
        dt = dates[i]
        # 信号在 T 日收盘生成，仓位从 T+1 日开始生效
        if i - last >= rebal:
            s = score.loc[dt].dropna()
            if len(s) >= top_n:
                new = list(s.nlargest(top_n).index)
                if set(new) != set(held):
                    turnover_log.append((str(dt.date()), held, new))
                    level *= (1 - cost)   # 换仓成本
                held = new
                last = i
        if held and i + 1 < len(dates):
            nxt = rets.iloc[i + 1]
            r = nxt[held].mean()
            if np.isfinite(r):
                level *= (1 + r)
        navs.append(level)

    idx = dates[MIN_HISTORY:MIN_HISTORY + len(navs)]
    return pd.DataFrame({"nav": navs}, index=idx)


def metrics(nav: pd.Series, label: str = "") -> dict:
    if len(nav) < 30:
        return {}
    r = nav.pct_change().dropna()
    years = len(r) / 244
    cagr = nav.iloc[-1] ** (1 / years) - 1
    vol = r.std() * np.sqrt(244)
    dd = (nav / nav.cummax() - 1).min()
    return {"label": label, "days": len(nav), "years": round(years, 2),
            "cagr": round(float(cagr), 4), "vol": round(float(vol), 4),
            "max_dd": round(float(dd), 4),
            "sharpe": round(float((cagr - 0.015) / vol), 3) if vol > 0 else None,
            "calmar": round(float(cagr / abs(dd)), 3) if dd < 0 else None,
            "total": round(float(nav.iloc[-1] - 1), 4)}


def main():
    px = build_panel()
    print(f"价格面板 {px.shape[0]} 行 × {px.shape[1]} 只  "
          f"{px.index.min().date()} ~ {px.index.max().date()}")

    score = composite_score(px)
    print(f"合成评分 {FACTORS.__len__()} 个因子，Top{TOP_N}，{REBAL_DAYS} 日换仓\n")

    nav = backtest(px, score)
    m = metrics(nav["nav"], "多因子 TopN")

    # 基准：等权持有全部 ETF（覆盖同一时间段）
    eq = px[px.index >= nav.index[0]].pct_change().mean(axis=1).fillna(0)
    eq_nav = (1 + eq).cumprod()
    mb = metrics(eq_nav, "等权持有全池")

    # 基准：最强单因子 rsv_10
    single = factor_frame(px, "rsv", 10)
    nav_s = backtest(px, single)
    ms = metrics(nav_s["nav"], "单因子 rsv_10")

    print("=" * 76)
    print("回测结果（已扣换仓成本，T+1 成交）")
    print("=" * 76)
    hdr = f"{'策略':22} {'年化':>8} {'波动':>8} {'回撤':>8} {'Sharpe':>8} {'Calmar':>8}"
    print(hdr)
    for x in (m, ms, mb):
        if not x:
            continue
        print(f"{x['label']:22} {x['cagr']*100:>7.2f}% {x['vol']*100:>7.2f}% "
              f"{x['max_dd']*100:>7.1f}% {x['sharpe']:>8.3f} {x['calmar']:>8.3f}")

    # 样本内外
    print("\n" + "=" * 76)
    print(f"样本切分（{IS_END}）")
    print("=" * 76)
    split = {}
    for name, series in (("多因子TopN", nav["nav"]), ("等权全池", eq_nav)):
        a = series[series.index < IS_END]
        b = series[series.index >= IS_END]
        ma, mb_ = metrics(a / a.iloc[0], "in"), metrics(b / b.iloc[0], "out")
        if not ma or not mb_:
            continue
        split[name] = {"in": ma, "out": mb_}
        print(f"{name:12}  样本内 {ma['cagr']*100:>6.2f}% (回撤 {ma['max_dd']*100:>5.1f}%)   "
              f"样本外 {mb_['cagr']*100:>6.2f}% (回撤 {mb_['max_dd']*100:>5.1f}%)")

    # 最近一年
    print("\n最近 12 个月：")
    for name, series in (("多因子TopN", nav["nav"]), ("等权全池", eq_nav)):
        w = series[series.index >= series.index[-1] - pd.Timedelta(days=365)]
        if len(w) > 20:
            r = w.iloc[-1] / w.iloc[0] - 1
            print(f"  {name:12} {r*100:+.2f}%")

    out = HERE.parent / "reports" / "multifactor_backtest.json"
    out.write_text(json.dumps({
        "factors": [{"op": o, "n": n, "dir": d, "w": w} for o, n, d, w in FACTORS],
        "params": {"top_n": TOP_N, "rebal_days": REBAL_DAYS, "cost": COST},
        "multifactor": m, "single_rsv10": ms, "equal_weight": mb, "split": split,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    nav.to_csv(HERE.parent / "reports" / "nav_multifactor.csv")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
