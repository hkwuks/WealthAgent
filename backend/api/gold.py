"""
黄金预测API路由
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.gold_prediction import (
    GoldPricePredictor, ModelType, PredictionHorizon,
    train_and_predict, PredictionResult
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


@router.post("/predict", response_model=GoldPredictionResponse)
async def predict_gold_price(
    symbol: str = Query("GC", description="黄金代码: GC=COMEX, XAU=现货"),
    horizon_days: int = Query(1, description="预测周期: 1=1天, 5=1周, 20=1月"),
    model_type: str = Query("xgboost", description="模型类型: xgboost, lstm"),
    exclude_today: bool = Query(True, description="是否排除当天数据以防止数据泄露")
):
    """
    预测黄金价格

    自动获取历史数据并训练模型进行预测。
    默认排除当天数据，使用上一交易日收盘价作为基准，防止数据泄露。
    """
    try:
        # 获取训练数据
        df = get_gold_training_data(symbol, lookback_days=2520)

        if df.empty or len(df) < 100:
            raise HTTPException(status_code=400, detail="Insufficient historical data")

        # 排除当天数据以防止数据泄露
        if exclude_today and 'date' in df.columns:
            from datetime import datetime
            today_str = datetime.now().strftime('%Y-%m-%d')
            # 获取今天的数据行数
            today_mask = df['date'] == today_str
            if today_mask.any():
                # 移除当天的数据
                df = df[~today_mask].copy()
                logger.info(f"Excluded today's data ({today_str}) to prevent data leakage")

        if len(df) < 100:
            raise HTTPException(status_code=400, detail="Insufficient historical data after excluding today")

        # 映射参数
        horizon_map = {1: PredictionHorizon.SHORT, 5: PredictionHorizon.MEDIUM, 20: PredictionHorizon.LONG}
        horizon = horizon_map.get(horizon_days, PredictionHorizon.SHORT)

        model_map = {"xgboost": ModelType.XGBOOST, "lstm": ModelType.LSTM}
        model = model_map.get(model_type.lower(), ModelType.XGBOOST)

        # 训练并预测
        predictor = GoldPricePredictor()
        predictor.train(df, model, horizon)
        result = predictor.predict(df, model, horizon, use_last_known_price=True)

        return GoldPredictionResponse(
            asset_code=result.asset_code,
            current_price=result.current_price,
            predicted_price=result.predicted_price,
            predicted_change=result.predicted_change,
            predicted_change_percent=result.predicted_change_percent,
            confidence=result.confidence,
            horizon_days=result.horizon,
            model_type=result.model_type,
            timestamp=result.timestamp,
            features_used=result.features_used[:10]  # 只返回前10个特征
        )

    except Exception as e:
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
            # 尝试同步数据
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


@router.get("/factors", response_model=dict)
async def get_gold_factors(
    symbol: str = Query("GC", description="黄金代码")
):
    """
    获取黄金相关因子数据

    包括技术指标和宏观指标
    """
    try:
        df = get_gold_training_data(symbol, lookback_days=252)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        # 计算最新因子值
        latest = df.iloc[-1]

        factors = {
            "price_factors": {
                "current_price": latest.get('close'),
                "ma_20": latest.get('ma_20'),
                "ma_60": latest.get('ma_60'),
                "rsi_14": latest.get('rsi_14'),
                "volatility_20": latest.get('volatility_20')
            },
            "macro_factors": {
                "dxy": latest.get('DXY_value'),
                "vix": latest.get('VIX_value'),
                "us10y": latest.get('US10Y_value')
            },
            "timestamp": datetime.now().isoformat()
        }

        return factors

    except Exception as e:
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
    model_types: str = Query("xgboost,lstm", description="模型类型，逗号分隔: xgboost, lstm"),
    horizon_days: int = Query(1, ge=1, le=20, description="预测周期: 1=1天, 5=1周, 20=1月")
):
    """
    运行模型回测

    使用滚动窗口回测（Walk-Forward Analysis）评估模型表现
    """
    from backend.backtest_engine import BacktestEngine

    # 解析模型类型
    model_map = {
        "xgboost": ModelType.XGBOOST,
        "lstm": ModelType.LSTM
    }
    selected_models = []
    for mt in model_types.split(","):
        if mt.strip() in model_map:
            selected_models.append(model_map[mt.strip()])

    if not selected_models:
        selected_models = [ModelType.XGBOOST, ModelType.LSTM]

    # 获取数据
    lookback_days = years * 252 + 300  # 额外加300天用于预热
    df = get_gold_training_data("GC", lookback_days=lookback_days)

    if df.empty or len(df) < years * 252:
        raise HTTPException(status_code=400, detail="Insufficient data for backtest")

    # 解析预测周期
    horizon_map = {1: PredictionHorizon.SHORT, 5: PredictionHorizon.MEDIUM, 20: PredictionHorizon.LONG}
    horizon = horizon_map.get(horizon_days, PredictionHorizon.SHORT)

    # 执行回测
    engine = BacktestEngine(train_window=252, test_window=horizon_days)
    results = engine.run_backtest(df, selected_models, horizon)

    return {
        "success": True,
        "data": {
            "backtest_id": f"bt_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "period_years": years,
            "period_days": len(df),
            "horizon_days": horizon_days,
            "results": results
        }
    }