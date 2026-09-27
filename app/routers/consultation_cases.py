"""Authenticated income-tax consultation workspace API."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.security import verify_token
from app.schemas.consultation_case import CaseCreate, CaseDocumentUpdate, CaseFactsPatch
from app.services import consultation_case_service as cases
from app.services.consultation_report_service import build_report
from app.services.calculator.errors import classify_error


router = APIRouter(prefix='/api/consultation-cases', tags=['consultation-cases'])


class ScenarioCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)


class ApplyReviewedField(BaseModel):
    model_config = ConfigDict(extra='forbid')
    filename: str = Field(min_length=1, max_length=255)
    field_key: str = Field(min_length=1, max_length=80)


@router.get('')
async def list_cases(user: dict = Depends(verify_token)):
    return await cases.list_cases(user['id'])


@router.post('', status_code=201)
async def create_case(body: CaseCreate, user: dict = Depends(verify_token)):
    return await cases.create_case(user['id'], body)


@router.get('/{case_id}')
async def get_case(case_id: str, user: dict = Depends(verify_token)):
    return await cases.get_case(case_id, user['id'])


@router.get('/{case_id}/report.pdf')
async def report(case_id: str, user: dict = Depends(verify_token)):
    detail = await cases.get_case(case_id, user['id'])
    return Response(build_report(detail), media_type='application/pdf', headers={
        'Content-Disposition': 'attachment; filename="consultation-report.pdf"',
        'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
    })


@router.get('/{case_id}/scenarios')
async def scenarios(case_id: str, user: dict = Depends(verify_token)):
    return await cases.list_scenarios(case_id, user['id'])


@router.post('/{case_id}/scenarios', status_code=201)
async def save_scenario(case_id: str, body: ScenarioCreate, user: dict = Depends(verify_token)):
    return await cases.save_scenario(case_id, user['id'], body.name.strip())


@router.delete('/{case_id}/scenarios/{scenario_id}')
async def delete_scenario(case_id: str, scenario_id: str, user: dict = Depends(verify_token)):
    return await cases.delete_scenario(case_id, scenario_id, user['id'])


@router.post('/{case_id}/apply-reviewed-field')
async def apply_reviewed_field(case_id: str, body: ApplyReviewedField,
                               user: dict = Depends(verify_token)):
    return await cases.apply_reviewed_field(case_id, user['id'], body.filename, body.field_key)


@router.patch('/{case_id}/facts')
async def update_facts(case_id: str, body: CaseFactsPatch, user: dict = Depends(verify_token)):
    return await cases.update_facts(case_id, user['id'], body)


@router.put('/{case_id}/documents/{slot}')
async def update_document(case_id: str, slot: str, body: CaseDocumentUpdate,
                          user: dict = Depends(verify_token)):
    return await cases.update_document(case_id, user['id'], slot, body)


@router.delete('/{case_id}/documents/{slot}')
async def clear_document(case_id: str, slot: str, user: dict = Depends(verify_token)):
    return await cases.clear_document(case_id, user['id'], slot)


@router.post('/{case_id}/calculate')
async def calculate_case(case_id: str, user: dict = Depends(verify_token)):
    try:
        return await cases.calculate_case(case_id, user['id'])
    except HTTPException:
        raise
    except Exception as exc:
        error = classify_error(exc, operation='consultation_case.income_tax')
        raise HTTPException(error.http_status, error.detail()) from exc


@router.post('/{case_id}/conversation')
async def ensure_conversation(case_id: str, user: dict = Depends(verify_token)):
    return await cases.ensure_conversation(case_id, user['id'])


@router.delete('/{case_id}')
async def delete_case(case_id: str, user: dict = Depends(verify_token)):
    return await cases.delete_case(case_id, user['id'])
