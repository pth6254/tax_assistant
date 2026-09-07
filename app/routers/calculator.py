import asyncio
import logging
from app.services.calculator.errors import classify_error

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.calculator import (
    CalculationResult,
    CapitalGainsRequest,
    GiftTaxRequest,
    IncomeTaxRequest,
    InheritanceRequest,
    PenaltyTaxRequest,
    VatRequest,
)
from app.services.calculator import capital_gains, gift_tax, income_tax, inheritance, penalty_tax, vat
from app.core.security import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/calculator", tags=["calculator"])


@router.post("/income-tax", response_model=CalculationResult)
async def calc_income_tax(
    req: IncomeTaxRequest,
    user: dict = Depends(verify_token),
):
    return await _calculate(income_tax.calculate, req)


@router.post("/capital-gains", response_model=CalculationResult)
async def calc_capital_gains(
    req: CapitalGainsRequest,
    user: dict = Depends(verify_token),
):
    return await _calculate(capital_gains.calculate, req)


@router.post("/inheritance", response_model=CalculationResult)
async def calc_inheritance(
    req: InheritanceRequest,
    user: dict = Depends(verify_token),
):
    return await _calculate(inheritance.calculate, req)


@router.post("/gift", response_model=CalculationResult)
async def calc_gift_tax(
    req: GiftTaxRequest,
    user: dict = Depends(verify_token),
):
    return await _calculate(gift_tax.calculate, req)


@router.post("/vat", response_model=CalculationResult)
async def calc_vat(
    req: VatRequest,
    user: dict = Depends(verify_token),
):
    return await _calculate(vat.calculate, req)


@router.post("/penalty-tax", response_model=CalculationResult)
async def calc_penalty_tax(
    req: PenaltyTaxRequest,
    user: dict = Depends(verify_token),
):
    return await _calculate(penalty_tax.calculate, req)


async def _calculate(calculate, request):
    try:
        async with asyncio.timeout(30):
            return await calculate(**request.model_dump())
    except Exception as exc:
        error = classify_error(exc, operation=calculate.__module__)
        raise HTTPException(status_code=error.http_status, detail=error.detail()) from exc
