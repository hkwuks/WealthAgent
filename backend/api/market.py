from fastapi import APIRouter, Query
from typing import Optional
from backend.market_data import market_data_service, INDEX_MAPPING, GLOBAL_INDEX_MAPPING
from backend.api.schemas import (
    MarketDataResponse,
    IndexDataResponse,
    EtfDataResponse,
)
from backend.models import AssetType, MarketData
from loguru import logger


router = APIRouter(prefix="/market", tags=["市场数据"])


@router.get(
    "/stock/{stock_code}",
    response_model=MarketDataResponse,
    summary="获取股票实时行情",
    description="获取A股股票的实时价格和涨跌幅"
)
async def get_stock_price(stock_code: str):
    """
    获取股票实时行情
    
    - **stock_code**: 股票代码（如 600519, 000858）
    """
    try:
        data = await market_data_service.get_stock_price(stock_code)
        
        if not data:
            return MarketDataResponse(
                success=False,
                message=f"未找到股票 {stock_code} 的行情数据",
                data=None
            )
        
        return MarketDataResponse(
            success=True,
            message="获取成功",
            data=data
        )
    except Exception as e:
        logger.error(f"获取股票行情失败: {stock_code}, {e}")
        return MarketDataResponse(
            success=False,
            message=f"获取股票行情失败: {str(e)}",
            data=None
        )


@router.get(
    "/etf/{etf_code}",
    response_model=EtfDataResponse,
    summary="获取ETF实时行情",
    description="获取场内ETF的实时价格、涨跌幅、成交量等信息"
)
async def get_etf_price(etf_code: str):
    """
    获取ETF实时行情
    
    - **etf_code**: ETF代码（如 510300, 159915）
    """
    try:
        data = await market_data_service.get_etf_realtime_data(etf_code)
        
        if not data:
            return EtfDataResponse(
                success=False,
                message=f"未找到ETF {etf_code} 的行情数据",
                data=None
            )
        
        return EtfDataResponse(
            success=True,
            message="获取成功",
            data=data
        )
    except Exception as e:
        logger.error(f"获取ETF行情失败: {etf_code}, {e}")
        return EtfDataResponse(
            success=False,
            message=f"获取ETF行情失败: {str(e)}",
            data=None
        )


@router.get(
    "/index/{index_code}",
    response_model=IndexDataResponse,
    summary="获取指数实时行情",
    description="获取国内指数（沪深300、中证500等）的实时数据"
)
async def get_index_price(index_code: str):
    """
    获取指数实时行情
    
    - **index_code**: 指数代码（如 000300, 000905, 399006）
    """
    try:
        data = await market_data_service.get_index_realtime_data(index_code)
        
        if not data:
            return IndexDataResponse(
                success=False,
                message=f"未找到指数 {index_code} 的行情数据",
                data=None
            )
        
        return IndexDataResponse(
            success=True,
            message="获取成功",
            data=data
        )
    except Exception as e:
        logger.error(f"获取指数行情失败: {index_code}, {e}")
        return IndexDataResponse(
            success=False,
            message=f"获取指数行情失败: {str(e)}",
            data=None
        )


@router.get(
    "/global-index/{index_code}",
    response_model=IndexDataResponse,
    summary="获取海外指数实时行情",
    description="获取海外指数（纳斯达克、标普500、恒生等）的实时数据"
)
async def get_global_index_price(index_code: str):
    """
    获取海外指数实时行情
    
    - **index_code**: 指数代码（如 nasdaq, sp500, hsi）
    """
    try:
        data = await market_data_service.get_global_index_realtime_data(index_code)
        
        if not data:
            return IndexDataResponse(
                success=False,
                message=f"未找到海外指数 {index_code} 的行情数据",
                data=None
            )
        
        return IndexDataResponse(
            success=True,
            message="获取成功",
            data=data
        )
    except Exception as e:
        logger.error(f"获取海外指数行情失败: {index_code}, {e}")
        return IndexDataResponse(
            success=False,
            message=f"获取海外指数行情失败: {str(e)}",
            data=None
        )


@router.get(
    "/indices",
    summary="获取支持的指数列表",
    description="获取系统支持的国内指数和海外指数列表"
)
async def get_supported_indices():
    """获取支持的指数列表"""
    return {
        "success": True,
        "message": "获取成功",
        "data": {
            "domestic": {
                code: info["name"] for code, info in INDEX_MAPPING.items()
            },
            "global": {
                code: info["name"] for code, info in GLOBAL_INDEX_MAPPING.items()
            }
        }
    }


@router.post(
    "/cache/clear",
    summary="清除缓存",
    description="清除市场数据缓存"
)
async def clear_cache():
    """清除市场数据缓存"""
    try:
        market_data_service.clear_cache()
        return {"success": True, "message": "缓存清除成功"}
    except Exception as e:
        logger.error(f"清除缓存失败: {e}")
        return {"success": False, "message": f"清除缓存失败: {str(e)}"}
