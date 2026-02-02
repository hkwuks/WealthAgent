from fastapi import APIRouter
from backend.market_data import market_data_service
from backend.models import MarketData, AssetType


router = APIRouter(prefix="/market", tags=["market"])


@router.get("/price/{code}")
async def get_price(code: str, asset_type: AssetType = AssetType.STOCK):
    data = await market_data_service.get_market_data(code, asset_type)
    if not data:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Market data not found")
    return data


@router.post("/cache/clear")
async def clear_cache():
    market_data_service.clear_cache()
    return {"message": "Cache cleared successfully"}
