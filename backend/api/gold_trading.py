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
        start=req.start_date, end=req.end_date,
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
        start=req.start_date, end=req.end_date,
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

    # 获取最新行情
    bars = await gateway.get_bars(symbol=symbol, period="d", limit=200)
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
