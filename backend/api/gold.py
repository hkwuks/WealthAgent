"""
黄金预测API路由
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import numpy as np

from backend.gold_prediction import (
    GoldPricePredictor, ModelType, PredictionHorizon,
    PredictionResult, TripleBarrierResult, TripleBarrierLabeler,
    model_manager, FeatureEngineer
)
from backend.data_sync import get_gold_training_data, data_sync
from backend.data_store import data_store
from loguru import logger

router = APIRouter(prefix="/gold", tags=["黄金预测"])


class GoldPredictionResponse(BaseModel):
    """黄金预测响应"""
    asset_code: str
    current_price: float
    predicted_price: float
    predicted_change: float
    predicted_change_percent: float
    confidence: float
    horizon_days: int
    model_type: str
    timestamp: datetime
    features_used: List[str]


class GoldHistoryResponse(BaseModel):
    """黄金历史数据响应"""
    symbol: str
    data_points: int
    date_range: dict
    latest_price: float
    price_change_24h: float


class TrainingStatusResponse(BaseModel):
    """训练状态响应"""
    status: str
    model_type: str
    horizon: int
    metrics: Optional[dict] = None
    message: str


@router.post("/predict")
async def predict_gold_price(
    symbol: str = Query("GC", description="黄金代码: GC=COMEX, XAU=现货"),
    horizon_days: int = Query(1, description="预测周期: 1=1天, 5=1周, 20=1月"),
    model_type: str = Query("lightgbm", description="模型类型: lightgbm, xgboost, ridge")
):
    """
    预测黄金价格

    使用缓存的模型进行预测，如无缓存则自动训练。
    """
    try:
        df = get_gold_training_data(symbol, lookback_days=2520)

        if df.empty or len(df) < 100:
            raise HTTPException(status_code=400, detail="Insufficient historical data")

        # 按日期升序排序（确保最新数据在最后）
        df = df.sort_values('date').reset_index(drop=True)

        # 排除当天数据
        if 'date' in df.columns:
            today_str = datetime.now().strftime('%Y-%m-%d')
            today_mask = df['date'] == today_str
            if today_mask.any():
                df = df[~today_mask].copy()
                df = df.sort_values('date').reset_index(drop=True)

        if len(df) < 100:
            raise HTTPException(status_code=400, detail="Insufficient historical data after excluding today")

        # 映射参数
        horizon_map = {1: PredictionHorizon.SHORT, 5: PredictionHorizon.MEDIUM, 20: PredictionHorizon.LONG}
        horizon = horizon_map.get(horizon_days, PredictionHorizon.SHORT)

        model_map = {"lightgbm": ModelType.LIGHTGBM, "xgboost": ModelType.XGBOOST, "ridge": ModelType.RIDGE}
        model = model_map.get(model_type.lower(), ModelType.LIGHTGBM)

        # 使用ModelManager获取或训练模型
        predictor, train_result = model_manager.get_or_train(df, model, horizon)
        result = predictor.predict(df, model, horizon, use_last_known_price=True)

        # 记录预测方向（用于漂移检测）
        predicted_dir = 1 if result.predicted_change_percent > 0 else (-1 if result.predicted_change_percent < 0 else 0)
        model_manager.record_prediction(model, horizon, predicted_dir)

        return {
            "success": True,
            "data": {
                "asset_code": result.asset_code,
                "current_price": result.current_price,
                "predicted_price": result.predicted_price,
                "predicted_change": result.predicted_change,
                "predicted_change_percent": result.predicted_change_percent,
                "confidence": result.confidence,
                "horizon_days": result.horizon,
                "model_type": result.model_type,
                "timestamp": result.timestamp.isoformat() if hasattr(result.timestamp, 'isoformat') else result.timestamp,
                "features_used": result.features_used[:10]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predict-tb", response_model=dict)
async def predict_triple_barrier(
    symbol: str = Query("GC", description="黄金代码"),
    model_type: str = Query("lightgbm", description="模型类型: lightgbm, xgboost, ridge")
):
    """
    Triple-Barrier 预测：预测方向概率而非价格

    返回看涨/看跌方向及概率，同时给出止盈止损价格。
    """
    try:
        df = get_gold_training_data(symbol, lookback_days=2520)

        if df.empty or len(df) < 100:
            raise HTTPException(status_code=400, detail="Insufficient historical data")

        # 按日期升序排序（确保最新数据在最后）
        df = df.sort_values('date').reset_index(drop=True)

        model_map = {"lightgbm": ModelType.LIGHTGBM, "xgboost": ModelType.XGBOOST, "ridge": ModelType.RIDGE}
        model = model_map.get(model_type.lower(), ModelType.LIGHTGBM)

        # 使用缓存或训练新模型
        tb_key = f"tb_{model.value}"
        predictor = model_manager.get_predictor(model, PredictionHorizon.SHORT)

        # 检查是否有TB模型（tb_前缀的模型在predictor.models中）
        if predictor is None or tb_key not in predictor.models:
            predictor = GoldPricePredictor()
            predictor.train_tb(df, model)
            model_manager.save_predictor(predictor, model, PredictionHorizon.SHORT,
                                         {'mode': 'triple_barrier'}, mode='triple_barrier')

        result = predictor.predict_tb(df, model)

        return {
            "success": True,
            "data": {
                "asset_code": result.asset_code,
                "current_price": result.current_price,
                "direction": result.direction,
                "direction_label": "看涨" if result.direction == 1 else "看跌",
                "direction_probability": result.direction_probability,
                "tp_level": result.tp_level,
                "sl_level": result.sl_level,
                "max_holding_days": result.max_holding_days,
                "atr_value": result.atr_value,
                "confidence": result.confidence,
                "model_type": result.model_type,
                "features_used": result.features_used[:10],
                "timestamp": result.timestamp.isoformat(),
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TB prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retrain", response_model=TrainingStatusResponse)
async def force_retrain(
    model_type: str = Query("lightgbm", description="模型类型: lightgbm, xgboost, ridge"),
    horizon_days: int = Query(1, description="预测周期: 1=1天, 5=1周, 20=1月"),
    symbol: str = Query("GC", description="黄金代码")
):
    """强制重新训练模型"""
    try:
        df = get_gold_training_data(symbol, lookback_days=2520)

        if df.empty or len(df) < 100:
            raise HTTPException(status_code=400, detail="Insufficient historical data")

        horizon_map = {1: PredictionHorizon.SHORT, 5: PredictionHorizon.MEDIUM, 20: PredictionHorizon.LONG}
        horizon = horizon_map.get(horizon_days, PredictionHorizon.SHORT)

        model_map = {"lightgbm": ModelType.LIGHTGBM, "xgboost": ModelType.XGBOOST, "ridge": ModelType.RIDGE}
        mt = model_map.get(model_type.lower(), ModelType.LIGHTGBM)

        # 清除缓存，强制重训
        model_manager.invalidate(mt, horizon)

        predictor = GoldPricePredictor()
        train_result = predictor.train(df, mt, horizon)
        model_manager.save_predictor(predictor, mt, horizon, train_result.get('metrics'))

        return TrainingStatusResponse(
            status="success",
            model_type=mt.value,
            horizon=horizon.value,
            metrics=train_result.get('metrics'),
            message="Model retrained successfully"
        )

    except Exception as e:
        logger.error(f"Retrain failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=GoldHistoryResponse)
async def get_gold_history(
    symbol: str = Query("GC", description="黄金代码"),
    days: int = Query(365, description="历史数据天数")
):
    """获取黄金历史数据概况"""
    try:
        from datetime import timedelta

        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        df = data_store.get_price_history(
            asset_code=symbol,
            asset_type='gold',
            start_date=start_date,
            end_date=end_date,
            as_dataframe=True
        )

        if df.empty:
            data_sync.sync_gold_history(symbol, period=f"{days//365}y")
            df = data_store.get_price_history(
                asset_code=symbol,
                asset_type='gold',
                start_date=start_date,
                end_date=end_date,
                as_dataframe=True
            )

        if df.empty:
            raise HTTPException(status_code=404, detail="No historical data available")

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        return GoldHistoryResponse(
            symbol=symbol,
            data_points=len(df),
            date_range={
                "start": df['date'].min(),
                "end": df['date'].max()
            },
            latest_price=latest['close'],
            price_change_24h=latest['close'] - prev['close']
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync", response_model=dict)
async def sync_gold_data(
    years: int = Query(5, description="同步年数")
):
    """同步黄金历史数据"""
    try:
        results = data_sync.sync_all_gold_data(years)

        return {
            "status": "success",
            "sync_results": {
                symbol: {"success": success, "records": count}
                for symbol, (success, count) in results.items()
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/current", response_model=dict)
async def get_gold_current(
    symbol: str = Query("GC", description="黄金代码")
):
    """获取黄金当前价格和宏观指标"""
    try:
        # 查询更长的历史数据（500天），确保能获取到宏观数据
        df = get_gold_training_data(symbol, lookback_days=500)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        # 按日期升序排序（确保最新数据在最后）
        df = df.sort_values('date').reset_index(drop=True)

        # 计算技术指标
        fe = FeatureEngineer()
        df = fe.create_technical_features(df)
        df = fe.create_macro_features(df)

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        # 计算金价变化百分比
        gold_price = latest.get('close')
        prev_price = prev.get('close')
        gold_change_percent = ((gold_price - prev_price) / prev_price * 100) if prev_price and prev_price > 0 else 0

        return {
            "success": True,
            "data": {
                "gold_price": round(gold_price, 2) if gold_price is not None else None,
                "gold_change_percent": round(gold_change_percent, 2),
                "dxy": round(latest.get('DXY_value'), 2) if latest.get('DXY_value') is not None else None,
                "vix": round(latest.get('VIX_value'), 2) if latest.get('VIX_value') is not None else None,
                "us10y": round(latest.get('US10Y_value'), 2) if latest.get('US10Y_value') is not None else None,
                "tips": round(latest.get('TIPS_value'), 2) if latest.get('TIPS_value') is not None else None,
                "breakeven": round(latest.get('BREAKEVEN_level'), 2) if latest.get('BREAKEVEN_level') is not None else None,
                "rsi_14": round(latest.get('rsi_14'), 2) if latest.get('rsi_14') is not None else None,
                "atr_ratio": round(latest.get('atr_ratio'), 4) if latest.get('atr_ratio') is not None else None,
                "bb_position": round(latest.get('bb_position'), 4) if latest.get('bb_position') is not None else None,
                "timestamp": datetime.now().isoformat()
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/factors", response_model=dict)
async def get_gold_factors(
    symbol: str = Query("GC", description="黄金代码")
):
    """获取黄金相关因子数据"""
    try:
        # 查询更长的历史数据（500天），确保能获取到宏观数据
        df = get_gold_training_data(symbol, lookback_days=500)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        # 按日期升序排序（确保最新数据在最后）
        df = df.sort_values('date').reset_index(drop=True)

        # 计算技术指标
        fe = FeatureEngineer()
        df = fe.create_technical_features(df)
        df = fe.create_macro_features(df)

        latest = df.iloc[-1]

        factors = {
            "price_factors": {
                "current_price": round(latest.get('close'), 2) if latest.get('close') is not None else None,
                "rsi_14": round(latest.get('rsi_14'), 2) if latest.get('rsi_14') is not None else None,
                "atr_ratio": round(latest.get('atr_ratio'), 4) if latest.get('atr_ratio') is not None else None,
                "bb_position": round(latest.get('bb_position'), 4) if latest.get('bb_position') is not None else None,
                "ma_ratio_20": round(latest.get('ma_ratio_20'), 4) if latest.get('ma_ratio_20') is not None else None,
                "ma_ratio_60": round(latest.get('ma_ratio_60'), 4) if latest.get('ma_ratio_60') is not None else None,
            },
            "macro_factors": {
                "dxy": round(latest.get('DXY_value'), 2) if latest.get('DXY_value') is not None else None,
                "vix": round(latest.get('VIX_value'), 2) if latest.get('VIX_value') is not None else None,
                "us10y": round(latest.get('US10Y_value'), 2) if latest.get('US10Y_value') is not None else None,
                "tips": round(latest.get('TIPS_value'), 2) if latest.get('TIPS_value') is not None else None,
                "breakeven": round(latest.get('BREAKEVEN_level'), 2) if latest.get('BREAKEVEN_level') is not None else None,
            },
            "timestamp": datetime.now().isoformat()
        }

        return factors

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/drift-status", response_model=dict)
async def get_drift_status(
    model_type: str = Query(None, description="模型类型（可选）"),
    horizon_days: int = Query(None, description="预测周期（可选）")
):
    """获取模型漂移检测状态"""
    try:
        model_map = {"lightgbm": ModelType.LIGHTGBM, "xgboost": ModelType.XGBOOST, "ridge": ModelType.RIDGE}
        horizon_map = {1: PredictionHorizon.SHORT, 5: PredictionHorizon.MEDIUM, 20: PredictionHorizon.LONG}

        mt = model_map.get(model_type.lower()) if model_type else None
        h = horizon_map.get(horizon_days) if horizon_days else None

        status = model_manager.get_drift_status(mt, h)
        return {"success": True, "data": status}

    except Exception as e:
        logger.error(f"Drift status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/record-actual", response_model=dict)
async def record_actual_direction(
    date: str = Query(..., description="日期 YYYY-MM-DD"),
    actual_direction: int = Query(..., description="实际方向: 1=涨, -1=跌, 0=平"),
    model_type: str = Query("lightgbm", description="模型类型"),
    horizon_days: int = Query(1, description="预测周期")
):
    """记录实际价格方向（用于漂移检测）"""
    try:
        model_map = {"lightgbm": ModelType.LIGHTGBM, "xgboost": ModelType.XGBOOST, "ridge": ModelType.RIDGE}
        horizon_map = {1: PredictionHorizon.SHORT, 5: PredictionHorizon.MEDIUM, 20: PredictionHorizon.LONG}
        mt = model_map.get(model_type.lower(), ModelType.LIGHTGBM)
        h = horizon_map.get(horizon_days, PredictionHorizon.SHORT)

        model_manager.record_actual(mt, h, date, actual_direction)
        return {"success": True, "message": f"Recorded actual direction for {date}"}

    except Exception as e:
        logger.error(f"Record actual failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/factor-importance", response_model=dict)
async def get_factor_importance(
    model_type: str = Query("lightgbm", description="模型类型: lightgbm, xgboost, ridge"),
    horizon_days: int = Query(1, description="预测周期: 1=1天, 5=1周, 20=1月"),
    symbol: str = Query("GC", description="黄金代码")
):
    """获取因子重要性（MI + SHAP/feature_importance）"""
    try:
        model_map = {"lightgbm": ModelType.LIGHTGBM, "xgboost": ModelType.XGBOOST, "ridge": ModelType.RIDGE}
        mt = model_map.get(model_type.lower(), ModelType.LIGHTGBM)

        horizon_map = {1: PredictionHorizon.SHORT, 5: PredictionHorizon.MEDIUM, 20: PredictionHorizon.LONG}
        horizon = horizon_map.get(horizon_days, PredictionHorizon.SHORT)

        predictor = model_manager.get_predictor(mt, horizon)
        if predictor is None:
            raise HTTPException(status_code=404, detail="Model not trained yet. Run prediction first.")

        importance = predictor.compute_factor_importance(mt)
        return {"success": True, "data": importance}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Factor importance failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/coverage", response_model=dict)
async def get_data_coverage():
    """获取数据覆盖情况"""
    try:
        coverage = data_store.get_data_coverage()
        return coverage
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backtest")
async def run_backtest(
    years: int = Query(1, ge=1, le=5, description="回测年数"),
    model_types: str = Query("lightgbm,xgboost,ridge", description="模型类型，逗号分隔"),
    horizon_days: int = Query(1, ge=1, le=20, description="预测周期: 1=1天, 5=1周, 20=1月"),
    method: str = Query("walk_forward", description="回测方法: walk_forward, cpcv")
):
    """运行模型回测（支持 Walk-Forward 和 CPCV）"""
    from backend.backtest_engine import BacktestEngine, CPCVEngine

    model_map = {
        "lightgbm": ModelType.LIGHTGBM,
        "xgboost": ModelType.XGBOOST,
        "ridge": ModelType.RIDGE
    }
    selected_models = []
    for mt in model_types.split(","):
        if mt.strip() in model_map:
            selected_models.append(model_map[mt.strip()])

    if not selected_models:
        selected_models = [ModelType.LIGHTGBM, ModelType.RIDGE]

    lookback_days = years * 252 + 300
    df = get_gold_training_data("GC", lookback_days=lookback_days)

    if df.empty or len(df) < years * 252:
        raise HTTPException(status_code=400, detail="Insufficient data for backtest")

    horizon_map = {1: PredictionHorizon.SHORT, 5: PredictionHorizon.MEDIUM, 20: PredictionHorizon.LONG}
    horizon = horizon_map.get(horizon_days, PredictionHorizon.SHORT)

    if method == "cpcv":
        engine = CPCVEngine()
        results = engine.run_cpcv(df, selected_models, horizon)
        backtest_method = "cpcv"
    else:
        engine = BacktestEngine(train_window=252, test_window=horizon_days)
        results = engine.run_backtest(df, selected_models, horizon)
        backtest_method = "walk_forward"

    return {
        "success": True,
        "data": {
            "backtest_id": f"bt_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "method": backtest_method,
            "period_years": years,
            "period_days": len(df),
            "horizon_days": horizon_days,
            "results": results
        }
    }


@router.post("/backtest-trend", response_model=dict)
async def run_trend_following_backtest(
    years: int = Query(2, ge=1, le=5, description="回测年数"),
    fast_ma: int = Query(50, ge=10, le=100, description="快速MA天数"),
    slow_ma: int = Query(200, ge=50, le=300, description="慢速MA天数"),
    sl_multiplier: float = Query(2.0, ge=0.5, le=5.0, description="ATR止损倍数"),
    symbol: str = Query("GC", description="黄金代码")
):
    """
    运行趋势跟踪策略回测

    50/200日MA交叉 + ATR止损策略
    """
    from backend.backtest_engine import TrendFollowingStrategy, CostModel

    lookback_days = years * 252 + 300
    df = get_gold_training_data(symbol, lookback_days=lookback_days)

    if df.empty or len(df) < slow_ma + 50:
        raise HTTPException(status_code=400, detail="Insufficient data for trend backtest")

    strategy = TrendFollowingStrategy(
        fast_ma=fast_ma,
        slow_ma=slow_ma,
        sl_multiplier=sl_multiplier,
    )
    results = strategy.run_backtest(df)

    return {
        "success": True,
        "data": {
            "backtest_id": f"trend_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "period_years": years,
            "period_days": len(df),
            "results": results
        }
    }


@router.get("/trend-signal", response_model=dict)
async def get_trend_signal(
    symbol: str = Query("GC", description="黄金代码")
):
    """
    获取当前趋势跟踪信号

    返回当前MA交叉状态和持仓建议
    """
    from backend.backtest_engine import TrendFollowingStrategy

    df = get_gold_training_data(symbol, lookback_days=500)

    if df.empty or len(df) < 210:
        raise HTTPException(status_code=400, detail="Insufficient data for trend signal")

    # 按日期升序排序（确保最新数据在最后）
    df = df.sort_values('date').reset_index(drop=True)

    close = df['close']
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    atr = TrendFollowingStrategy().compute_atr_for_signal(df)

    current_price = close.iloc[-1]
    current_ma50 = ma50.iloc[-1]
    current_ma200 = ma200.iloc[-1]
    current_atr = atr.iloc[-1] if atr is not None else 0

    golden_cross = current_ma50 > current_ma200
    death_cross = current_ma50 < current_ma200

    # 计算MA交叉距离
    cross_distance_pct = ((current_ma50 - current_ma200) / current_ma200 * 100) if current_ma200 > 0 else 0

    # 计算历史信号变化（近5天的交叉状态）
    recent_signals = []
    for i in range(max(0, len(df) - 5), len(df)):
        if not np.isnan(ma50.iloc[i]) and not np.isnan(ma200.iloc[i]):
            recent_signals.append('golden' if ma50.iloc[i] > ma200.iloc[i] else 'death')

    # 最近一次信号切换日期
    last_cross_date = None
    for i in range(len(df) - 1, 200, -1):
        prev_signal = 'golden' if ma50.iloc[i-1] > ma200.iloc[i-1] else 'death'
        curr_signal = 'golden' if ma50.iloc[i] > ma200.iloc[i] else 'death'
        if prev_signal != curr_signal:
            last_cross_date = df['date'].iloc[i]
            last_cross_type = curr_signal
            break

    return {
        "success": True,
        "data": {
            "current_price": round(current_price, 2),
            "ma50": round(current_ma50, 2) if not np.isnan(current_ma50) else None,
            "ma200": round(current_ma200, 2) if not np.isnan(current_ma200) else None,
            "signal": "看涨（金叉）" if golden_cross else "看跌（死叉）" if death_cross else "无信号",
            "signal_type": "golden_cross" if golden_cross else "death_cross",
            "cross_distance_pct": round(cross_distance_pct, 2),
            "atr": round(current_atr, 4) if current_atr and not np.isnan(current_atr) else None,
            "stop_loss_level": round(current_price - current_atr * 2.0, 2) if current_atr and not np.isnan(current_atr) else None,
            "recent_signals": recent_signals,
            "last_cross_date": last_cross_date,
            "timestamp": datetime.now().isoformat(),
        }
    }
