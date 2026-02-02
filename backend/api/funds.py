from fastapi import APIRouter, HTTPException
from typing import List
from backend.models import Fund, FundListResponse, ValuationRequest, ValuationResult, FundInfo
from backend.fund_service import fund_service
from backend.market_data import get_fund_info


router = APIRouter(prefix="/funds", tags=["funds"])


@router.get("", response_model=FundListResponse)
async def get_funds():
    funds = fund_service.load_funds()
    return FundListResponse(funds=funds, total=len(funds))


@router.get("/{fund_code}", response_model=Fund)
async def get_fund(fund_code: str):
    fund = fund_service.get_fund(fund_code)
    if not fund:
        raise HTTPException(status_code=404, detail="Fund not found")
    return fund


@router.get("/info/{fund_code}", response_model=FundInfo)
async def get_fund_info_endpoint(fund_code: str):
    info = await get_fund_info(fund_code)
    if not info:
        raise HTTPException(status_code=404, detail="Fund info not found")
    return info


@router.post("", response_model=Fund)
async def create_fund(fund: Fund):
    return fund_service.add_fund(fund)


@router.delete("/{fund_code}")
async def delete_fund(fund_code: str):
    success = fund_service.delete_fund(fund_code)
    if not success:
        raise HTTPException(status_code=404, detail="Fund not found")
    return {"message": "Fund deleted successfully"}


@router.post("/valuation", response_model=List[ValuationResult])
async def calculate_valuation(request: ValuationRequest):
    results = await fund_service.calculate_batch_valuation(request.fund_codes)
    if not results:
        raise HTTPException(status_code=404, detail="No funds found")
    return results
