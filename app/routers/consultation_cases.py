"""Authenticated income-tax consultation workspace API."""
from fastapi import APIRouter, Depends, HTTPException

from app.core.security import verify_token
from app.schemas.consultation_case import CaseCreate, CaseDocumentUpdate, CaseFactsPatch
from app.services import consultation_case_service as cases
from app.services.calculator.errors import classify_error


router = APIRouter(prefix='/api/consultation-cases', tags=['consultation-cases'])


@router.get('')
async def list_cases(user: dict = Depends(verify_token)):
    return await cases.list_cases(user['id'])


@router.post('', status_code=201)
async def create_case(body: CaseCreate, user: dict = Depends(verify_token)):
    return await cases.create_case(user['id'], body)


@router.get('/{case_id}')
async def get_case(case_id: str, user: dict = Depends(verify_token)):
    return await cases.get_case(case_id, user['id'])


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
