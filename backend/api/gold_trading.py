"""
黄金量化交易API路由

Phase 3: 回测、策略列表、多策略对比、信号查询
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime

from backend.gold.strategy.base import StrategyRegistry
from backend.gold.backtest.engine import Backtester
from backend.gold.data.gateway import GoldDataGateway
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
        start=req.start_date, end=req.end_date,
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
            "signals": result["signals"][-20:],  # 最近20条信号
            "trades": result["trades"][-20:],     # 最近20条交易
        },
    }


# ===== 多策略对比 =====

@router.post("/compare")
async def compare_strategies(req: StrategyComparisonRequest):
    """
    多策略对比回测

    同一数据集、同一资金，跑多个策略并排对比。
    """
    results = []
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
            results.append({
                "strategy": name,
                "report": result["report"],
                "signal_count": len(result["signals"]),
            })
        except Exception as e:
            errors.append(f"Strategy '{name}' failed: {str(e)}")

    return {
        "success": True,
        "data": {
            "comparison": results,
            "errors": errors,
        },
    }


# ===== 信号查询 =====

@router.get("/signals")
async def get_recent_signals(
    strategy_name: Optional[str] = Query(None, description="策略名称过滤"),
    limit: int = Query(50, ge=1, le=200),
):
    """获取最近的交易信号（从数据库）"""
    from backend.gold.data.storage import GoldDataStore
    store = GoldDataStore()
    signals = store.get_signals(strategy_id=strategy_name, limit=limit)
    return {"success": True, "data": signals}


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
        },
    }
