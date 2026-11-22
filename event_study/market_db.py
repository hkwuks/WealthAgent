"""本地行情库：ETF 日线（OHLCV）+ 净值。

教程第四章 §4.1「免费数据优先、交叉校验」，§4.4「数据质量检查」。
东财 push2his 实测经常连不上（5 次重试全失败），所以主源新浪、备源东财。

用法:
    from market_db import load_daily, update_all
    df = load_daily("510300")     # 有缓存读缓存
输出: data/ohlcv/<code>.json  [{date,open,high,low,close,volume,amount}]
"""
import json
import os
import time
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
OUT = PROJECT / "data" / "ohlcv"

# 代理会干扰东财直连；新浪需要代理。按源分别处理。
_PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")


def _no_proxy():
    return {k: os.environ.pop(k, None) for k in _PROXY_KEYS}


def _restore(saved):
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v


def _sina_etf(code: str) -> pd.DataFrame | None:
    """新浪 ETF 日线 — 实测唯一稳定的源（3520 条，含 OHLCV+成交额）。

    akshare 的 stock_zh_a_daily 对 ETF 会 JSONDecodeError，用这个专用接口。
    """
    import akshare as ak

    sym = ("sh" if code.startswith(("5", "6")) else "sz") + code
    for _ in range(3):
        try:
            df = ak.fund_etf_hist_sina(symbol=sym)
            if df is not None and not df.empty:
                return df
        except Exception:
            time.sleep(2)
    return None


def _eastmoney(code: str, start: str, end: str) -> pd.DataFrame | None:
    """东财 ETF 源（含涨跌幅/换手率）。需绕过代理，实测常失败，仅作备源。"""
    import akshare as ak

    saved = _no_proxy()
    try:
        for _ in range(2):
            try:
                df = ak.fund_etf_hist_em(
                    symbol=code, period="daily",
                    start_date=start, end_date=end, adjust="",
                )
                if df is not None and not df.empty:
                    return df
            except Exception:
                time.sleep(2)
        return None
    finally:
        _restore(saved)


SINA_MAP = {"date": "日期", "open": "开盘", "high": "最高", "low": "最低",
            "close": "收盘", "volume": "成交量", "amount": "成交额"}


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """统一成小写英文列。两个源列名完全不同，不归一化下游全是 None。"""
    cols = {c.lower(): c for c in df.columns}
    out = pd.DataFrame()
    for std, cn in SINA_MAP.items():
        src = cols.get(std) or cols.get(cn)
        if src is None:
            out[std] = None
        else:
            out[std] = df[src]
    out["date"] = pd.to_datetime(out["date"].astype(str))
    for c in ("open", "high", "low", "close", "volume", "amount"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["close"]).sort_values("date")
    return out.drop_duplicates("date", keep="last").reset_index(drop=True)


def fetch(code: str, start: str = "20150101", end: str | None = None) -> pd.DataFrame | None:
    end = end or pd.Timestamp.today().strftime("%Y%m%d")
    for src in (_sina_etf, _eastmoney):
        df = src(code, start, end) if src is _eastmoney else src(code)
        if df is not None and not df.empty:
            n = normalize(df)
            n = n[n["date"] >= pd.Timestamp(start)]
            if len(n) > 20:
                return n
    return None


def load_daily(code: str, refresh: bool = False) -> pd.DataFrame | None:
    f = OUT / f"{code}.json"
    if f.exists() and not refresh:
        rows = json.loads(f.read_text(encoding="utf-8"))
        if rows:
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"])
            return df
    df = fetch(code)
    if df is None:
        return None
    OUT.mkdir(parents=True, exist_ok=True)
    recs = df.assign(date=df["date"].dt.strftime("%Y-%m-%d")).to_dict("records")
    f.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    return df


def update_all(codes: list[str] | None = None) -> dict:
    codes = codes or CODES
    ok, fail = {}, []
    for c in codes:
        df = load_daily(c, refresh=True)
        if df is None:
            fail.append(c)
        else:
            ok[c] = (len(df), str(df["date"].iloc[0].date()), str(df["date"].iloc[-1].date()))
        time.sleep(0.5)
    return {"ok": ok, "fail": fail}


# 用于研究的最小池：宽基 + 创业板 + 红利 + 跨境 + 债券 + 黄金
CODES = [
    "510300", "510500", "512100", "159915", "588000",
    "515080", "512890", "515650", "563020",
    "513100", "513500", "518880", "159985", "511260", "511520",
]


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "update":
        r = update_all()
        print(f"成功 {len(r['ok'])} / 失败 {len(r['fail'])}")
        for c, (n, a, b) in r["ok"].items():
            print(f"  {c} {n:>5} 条  {a} ~ {b}")
        if r["fail"]:
            print("失败:", r["fail"])
    else:
        df = load_daily(sys.argv[1] if len(sys.argv) > 1 else "510300")
        print(df.tail(5).to_string(index=False) if df is not None else "无数据")
