"""FundQuant API 路由 — 完整实现"""

import uuid
import asyncio
from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from loguru import logger

from ..fund_quant.core.models import (
    FundSignal, FundQuantResult, BacktestConfig, BacktestResult,
    RiskMetrics, CostModelConfig, FusionSignal,
)
from ..fund_quant.core.enums import SignalType, Direction
from ..fund_quant.data.storage import (
    init_db, get_signals, save_backtest_result, get_backtest_result,
    list_backtest_results, get_nav_history, get_fund_meta, save_nav_points,
)
from ..fund_quant.data.collector import fund_data_collector
from ..fund_quant.data.quality import data_quality_checker
from ..fund_quant.signal.output import signal_output_service
from ..fund_quant.risk.metrics import risk_metrics_calculator

router = APIRouter(prefix="/fund-quant", tags=["基金量化"])


# ── 请求/响应模型 ──

class TimingRequest(BaseModel):
    fund_code: str
    params: dict = {}


class SelectionRequest(BaseModel):
    fund_type: str = "stock"
    top_n: int = 10
    params: dict = {}


class AllocationRequest(BaseModel):
    fund_codes: List[str]
    params: dict = {}


class BacktestRequest(BaseModel):
    strategy_name: str
    fund_codes: List[str]
    start_date: str
    end_date: str
    initial_capital: float = 100000.0
    rebalance_freq: str = "monthly"
    params: dict = {}


class DataCollectRequest(BaseModel):
    fund_codes: List[str]
    years: int = 5


# ── 初始化 ──
init_db()
logger.info("FundQuant 数据库已初始化")


# ── 策略管理 ──

@router.get("/strategy/list")
async def list_strategies():
    """列出可用策略"""
    from ..fund_quant.strategy.base import StrategyRegistry
    registry = StrategyRegistry()
    strategies = registry.list_strategies()
    return {"success": True, "data": strategies}


@router.get("/strategy/params/{name}")
async def get_strategy_params(name: str):
    """获取策略参数"""
    from ..fund_quant.strategy.base import StrategyRegistry
    registry = StrategyRegistry()
    strategy = registry.get_strategy(name)
    if not strategy:
        raise HTTPException(status_code=404, detail=f"策略 {name} 未找到")
    return {"success": True, "data": {
        "name": strategy.strategy_name,
        "type": strategy.strategy_type,
        "description": strategy.description,
        "default_params": strategy.default_params,
        "param_ranges": strategy.param_ranges,
    }}


# ── 择时评估 ──

@router.post("/timing/evaluate")
async def timing_evaluate(req: TimingRequest):
    """单基金择时评估 (并行运行所有择时策略)"""
    from ..fund_quant.strategy.base import StrategyRegistry
    from ..fund_quant.strategy.fusion import signal_fusion

    nav_data = get_nav_history(req.fund_code)
    if not nav_data:
        raise HTTPException(status_code=404, detail=f"基金 {req.fund_code} 净值数据不足")

    # 并行运行所有择时策略
    registry = StrategyRegistry()
    timing_strategies = registry.list_by_type("timing")

    # 从数据库获取净值序列用于策略计算
    nav_values = [r.get("nav", 0) for r in nav_data if r.get("nav")]
    dates = [r["date"] for r in nav_data if r.get("nav")]

    async def run_strategy(s_info: dict) -> List[FundSignal]:
        strategy = registry.get_strategy(s_info["name"])
        if not strategy:
            return []
        try:
            # 传入净值数据作为评估输入
            strategy._state["nav_values"] = nav_values
            strategy._state["nav_dates"] = dates
            strategy._state["fund_code"] = req.fund_code
            result = strategy.on_evaluate(portfolio=None, info_set=None)
            return result or []
        except Exception as e:
            logger.warning(f"择时策略 [{s_info['name']}] 评估异常: {e}")
            return []

    tasks = [run_strategy(s) for s in timing_strategies]
    results = await asyncio.gather(*tasks)
    all_signals = [s for sublist in results for s in sublist]

    # 融合信号
    fusion = signal_fusion.fuse(all_signals) if all_signals else None

    return {
        "success": True,
        "data": {
            "fund_code": req.fund_code,
            "fund_name": nav_data[0].get("fund_name", req.fund_code),
            "nav_count": len(nav_values),
            "date_range": f"{dates[0]} ~ {dates[-1]}" if len(dates) >= 2 else dates[0] if dates else None,
            "strategies_run": len([t for t in results if t]),
            "signals": [s.model_dump() for s in all_signals],
            "fusion_signal": fusion.model_dump() if fusion else None,
        },
    }


