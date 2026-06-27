"""
黄金量化交易API路由

完整端点: 状态/策略/回测/对比/敏感性/验证/信号生成/风控/数据同步/配置
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

from backend.gold.strategy.base import StrategyRegistry
from backend.gold.backtest.engine import Backtester
from backend.gold.backtest.sensitivity import SensitivityAnalyzer
from backend.gold.backtest.validation import SampleSplitter, ScenarioValidator
from backend.gold.risk.checks import RiskChecker
from backend.gold.signal.output import SignalOutput
from backend.gold.data.gateway import GoldDataGateway
from backend.gold.data.storage import GoldDataStore
from backend.gold.core.models import BacktestRequest, StrategyComparisonRequest
from backend.gold.core.config import GoldSettings
from loguru import logger

router = APIRouter(prefix="/gold/trading", tags=["黄金量化交易"])

gateway = GoldDataGateway()


# ===== 系统状态 =====

@router.get("/status")
async def get_status():
    """系统状态"""
    strategies = StrategyRegistry.list_all()
    return {
        "status": "ok",
        "mode": "signal_only",
        "strategies": list(strategies.keys()),
    }


# ===== 策略管理 =====

@router.get("/strategies")
async def list_strategies():
    """列出所有可用策略"""
    strategies = StrategyRegistry.list_all()
    result = []
    for name, cls in strategies.items():
        result.append({
            "strategy_id": name,
            "strategy_name": cls.strategy_name,
            "strategy_type": cls.strategy_type,
            "description": cls.description,
            "default_params": cls.default_params,
            "param_ranges": cls.param_ranges,
        })
    return {"success": True, "data": result}


@router.get("/strategies/{strategy_name}")
async def get_strategy_detail(strategy_name: str):
    """获取策略详情"""
    cls = StrategyRegistry.get(strategy_name)
    if cls is None:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found")
    return {
        "success": True,
        "data": {
            "strategy_id": strategy_name,
            "strategy_name": cls.strategy_name,
            "strategy_type": cls.strategy_type,
            "description": cls.description,
            "default_params": cls.default_params,
            "param_ranges": cls.param_ranges,
        },
    }


# ===== 回测 =====

@router.post("/backtest")
async def run_backtest(req: BacktestRequest):
    """
    运行单策略回测

    从数据网关获取K线，驱动Backtester运行，返回回测报告。
    """
    cls = StrategyRegistry.get(req.strategy_name)
    if cls is None:
        raise HTTPException(status_code=404, detail=f"Strategy '{req.strategy_name}' not found")

    bars = await gateway.get_bars(
        symbol=req.symbol, period=req.period,
        start=req.start_date, end=req.end_date, refresh=True,
    )
    if not bars:
        raise HTTPException(status_code=400, detail="No bar data available for the given parameters")

    strategy = cls()
    backtester = Backtester()
    try:
        result = backtester.run(strategy, bars, capital=req.capital, params=req.params)
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "success": True,
        "data": {
            "strategy": result["strategy"],
            "signal_count": len(result["signals"]),
            "trade_count": len([t for t in result["trades"] if t.get("type") == "close"]),
            "report": result["report"],
            "signals": result["signals"][-20:],
            "trades": result["trades"][-20:],
        },
    }


# ===== 多策略对比 =====

@router.post("/compare")
async def compare_strategies(req: StrategyComparisonRequest):
    """
    多策略对比回测

    同一数据集、同一资金，跑多个策略并排对比，含排名。
    """
    results = {}
    errors = []

    for name in req.strategy_names:
        cls = StrategyRegistry.get(name)
        if cls is None:
            errors.append(f"Strategy '{name}' not found")
            continue

        bars = await gateway.get_bars(
            symbol=req.symbol, period=req.period,
            start=req.start_date, end=req.end_date,
        )
        if not bars:
            errors.append(f"No data for strategy '{name}'")
            continue

        strategy = cls()
        backtester = Backtester()
        try:
            result = backtester.run(strategy, bars, capital=req.capital)
            results[name] = result["report"]
        except Exception as e:
            errors.append(f"Strategy '{name}' failed: {str(e)}")

    # 排名
    comparison = {
        "sharpe_ranking": sorted(
            [(n, r["performance"]["sharpe_ratio"]) for n, r in results.items()],
            key=lambda x: x[1], reverse=True
        ),
        "return_ranking": sorted(
            [(n, r["performance"]["total_return"]) for n, r in results.items()],
            key=lambda x: x[1], reverse=True
        ),
        "max_dd_ranking": sorted(
            [(n, r["risk"]["max_drawdown"]) for n, r in results.items()],
            key=lambda x: abs(x[1])
        ),
        "win_rate_ranking": sorted(
            [(n, r["performance"]["win_rate"]) for n, r in results.items()],
            key=lambda x: x[1], reverse=True
        ),
    }

    return {
        "success": True,
        "data": {
            "strategies": results,
            "comparison": comparison,
            "errors": errors,
        },
    }


# ===== 参数敏感性分析 =====

class SensitivityRequest(BaseModel):
    strategy_name: str
    symbol: str = "AU0"
    period: str = "d"
    start_date: str = "2024-01-01"
    end_date: str = "2025-12-31"
    capital: float = 1_000_000
    param_ranges: Optional[dict] = None  # None → use strategy's param_ranges


@router.post("/backtest/sensitivity")
async def run_sensitivity(req: SensitivityRequest):
    """参数敏感性分析 — 邻域扫描 + 稳健性评估"""
    cls = StrategyRegistry.get(req.strategy_name)
    if cls is None:
        raise HTTPException(status_code=404, detail=f"Strategy '{req.strategy_name}' not found")

    bars = await gateway.get_bars(
        symbol=req.symbol, period=req.period,
        start=req.start_date, end=req.end_date, refresh=True,
    )
    if not bars:
        raise HTTPException(status_code=400, detail="No bar data available")

    # 使用策略自带的param_ranges或用户自定义
    param_ranges = req.param_ranges or cls.param_ranges
    if not param_ranges:
        raise HTTPException(status_code=400, detail="No param_ranges available for this strategy")

    analyzer = SensitivityAnalyzer(capital=req.capital)
    try:
        result = analyzer.analyze(req.strategy_name, cls.default_params, param_ranges, bars)
    except Exception as e:
        logger.error(f"Sensitivity analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, "data": result}


# ===== In/Out样本验证 + 场景验证 =====

class ValidationRequest(BaseModel):
    strategy_name: str
    symbol: str = "AU0"
    period: str = "d"
    start_date: str = "2020-01-01"
    end_date: str = "2025-12-31"
    capital: float = 1_000_000
    in_sample_ratio: float = 0.7
    scenario_name: Optional[str] = None  # None → run all scenarios


@router.post("/backtest/validation")
async def run_validation(req: ValidationRequest):
    """In/Out样本验证 + 场景验证"""
    cls = StrategyRegistry.get(req.strategy_name)
    if cls is None:
        raise HTTPException(status_code=404, detail=f"Strategy '{req.strategy_name}' not found")

    bars = await gateway.get_bars(
        symbol=req.symbol, period=req.period,
        start=req.start_date, end=req.end_date, refresh=True,
    )
    if not bars:
        raise HTTPException(status_code=400, detail="No bar data available")

    # In/Out样本验证
    splitter = SampleSplitter()
    strategy = cls()
    split_result = splitter.validate(strategy, bars, capital=req.capital,
                                      in_sample_ratio=req.in_sample_ratio)

    # 场景验证
    validator = ScenarioValidator()
    scenario_result = validator.validate(
        req.strategy_name, bars, capital=req.capital,
        scenario_name=req.scenario_name,
    )

    return {
        "success": True,
        "data": {
            "sample_validation": split_result,
            "scenario_validation": scenario_result,
        },
    }


# ===== 信号生成 =====

@router.post("/signal/generate")
async def generate_signal(
    strategy_name: str = Query(..., description="策略名称"),
    symbol: str = Query("AU0", description="合约代码"),
):
    """
    手动触发信号生成

    用最新行情数据驱动策略，输出交易建议。
    不自动下单，仅返回建议。
    """
    cls = StrategyRegistry.get(strategy_name)
    if cls is None:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found")

    # 获取最新行情 — ML策略需要足够数据训练模型
    bars = await gateway.get_bars(symbol=symbol, period="d", start="2020-01-01", refresh=True)
    if not bars or len(bars) < 30:
        raise HTTPException(status_code=400, detail="Insufficient data for signal generation")

    strategy = cls()
    backtester = Backtester()

    # 用最近bars运行策略获取信号
    try:
        result = backtester.run(strategy, bars, capital=1_000_000)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 获取最新信号
    signals = result.get("signals", [])
    if not signals:
        return {
            "success": True,
            "data": {
                "signal": None,
                "message": "当前无交易信号",
                "strategy": strategy_name,
            },
        }

    # 取最后一个信号作为建议
    from backend.gold.core.models import GoldSignal
    latest_signal_data = signals[-1]
    signal = GoldSignal(**latest_signal_data) if isinstance(latest_signal_data, dict) else None

    if signal is None:
        return {"success": True, "data": {"signal": latest_signal_data, "strategy": strategy_name}}

    # 风控检查
    risk_checker = RiskChecker()
    risk_result = risk_checker.check(signal)

    # 输出交易建议
    signal_output = SignalOutput()
    advice = signal_output.output(signal, risk_result)

    return {"success": True, "data": advice}


# ===== 信号查询 =====

@router.get("/signals")
async def get_recent_signals(
    strategy_name: Optional[str] = Query(None, description="策略名称过滤"),
    limit: int = Query(50, ge=1, le=200),
):
    """获取最近的交易信号（从数据库）"""
    store = GoldDataStore()
    signals = store.get_signals(strategy_id=strategy_name, limit=limit)
    return {"success": True, "data": signals}


# ===== 风控 =====

@router.get("/risk/status")
async def get_risk_status():
    """获取风控状态和配置"""
    config = GoldSettings()
    store = GoldDataStore()

    # 获取最近信号统计
    recent_signals = store.get_signals(limit=100)

    return {
        "success": True,
        "data": {
            "checks": [
                {"name": "max_drawdown", "threshold": f"{config.max_drawdown_pct*100:.0f}%", "status": "active"},
                {"name": "daily_loss", "threshold": f"{config.max_daily_loss_pct*100:.0f}%", "status": "active"},
                {"name": "signal_frequency", "threshold": f"{config.max_daily_signals}/日", "status": "active"},
            ],
            "recent_signal_count": len(recent_signals),
        },
    }


# ===== 数据管理 =====

@router.post("/sync-data")
async def sync_gold_bars(
    symbol: str = Query("AU0", description="合约代码"),
    period: str = Query("d", description="K线周期"),
    start_date: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(None, description="结束日期 YYYY-MM-DD"),
):
    """从外部数据源同步K线到本地数据库"""
    bars = await gateway.get_bars(symbol=symbol, period=period, start=start_date, end=end_date)
    if not bars:
        raise HTTPException(status_code=400, detail="No data fetched")

    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "period": period,
            "bars_synced": len(bars),
            "date_range": {
                "start": bars[0].datetime.strftime("%Y-%m-%d"),
                "end": bars[-1].datetime.strftime("%Y-%m-%d"),
            } if bars else None,
        },
    }


# ===== K线数据（图表用） =====

@router.get("/bars")
async def get_bars_for_chart(
    symbol: str = Query("AU0", description="合约代码"),
    period: str = Query("d", description="K线周期: d=日线, 1=1分钟, 5=5分钟, 30=30分钟"),
    start_date: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(200, ge=1, le=2000, description="返回根数"),
):
    """返回K线数据用于图表展示（OHLCV + 技术指标）"""
    bars = await gateway.get_bars(
        symbol=symbol, period=period,
        start=start_date, end=end_date,
        limit=limit, refresh=True,
    )
    if not bars:
        raise HTTPException(status_code=404, detail="No bar data available")

    # 计算MA指标用于图表
    closes = [b.close for b in bars]
    def ma(arr, n):
        if len(arr) < n:
            return [None] * len(arr)
        result = [None] * (n - 1)
        for i in range(n - 1, len(arr)):
            result.append(round(sum(arr[i-n+1:i+1]) / n, 2))
        return result

    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "period": period,
            "bars": [
                {
                    "time": b.datetime.strftime("%Y-%m-%d") if period == "d" else b.datetime.isoformat(),
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                }
                for b in bars
            ],
            "indicators": {
                "ma5": ma(closes, 5),
                "ma10": ma(closes, 10),
                "ma20": ma(closes, 20),
                "ma60": ma(closes, 60),
            },
            "count": len(bars),
        },
    }


# ===== 市场数据仪表盘（实时用） =====

@router.get("/market-data")
async def get_market_data():
    """获取黄金实时市场数据仪表盘"""
    try:
        from backend.gold.core.config import GoldSettings
        from backend.gold.data.storage import GoldDataStore

        config = GoldSettings()
        store = GoldDataStore()

        bars = await gateway.get_bars(symbol="AU0", period="d", limit=300, refresh=True)
        if not bars:
            raise HTTPException(status_code=404, detail="No market data")

        latest = bars[-1]
        prev = bars[-2] if len(bars) > 1 else latest

        price = latest.close
        prev_price = prev.close
        change = price - prev_price
        change_pct = (change / prev_price * 100) if prev_price > 0 else 0

        high_20 = max(b.high for b in bars[-20:])
        low_20 = min(b.low for b in bars[-20:])
        high_60 = max(b.high for b in bars[-60:]) if len(bars) >= 60 else high_20
        low_60 = min(b.low for b in bars[-60:]) if len(bars) >= 60 else low_20

        # 计算简单技术指标
        closes = [b.close for b in bars]
        rsi = _calc_rsi(closes, 14)
        atr = _calc_atr(bars, 14)
        vol_avg5 = sum(b.volume for b in bars[-5:]) / 5
        vol_avg20 = sum(b.volume for b in bars[-20:]) / 20
        vol_ratio = vol_avg5 / vol_avg20 if vol_avg20 > 0 else 1

        recent_signals = store.get_signals(limit=10)

        return {
            "success": True,
            "data": {
                "price": round(price, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "high": round(latest.high, 2),
                "low": round(latest.low, 2),
                "open": round(latest.open, 2),
                "volume": latest.volume,
                "high_20": round(high_20, 2),
                "low_20": round(low_20, 2),
                "high_60": round(high_60, 2),
                "low_60": round(low_60, 2),
                "rsi_14": round(rsi, 1) if rsi is not None else None,
                "atr_14": round(atr, 2) if atr is not None else None,
                "vol_ratio": round(vol_ratio, 2),
                "timestamp": latest.datetime.isoformat() if hasattr(latest.datetime, 'isoformat') else str(latest.datetime),
                "date": latest.datetime.strftime("%Y-%m-%d") if hasattr(latest.datetime, 'strftime') else str(latest.datetime),
                "recent_signals": recent_signals,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Market data error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== K线技术分析 =====

@router.get("/analysis")
async def get_kline_analysis(
    symbol: str = Query("AU0", description="合约代码"),
    period: str = Query("d", description="K线周期"),
    limit: int = Query(500, ge=60, le=2000),
):
    """K线技术分析解读 — 趋势/指标/价位/综合研判"""
    bars = await gateway.get_bars(symbol=symbol, period=period, limit=limit, refresh=False)
    if not bars:
        raise HTTPException(status_code=404, detail="No data for analysis")

    closes = [b.close for b in bars]
    opens = [b.open for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    vols = [b.volume for b in bars]
    latest = bars[-1]
    price = latest.close

    # --- 移动均线 ---
    def ma(n):
        if len(closes) < n: return None
        return round(sum(closes[-n:]) / n, 2)

    ma5, ma10, ma20, ma60, ma120, ma250 = [ma(n) for n in [5, 10, 20, 60, 120, 250]]
    mas = {"ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60, "ma120": ma120, "ma250": ma250}

    # 均线排列
    short = [ma5, ma10, ma20]
    short_valid = all(v is not None for v in short)
    if short_valid and all(short[i] > short[i + 1] for i in range(2)):
        ma_alignment = "多头排列"
    elif short_valid and all(short[i] < short[i + 1] for i in range(2)):
        ma_alignment = "空头排列"
    else:
        ma_alignment = "交织盘整"

    # 价格相对均线位置
    above_ma_count = sum(1 for m in [ma5, ma10, ma20, ma60] if m is not None and price > m)
    below_ma_count = sum(1 for m in [ma5, ma10, ma20, ma60] if m is not None and price < m)
    ma_position = "均线上方" if above_ma_count >= 3 else "均线下方" if below_ma_count >= 3 else "均线附近"

    # --- RSI ---
    rsi14 = _calc_rsi(closes, 14)
    rsi_signal = "超卖" if rsi14 and rsi14 < 30 else "超买" if rsi14 and rsi14 > 70 else "中性"

    # --- 布林带 (20,2) ---
    import statistics
    bb_ma = ma(20)
    bb_std = statistics.stdev(closes[-20:]) if len(closes) >= 20 else 0
    bb_upper = round(bb_ma + 2 * bb_std, 2) if bb_ma else None
    bb_lower = round(bb_ma - 2 * bb_std, 2) if bb_ma else None
    bb_width = round((bb_upper - bb_lower) / bb_ma * 100, 2) if bb_ma and bb_upper and bb_lower else None
    if bb_lower and bb_upper:
        bb_position = round((price - bb_lower) / (bb_upper - bb_lower) * 100, 1)
        bb_signal = "下轨附近" if bb_position < 20 else "上轨附近" if bb_position > 80 else "中轨附近"
    else:
        bb_position, bb_signal = None, "--"

    # --- 关键价位 ---
    lookback = min(60, len(bars))
    recent_high = max(highs[-lookback:])
    recent_low = min(lows[-lookback:])
    recent_high_idx = highs[-lookback:].index(recent_high)
    recent_low_idx = lows[-lookback:].index(recent_low)

    # 近52周高/低（仅日线有意义）
    yearly = min(252, len(bars))
    high_52w = max(highs[-yearly:])
    low_52w = min(lows[-yearly:])

    # 斐波那契
    fib_diff = recent_high - recent_low
    fib_levels = {
        "0.236": round(recent_high - fib_diff * 0.236, 2),
        "0.382": round(recent_high - fib_diff * 0.382, 2),
        "0.500": round(recent_high - fib_diff * 0.500, 2),
        "0.618": round(recent_high - fib_diff * 0.618, 2),
        "0.786": round(recent_high - fib_diff * 0.786, 2),
    }

    # --- 成交量分析 ---
    vol_avg_60 = sum(vols[-60:]) / 60 if len(vols) >= 60 else sum(vols) / len(vols)
    vol_avg_20 = sum(vols[-20:]) / 20
    vol_avg_5 = sum(vols[-5:]) / 5
    vol_ratio_20_60 = round(vol_avg_20 / vol_avg_60, 2) if vol_avg_60 else 1
    vol_trend = "缩量" if vol_ratio_20_60 < 0.8 else "放量" if vol_ratio_20_60 > 1.3 else "正常"
    latest_vol_ratio = round(vols[-1] / vol_avg_20, 1) if vol_avg_20 else 1

    # --- 特殊K线形态（近30根） ---
    patterns = []
    for i in range(-min(30, len(bars)), 0):
        b = bars[i]
        body = abs(b.close - b.open)
        total_range = b.high - b.low
        if total_range == 0:
            continue
        body_ratio = body / total_range

        # 十字星
        if body_ratio < 0.1 and total_range / b.open * 100 > 1.0:
            patterns.append({
                "date": b.datetime.strftime("%Y-%m-%d") if period == "d" else b.datetime.isoformat(),
                "type": "十字星",
                "detail": f"上下影线明显，多空博弈激烈" if b.high - max(b.close, b.open) > body and min(b.close, b.open) - b.low > body else "纺锤线，趋势犹豫",
                "signal": "反转预警" if i == -1 else "分歧信号",
            })

        # 大阳/大阴
        range_pct = (b.high - b.low) / b.open * 100
        if b.close > b.open and range_pct > 2.5:
            direction = "大阳线"
            signal_text = "多头强势" if i >= -5 else "多方占优"
            patterns.append({"date": b.datetime.isoformat(), "type": direction, "detail": f"涨幅{(b.close-b.open)/b.open*100:.1f}%", "signal": signal_text})
        elif b.close < b.open and range_pct > 2.5:
            direction = "大阴线"
            signal_text = "空头打压" if i >= -5 else "空方占优"
            patterns.append({"date": b.datetime.isoformat(), "type": direction, "detail": f"跌幅{(b.close-b.open)/b.open*100:.1f}%", "signal": signal_text})

    patterns = patterns[:8]  # 最多8个

    # --- 趋势强度 ---
    # 计算斜率（最近20根收盘价的线性回归）
    if len(closes) >= 20:
        n = 20
        x_avg = (n - 1) / 2
        y_avg = sum(closes[-n:]) / n
        num = sum((i - x_avg) * (closes[-n + i] - y_avg) for i in range(n))
        den = sum((i - x_avg) ** 2 for i in range(n))
        slope = num / den if den != 0 else 0
        trend_strength = "强势" if abs(slope) > 2 else "温和" if abs(slope) > 0.5 else "弱势"
    else:
        slope, trend_strength = 0, "--"

    # 近10日涨跌天数
    up_days = sum(1 for i in range(-10, 0) if closes[i] > closes[i - 1])
    down_days = 10 - up_days

    # 连续涨跌
    streak = 0
    for i in range(-1, -min(20, len(closes)), -1):
        if closes[i] > closes[i - 1]:
            if streak >= 0: streak += 1
            else: break
        else:
            if streak <= 0: streak -= 1
            else: break
    streak_dir = f"连涨{streak}天" if streak > 0 else f"连跌{abs(streak)}天" if streak < 0 else "平盘"

    # --- 综合研判 ---
    judgments = []
    if rsi14 and rsi14 < 35:
        judgments.append("RSI进入超卖区，短期技术性反弹需求上升")
    if bb_position is not None and bb_position < 20:
        judgments.append(f"价格处于布林下轨附近（{bb_position}%），偏低估区域")
    if ma_alignment == "空头排列":
        judgments.append("均线系统空头排列，中期趋势偏空")
    if above_ma_count == 0:
        judgments.append(f"价格运行于所有均线之下，空头主导市场")
    if vol_ratio_20_60 and vol_ratio_20_60 < 0.8:
        judgments.append("近期持续缩量，下跌动能衰减，关注企稳信号")
    if slope and slope < -3:
        judgments.append(f"近期斜率较陡（{slope:.1f}），下跌速度偏快，注意加速赶底可能")
    elif slope and slope > 3:
        judgments.append(f"近期斜率较陡（{slope:.1f}），上涨加速，关注超买风险")
    if streak <= -3:
        judgments.append(f"连续{abs(streak)}日下跌，短期乖离较大")
    if streak >= 3:
        judgments.append(f"连续{streak}日上涨，短期过热需注意回调")

    if not judgments:
        judgments.append("各指标信号不明确，建议结合更大周期趋势判断")

    r = {
        "trend": {
            "direction": "上涨" if slope > 0.5 else "下跌" if slope < -0.5 else "震荡",
            "ma_alignment": ma_alignment,
            "ma_position": ma_position,
            "slope": round(slope, 2) if slope != 0 else None,
            "strength": trend_strength,
            "up_days": up_days,
            "down_days": down_days,
            "streak": streak_dir,
            # 最近涨跌幅（从当前周期视角）
            "change_1w": round((price - closes[-6]) / closes[-6] * 100, 2) if len(closes) >= 6 else None,
            "change_1m": round((price - closes[-22]) / closes[-22] * 100, 2) if len(closes) >= 22 else None,
            "change_3m": round((price - closes[-66]) / closes[-66] * 100, 2) if len(closes) >= 66 else None,
        },
        "indicators": {
            "rsi14": rsi14,
            "rsi_signal": rsi_signal,
            "bb_upper": bb_upper,
            "bb_mid": bb_ma,
            "bb_lower": bb_lower,
            "bb_width": bb_width,
            "bb_position": bb_position,
            "bb_signal": bb_signal,
            "atr14": _calc_atr(bars, 14),
        },
        "mas": mas,
        "levels": {
            "recent_high": round(recent_high, 2),
            "recent_low": round(recent_low, 2),
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "price_position_52w": round((price - low_52w) / (high_52w - low_52w) * 100, 1) if high_52w != low_52w else None,
            "fib": fib_levels,
        },
        "volume": {
            "latest": vols[-1],
            "avg_20": round(vol_avg_20, 0),
            "avg_60": round(vol_avg_60, 0),
            "ratio_20_60": vol_ratio_20_60,
            "trend": vol_trend,
            "recent_vol_ratio": latest_vol_ratio,
        },
        "patterns": patterns,
        "judgment": "；".join(judgments),
    }
    return {"success": True, "data": r, "symbol": symbol, "period": period}


def _calc_rsi(closes: list, period: int = 14):
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff >= 0:
            gains.append(diff); losses.append(0)
        else:
            gains.append(0); losses.append(abs(diff))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def _calc_atr(bars: list, period: int = 14):
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        b, p = bars[i], bars[i-1]
        tr = max(b.high - b.low, abs(b.high - p.close), abs(b.low - p.close))
        trs.append(tr)
    return round(sum(trs[-period:]) / period, 2)


# ===== 配置 =====

@router.get("/config")
async def get_gold_config():
    """获取黄金交易配置"""
    config = GoldSettings()
    return {
        "success": True,
        "data": {
            "au_multiplier": config.au_multiplier,
            "au_margin_rate": config.au_margin_rate,
            "au_price_tick": config.au_price_tick,
            "au_limit_pct": config.au_limit_pct,
            "backtest_capital": config.backtest_capital,
            "backtest_commission_per_lot": config.backtest_commission_per_lot,
            "backtest_slippage_per_lot": config.backtest_slippage_per_lot,
            "risk_free_rate": config.risk_free_rate,
            "max_drawdown_pct": config.max_drawdown_pct,
            "max_daily_loss_pct": config.max_daily_loss_pct,
            "max_daily_signals": config.max_daily_signals,
        },
    }
