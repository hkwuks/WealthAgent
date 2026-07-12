"""AuroraCore 黄金量化 API — 新内核驱动，与旧 API 共存"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

from core import (
    BacktestEngine, BacktestConfig, EventBus, Bar,
    MetricsCalculator, ComparisonReport, StrategyRegistry,
    WalkForwardValidator,
)
from gold.adapter import GoldDomainAdapter

router = APIRouter(prefix="/gold-core", tags=["黄金量化 (AuroraCore)"])

adapter = GoldDomainAdapter()


class BacktestRequest(BaseModel):
    strategy_name: str
    symbol: str = "AU0"
    period: str = "d"
    start_date: str = "2024-01-01"
    end_date: str = "2025-12-31"
    capital: float = 1_000_000.0
    slippage_pct: float = 0.0005
    fill_ratio: float = 1.0
    open_commission: float = 10.0
    close_commission: float = 10.0
    params: dict = {}


@router.get("/strategies")
async def list_core_strategies():
    """列出 AuroraCore 注册的黄金策略"""
    gold_strategies = adapter.get_available_strategies()
    result = []
    for name, cls in gold_strategies.items():
        result.append({
            "name": name,
            "type": getattr(cls, "strategy_type", ""),
            "description": getattr(cls, "description", ""),
            "default_params": getattr(cls, "default_params", {}),
        })
    return {"success": True, "data": result}


@router.post("/backtest")
async def run_core_backtest(req: BacktestRequest):
    """使用 AuroraCore 引擎运行黄金回测"""
    from backend.gold.data.gateway import GoldDataGateway

    gateway = GoldDataGateway()
    klines = await gateway.get_bars(
        symbol=req.symbol, period=req.period,
        start=req.start_date, end=req.end_date, refresh=True,
    )
    if not klines:
        raise HTTPException(400, detail="无 K 线数据")

    bars = []
    for k in klines:
        dt = k.datetime if hasattr(k, "datetime") and k.datetime else datetime.now()
        bars.append(Bar(
            symbol=req.symbol, exchange="SHFE", timeframe=req.period,
            datetime=dt,
            open=float(k.open),
            high=float(k.high),
            low=float(k.low),
            close=float(k.close),
            volume=float(k.volume),
        ))
    if not bars:
        raise HTTPException(400, detail="K 线数据解析失败")

    # 查找策略
    strategies = adapter.get_available_strategies()
    if req.strategy_name not in strategies:
        try:
            cls = StrategyRegistry.get(req.strategy_name)
        except KeyError:
            raise HTTPException(404, detail=f"策略 {req.strategy_name} 未找到")
    else:
        cls = strategies[req.strategy_name]

    strategy = cls()
    if req.params:
        strategy.params = req.params

    cfg = BacktestConfig(
        initial_capital=req.capital,
        start_date=bars[0].datetime.date(),
        end_date=bars[-1].datetime.date(),
        timeframe=_timeframe_map(req.period),
    )

    engine = BacktestEngine(cfg)
    engine.set_event_bus(EventBus())
    engine.set_strategy(strategy)
    engine.set_executor(adapter.create_executor({
        "slippage_pct": req.slippage_pct,
        "fill_ratio": req.fill_ratio,
    }))
    engine.set_cost_model(adapter.create_cost_model({
        "open_commission": req.open_commission,
        "close_commission": req.close_commission,
    }))
    engine.set_data(bars)

    from core import RiskPipeline
    pipeline = RiskPipeline()
    for c in adapter.default_risk_checks():
        pipeline.add(c)
    engine.set_risk(pipeline)

    try:
        report = await _run_in_thread(engine.run)
    except Exception as e:
        logger.error(f"AuroraCore 黄金回测失败: {e}")
        raise HTTPException(500, detail=str(e))

    equity = [e["equity"] for e in report.equity_curve]
    metrics = MetricsCalculator.calculate(equity)
    metrics.total_trades = report.total_trades

    return {
        "success": True,
        "data": {
            "strategy": req.strategy_name,
            "engine": "aurora_core",
            "metadata": {
                "symbol": req.symbol,
                "bar_count": len(bars),
                "period": f"{req.start_date} ~ {req.end_date}",
            },
            "metrics": {
                "total_return": metrics.total_return,
                "annual_return": metrics.annual_return,
                "volatility": metrics.volatility,
                "max_drawdown": metrics.max_drawdown,
                "sharpe_ratio": metrics.sharpe_ratio,
                "sortino_ratio": metrics.sortino_ratio,
                "calmar_ratio": metrics.calmar_ratio,
                "var_95": metrics.var_95,
                "total_trades": metrics.total_trades,
                "win_rate": metrics.win_rate,
            },
            "equity_curve": equity,
            "trade_count": report.total_trades,
        },
    }


def _timeframe_map(period: str) -> str:
    return {"1m": "1m", "5m": "5m", "d": "1d", "w": "1w", "mo": "1M"}.get(period, "1d")


async def _run_in_thread(fn, *args, **kwargs):
    import asyncio
    return await asyncio.to_thread(fn, *args, **kwargs)