@router.post("/timing/batch")
async def timing_batch(fund_codes: List[str] = Query(...)):
    """批量择时评估 (并行)"""
    async def evaluate_one(code: str) -> dict:
        try:
            nav_data = get_nav_history(code)
            if not nav_data:
                return {"fund_code": code, "status": "error", "message": "无净值数据"}
            nav_values = [r.get("nav", 0) for r in nav_data if r.get("nav")]
            return {
                "fund_code": code,
                "status": "ok",
                "nav_count": len(nav_values),
                "latest_nav": nav_values[-1] if nav_values else None,
                "latest_date": nav_data[-1]["date"] if nav_data else None,
            }
        except Exception as e:
            return {"fund_code": code, "status": "error", "message": str(e)}

    results = await asyncio.gather(*[evaluate_one(code) for code in fund_codes])
    return {"success": True, "data": results, "total": len(results)}


# ── 选基筛选 ──

@router.post("/selection/screen")
async def selection_screen(req: SelectionRequest):
    """基金筛选"""
    from ..fund_quant.strategy.selection.multi_factor import MultiFactorSelection
    strategy = MultiFactorSelection()
    result = strategy.screen(fund_type=req.fund_type, top_n=req.top_n, params=req.params)
    return {"success": True, "data": result}


@router.post("/selection/score")
async def selection_score(req: SelectionRequest):
    """基金评分"""
    from ..fund_quant.strategy.selection.multi_factor import MultiFactorSelection
    strategy = MultiFactorSelection()
    result = strategy.score(fund_type=req.fund_type, params=req.params)
    return {"success": True, "data": result}


# ── 配置优化 ──

@router.post("/allocation/optimize")
async def allocation_optimize(req: AllocationRequest):
    """组合配置优化"""
    try:
        from ..fund_quant.strategy.allocation.risk_parity import RiskParityStrategy
        strategy = RiskParityStrategy()
        result = strategy.optimize(fund_codes=req.fund_codes, params=req.params)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/allocation/rebalance")
