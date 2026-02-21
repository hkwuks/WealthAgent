from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from backend.market_data import market_data_service
from backend.api.schemas import (
    FundInfoResponse,
    FundInfoListResponse,
    HoldingsResponse,
    NavHistoryResponse,
)
from backend.models import FundInfo
from loguru import logger


router = APIRouter(prefix="/funds", tags=["基金信息"])


@router.get(
    "/{fund_code}",
    response_model=FundInfoResponse,
    summary="获取基金信息",
    description="根据基金代码获取基金的详细信息，包括名称、类型、净值、业绩基准等"
)
async def get_fund_info(fund_code: str):
    """
    获取基金信息
    
    - **fund_code**: 基金代码（如 110022, 510300）
    """
    try:
        info = await market_data_service.get_fund_info(fund_code)
        
        if not info:
            return FundInfoResponse(
                success=False,
                message=f"未找到基金 {fund_code} 的信息",
                data=None
            )
        
        return FundInfoResponse(
            success=True,
            message="获取成功",
            data=info
        )
    except Exception as e:
        logger.error(f"获取基金信息失败: {fund_code}, {e}")
        return FundInfoResponse(
            success=False,
            message=f"获取基金信息失败: {str(e)}",
            data=None
        )


@router.post(
    "/batch",
    response_model=FundInfoListResponse,
    summary="批量获取基金信息",
    description="批量获取多个基金的信息"
)
async def get_fund_info_batch(fund_codes: list[str]):
    """
    批量获取基金信息
    
    - **fund_codes**: 基金代码列表
    """
    results = []
    
    for code in fund_codes:
        try:
            info = await market_data_service.get_fund_info(code)
            if info:
                results.append(info)
        except Exception as e:
            logger.warning(f"获取基金 {code} 信息失败: {e}")
    
    return FundInfoListResponse(
        success=True,
        message=f"成功获取 {len(results)}/{len(fund_codes)} 个基金信息",
        data=results,
        total=len(results)
    )


@router.get(
    "/{fund_code}/holdings",
    response_model=HoldingsResponse,
    summary="获取基金持仓",
    description="获取基金的最新持仓信息"
)
async def get_fund_holdings(fund_code: str):
    """
    获取基金持仓
    
    - **fund_code**: 基金代码
    """
    try:
        holdings = await market_data_service.get_fund_holdings(fund_code)
        
        if not holdings:
            return HoldingsResponse(
                success=False,
                message=f"未找到基金 {fund_code} 的持仓信息",
                data=[],
                total=0
            )
        
        return HoldingsResponse(
            success=True,
            message="获取成功",
            data=holdings,
            total=len(holdings)
        )
    except Exception as e:
        logger.error(f"获取基金持仓失败: {fund_code}, {e}")
        return HoldingsResponse(
            success=False,
            message=f"获取基金持仓失败: {str(e)}",
            data=[],
            total=0
        )


@router.get(
    "/{fund_code}/nav-history",
    response_model=NavHistoryResponse,
    summary="获取基金净值历史",
    description="获取基金的最新净值和昨日净值"
)
async def get_fund_nav_history(fund_code: str):
    """
    获取基金净值历史
    
    - **fund_code**: 基金代码
    """
    try:
        nav_history = await market_data_service.get_fund_nav_history(fund_code)
        
        if not nav_history:
            return NavHistoryResponse(
                success=False,
                message=f"未找到基金 {fund_code} 的净值历史",
                data=None
            )
        
        return NavHistoryResponse(
            success=True,
            message="获取成功",
            data=nav_history
        )
    except Exception as e:
        logger.error(f"获取基金净值历史失败: {fund_code}, {e}")
        return NavHistoryResponse(
            success=False,
            message=f"获取基金净值历史失败: {str(e)}",
            data=None
        )
