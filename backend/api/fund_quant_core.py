"""AuroraCore 基金量化 API — 新内核驱动，与旧 API 共存"""
from datetime import date
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

from core import (
    BacktestEngine, BacktestConfig, EventBus,
    MetricsCalculator, ComparisonReport,
    StrategyRegistry,
    Bar, FundNavPoint,
)
from fund_quant.adapter import FundDomainAdapter

router = APIRouter(prefix="/fund-quant-core", tags=["基金量化 (AuroraCore)"])

adapter = FundDomainAdapter()


class BacktestRequest(BaseModel):
    strategy_name: str
    fund_code: str = "000001"
    start_date: str = "2024-01-01"
    end_date: str = "2025-12-31"
    initial_capital: float = 100_000.0
    confirmation_delay: int = 1
    params: dict = {}


@router.get("/strategies")
async def list_core_strategies():
    """列出 AuroraCore 注册的基金策略"""
    all_strategies = StrategyRegistry.list_all()
    fund_strategies = adapter.get_available_strategies()
    result = []
    for name, cls in fund_strategies.items():
        result.append({
            "name": name,
            "type": getattr(cls, "strategy_type", ""),
            "description": getattr(cls, "description", ""),
            "default_params": getattr(cls, "default_params", {}),
        })
    return {"success": True, "data": result, "registry_total": len(all_strategies)}


@router.post("/backtest")
async def run_core_backtest(req: BacktestRequest):
    """使用 AuroraCore 引擎运行基金回测"""
    # 获取净值数据（查数据库，没有则生成模拟数据）
    from backend.fund_quant.data.storage import get_nav_history
    nav_data = await _run_in_thread(get_nav_history, req.fund_code)
    if not nav_data:
        from datetime import date, timedelta
        nav_data = []
        d = date.fromisoformat(req.start_date) if isinstance(req.start_date, str) else req.start_date
        if isinstance(d, str): d = date.fromisoformat(d)
        end = date.fromisoformat(req.end_date) if isinstance(req.end_date, str) else req.end_date
        if isinstance(end, str): end = date.fromisoformat(end)
        cur = d
        base_nav = 1.0
        while cur <= end:
            days = (cur - d).days
            trend = 1.0 + days * 0.002 if days < 150 else 1.0 + (300 - days) * 0.002
            nav_data.append({
                "date": cur.isoformat(),
                "nav": round(trend, 4),
                "fund_name": req.fund_code,
            })
            cur += timedelta(days=1)

    navs = []
    for r in nav_data:
        try:
            nd = date.fromisoformat(r["date"]) if isinstance(r["date"], str) else r["date"]
            navs.append(FundNavPoint(
                fund_code=req.fund_code, date=nd,
                nav=r.get("nav", 0),
                adjusted_nav=r.get("adjusted_nav"),
            ))
        except Exception:
            continue
    if not navs:
        raise HTTPException(400, detail="净值数据解析失败")

    # 查找策略
    strategies = adapter.get_available_strategies()
    if req.strategy_name not in strategies:
        # 尝试在全局注册表中查找
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
        initial_capital=req.initial_capital,
        start_date=navs[0].date,
        end_date=navs[-1].date,
    )

    engine = BacktestEngine(cfg)
    engine.set_event_bus(EventBus())
    engine.set_strategy(strategy)
    engine.set_executor(adapter.create_executor({"confirmation_delay": req.confirmation_delay}))
    engine.set_data(navs)
    from core import RiskPipeline
    pipeline = RiskPipeline()
    for c in adapter.default_risk_checks():
        pipeline.add(c)
    engine.set_risk(pipeline)

    try:
        report = await _run_in_thread(engine.run)
    except Exception as e:
        logger.error(f"AuroraCore 基金回测失败: {e}")
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
                "fund_code": req.fund_code,
                "nav_count": len(navs),
                "period": f"{navs[0].date} ~ {navs[-1].date}",
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


async def _run_in_thread(fn, *args, **kwargs):
    import asyncio
    return await asyncio.to_thread(fn, *args, **kwargs)
