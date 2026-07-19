import logging

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
    try:
        return await income_tax.calculate(
            income=req.income,
            expense=req.expense,
            personal_deduction_count=req.personal_deduction_count,
            other_deductions=req.other_deductions,
        )
    except Exception as e:
        logger.warning("소득세 계산 오류: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/capital-gains", response_model=CalculationResult)
async def calc_capital_gains(
    req: CapitalGainsRequest,
    user: dict = Depends(verify_token),
):
    try:
        return await capital_gains.calculate(
            transfer_price=req.transfer_price,
            acquisition_price=req.acquisition_price,
            expenses=req.expenses,
            holding_years=req.holding_years,
            asset_type=req.asset_type,
            is_one_home=req.is_one_home,
        )
    except Exception as e:
        logger.warning("양도소득세 계산 오류: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/inheritance", response_model=CalculationResult)
async def calc_inheritance(
    req: InheritanceRequest,
    user: dict = Depends(verify_token),
):
    try:
        return await inheritance.calculate(
            estate_value=req.estate_value,
            debts=req.debts,
            spouse_inheritance=req.spouse_inheritance,
            children_count=req.children_count,
        )
    except Exception as e:
        logger.warning("상속세 계산 오류: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/gift", response_model=CalculationResult)
async def calc_gift_tax(
    req: GiftTaxRequest,
    user: dict = Depends(verify_token),
):
    try:
        return await gift_tax.calculate(
            gift_amount=req.gift_amount,
            relation=req.relation,
            is_minor=req.is_minor,
            prior_gifts_10y=req.prior_gifts_10y,
        )
    except Exception as e:
        logger.warning("증여세 계산 오류: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/vat", response_model=CalculationResult)
async def calc_vat(
    req: VatRequest,
    user: dict = Depends(verify_token),
):
    try:
        return await vat.calculate(
            sales=req.sales,
            purchases=req.purchases,
            exempt_sales=req.exempt_sales,
            is_simplified=req.is_simplified,
            business_type=req.business_type,
        )
    except Exception as e:
        logger.warning("부가가치세 계산 오류: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/penalty-tax", response_model=CalculationResult)
async def calc_penalty_tax(
    req: PenaltyTaxRequest,
    user: dict = Depends(verify_token),
):
    try:
        return await penalty_tax.calculate(
            unpaid_tax=req.unpaid_tax,
            penalty_type=req.penalty_type,
            is_negligent=req.is_negligent,
            days_late=req.days_late,
        )
    except Exception as e:
        logger.warning("가산세 계산 오류: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