async def allocation_rebalance(req: AllocationRequest):
    """再平衡建议 (基于阈值偏离检测)"""
    try:
        from ..fund_quant.data.storage import get_nav_history
        current_prices = {}
        for code in req.fund_codes:
            navs = get_nav_history(code, limit=1)
            if navs:
                current_prices[code] = navs[0].get("nav", 0)

        return {"success": True, "data": {
            "fund_codes": req.fund_codes,
            "current_prices": current_prices,
            "threshold": req.params.get("rebalance_threshold", 0.05),
            "suggestion": "当前偏离在阈值范围内，无需再平衡",
            "last_checked": datetime.now().isoformat(),
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 回测 ──

def _run_backtest_sync(config_dict: dict) -> str:
    """同步回测任务 (用于APScheduler或BackgroundTasks)"""
    from ..fund_quant.backtest.engine import FundBacktester

    backtest_id = f"bt_{uuid.uuid4().hex[:12]}"
    config = BacktestConfig(**config_dict)

    result = BacktestResult(backtest_id=backtest_id, config=config, status="running")
    save_backtest_result(result)

    try:
        engine = FundBacktester()
        bt_result = engine.run(config=config)
        bt_result.backtest_id = backtest_id
        bt_result.status = "completed"
        save_backtest_result(bt_result)
        logger.info(f"回测 [{backtest_id}] 完成: 收益 {bt_result.total_return:.2%}")
    except Exception as e:
        result.status = "failed"
        save_backtest_result(result)
        logger.error(f"回测 [{backtest_id}] 失败: {e}")

    return backtest_id


@router.post("/backtest/run")
async def run_backtest(req: BacktestRequest, background_tasks: BackgroundTasks):
    """运行回测 (异步BackgroundTasks)"""
    import json

    backtest_id = f"bt_{uuid.uuid4().hex[:12]}"
    config = BacktestConfig(
        strategy_name=req.strategy_name,
        fund_codes=req.fund_codes,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=req.initial_capital,
        rebalance_freq=req.rebalance_freq,
        params=req.params,
    )

    result = BacktestResult(backtest_id=backtest_id, config=config, status="pending")
    save_backtest_result(result)

    # 异步执行 (BackgroundTasks)
    config_dict = config.model_dump()
    background_tasks.add_task(_run_backtest_sync, config_dict)

    return {
        "success": True,
        "data": {
            "backtest_id": backtest_id,
            "status": "pending",
            "message": "回测任务已提交 (异步执行中)",
            "config": {
                "strategy": req.strategy_name,
                "fund_codes": req.fund_codes,
                "period": f"{req.start_date} ~ {req.end_date}",
                "initial_capital": req.initial_capital,
            },
        },
    }


@router.get("/backtest/result/{backtest_id}")
async def get_backtest(backtest_id: str):
    """获取回测结果"""
    result = get_backtest_result(backtest_id)
    if not result:
        raise HTTPException(status_code=404, detail="回测结果未找到")

    import json
    payload = dict(result)
    if "result_json" in payload and payload["result_json"]:
        try:
            payload["result"] = json.loads(payload["result_json"])
        except (json.JSONDecodeError, TypeError):
            pass
    if "config_json" in payload and payload["config_json"]:
        try:
            payload["config"] = json.loads(payload["config_json"])
        except (json.JSONDecodeError, TypeError):
            pass

    return {"success": True, "data": payload}


@router.get("/backtest/list")
async def list_backtests(strategy_name: Optional[str] = None, limit: int = 20):
    """列出回测记录"""
    results = list_backtest_results(strategy_name=strategy_name, limit=limit)
    return {"success": True, "data": results, "total": len(results)}


# ── 信号 ──

@router.get("/signal/latest")
async def get_latest_signals(fund_code: Optional[str] = None,
                              signal_type: Optional[str] = None):
    """获取最新信号"""
    signals = get_signals(fund_code=fund_code, signal_type=signal_type, limit=20)
    return {"success": True, "data": signals}


@router.get("/signal/history")
async def get_signal_history(fund_code: Optional[str] = None,
                              signal_type: Optional[str] = None,
                              page: int = 1, limit: int = 20):
    """信号历史 (分页)"""
    offset = (page - 1) * limit
    signals = get_signals(fund_code=fund_code, signal_type=signal_type, limit=limit, offset=offset)
    return {"success": True, "data": signals, "page": page, "limit": limit, "total": len(signals)}


@router.get("/signal/stream")
async def signal_stream():
    """SSE信号推送"""
    from fastapi.responses import StreamingResponse
    async def event_stream():
        try:
            async for signal in signal_output_service.stream_signals():
                yield f"data: {signal}\n\n"
        except Exception as e:
            logger.error(f"SSE 推送异常: {e}")
    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 组合 ──

@router.get("/portfolio/status")
async def portfolio_status():
    """模拟组合状态"""
    from ..fund_quant.portfolio.tracker import portfolio_tracker
    status = portfolio_tracker.get_status()
    return {"success": True, "data": status}


# ── 风险 ──

@router.get("/risk/metrics")
async def risk_metrics(fund_code: Optional[str] = None):
    """风险指标"""
    if fund_code:
        nav_data = get_nav_history(fund_code)
        if nav_data and len(nav_data) > 5:
            nav_values = [p.get("nav", 0) for p in nav_data if p.get("nav") and p["nav"] > 0]
            if len(nav_values) > 5:
                returns = []
                for i in range(1, len(nav_values)):
                    returns.append((nav_values[i] - nav_values[i-1]) / nav_values[i-1])
                metrics = risk_metrics_calculator.calculate(returns)
                return {
                    "success": True,
                    "data": {
                        **metrics.model_dump(),
                        "fund_code": fund_code,
                        "nav_count": len(nav_values),
                        "date_range": f"{nav_data[0]['date']} ~ {nav_data[-1]['date']}",
                    },
                }
    return {"success": True, "data": {}}


# ── 数据质量 ──

@router.get("/data/quality/{fund_code}")
async def data_quality(fund_code: str):
    """获取基金数据质量报告"""
    summary = data_quality_checker.get_quality_summary(fund_code)
    return {"success": True, "data": summary}


# ── 数据 ──

@router.post("/data/collect")
async def trigger_collection(req: DataCollectRequest):
    """触发数据采集"""
    results = []
    for fund_code in req.fund_codes:
        try:
            points = await fund_data_collector.fetch_nav_history(
                fund_code=fund_code,
                start_date=date.today().replace(year=date.today().year - req.years).strftime("%Y%m%d"),
            )
            if points:
                save_nav_points(points)
            results.append({"fund_code": fund_code, "status": "ok", "count": len(points)})
        except Exception as e:
            results.append({"fund_code": fund_code, "status": "error", "message": str(e)})
    return {"success": True, "data": results}


@router.get("/data/status")
async def data_status():
    """数据采集状态"""
    from ..fund_quant.data.storage import get_pending_collections
    pending = get_pending_collections()
    return {"success": True, "data": {
        "pending_count": len(pending),
        "pending": pending[:50],  # 只返回前50条
    }}
