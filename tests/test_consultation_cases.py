from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.calculator import CalculationResult
from app.schemas.consultation_case import CaseCreate, CaseDocumentUpdate
from app.services import consultation_case_service as cases
from app.services.consultation_catalog import CASE_KINDS


def test_case_questions_require_explicit_zero_and_checklist_detects_changed_document():
    facts = {'income': 0, 'expense': 100, 'personal_deduction_count': 1,
             'other_deductions': 0}
    assert all(item['answered'] for item in cases._questions(facts))
    checklist = cases._checklist(facts, {
        'income_proof': {'status': 'attached', 'filename': 'income.pdf', 'uploaded_at': 'old'},
    }, {'income.pdf': 'new'})
    assert [item['needed'] for item in checklist] == [True, True, False]
    assert checklist[0]['status'] == 'needs_recheck'


def test_case_input_rejects_future_year_and_missing_document_reason():
    with pytest.raises(ValidationError):
        CaseCreate(title='x', question='x', tax_year=date.today().year + 1)
    with pytest.raises(ValidationError):
        CaseDocumentUpdate(status='not_available')


@pytest.mark.asyncio
async def test_case_lookup_does_not_reveal_foreign_or_invalid_id():
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    user_id = str(uuid.uuid4())
    for case_id in ('invalid', str(uuid.uuid4())):
        with pytest.raises(HTTPException) as exc:
            await cases._owned_row(conn, case_id, user_id)
        assert exc.value.status_code == 404
    assert conn.fetchrow.await_count == 1
    assert 'user_id=$2' in conn.fetchrow.call_args.args[0]


def fake_pool(conn):
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=conn)
    context.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire.return_value = context
    return pool


@pytest.mark.asyncio
async def test_case_calculation_uses_selected_year_and_saves_exact_facts(monkeypatch):
    uid, cid = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(timezone.utc)
    facts = {'income': 50000000, 'expense': 0, 'personal_deduction_count': 1,
             'other_deductions': 0}
    row = {'id': cid, 'user_id': uid, 'conversation_id': None, 'kind': 'income_tax',
           'title': 'test', 'question': 'tax', 'tax_year': 2024, 'facts': facts,
           'checklist': {}, 'calculation': None, 'created_at': now, 'updated_at': now}
    conn = AsyncMock()
    async def fetchrow(query, *args):
        return row if query.startswith('SELECT') else {**row, 'calculation': args[0]}
    conn.fetchrow.side_effect = fetchrow
    monkeypatch.setattr(cases, 'get_pool', AsyncMock(return_value=fake_pool(conn)))
    result = CalculationResult(tax_type='소득세', steps=[], taxable_income=0,
                               calculated_tax=0, final_tax=0, effective_rate=0,
                               source_articles=[])
    calculate = AsyncMock(return_value=result)
    monkeypatch.setattr(cases, 'calculate_income_tax', calculate)
    response = await cases.calculate_case(str(cid), str(uid))
    assert response['calculation']['result']['final_tax'] == 0
    assert calculate.await_args.kwargs['as_of'] == date(2024, 12, 31)
    assert conn.fetchrow.call_args.args[-2] == facts
    assert conn.fetchrow.call_args.args[-1] == date(2024, 12, 31)


@pytest.mark.asyncio
async def test_missing_fact_prevents_any_calculation(monkeypatch):
    uid, cid = uuid.uuid4(), uuid.uuid4()
    conn = AsyncMock()
    conn.fetchrow.return_value = {'id': cid, 'user_id': uid, 'kind': 'income_tax',
                                  'facts': {'income': 0}}
    monkeypatch.setattr(cases, 'get_pool', AsyncMock(return_value=fake_pool(conn)))
    calculate = AsyncMock()
    monkeypatch.setattr(cases, 'calculate_income_tax', calculate)
    with pytest.raises(HTTPException) as exc:
        await cases.calculate_case(str(cid), str(uid))
    assert exc.value.status_code == 422
    assert exc.value.detail['code'] == 'needs_input'
    calculate.assert_not_awaited()


def test_case_endpoints_require_auth(client):
    assert client.get('/api/consultation-cases').status_code == 401
    assert client.post('/api/consultation-cases', json={}).status_code == 401


@pytest.mark.parametrize('kind', list(CASE_KINDS))
def test_each_case_kind_has_distinct_questions_and_documents(kind):
    questions = cases._questions({}, kind)
    checklist = cases._checklist({}, {}, {}, kind)
    assert questions and checklist
    assert len({item['key'] for item in questions}) == len(questions)
    assert len({item['key'] for item in checklist}) == len(checklist)
    assert all(not item['answered'] for item in questions)
    assert all(item['status'] == 'pending' for item in checklist)


def test_non_income_case_date_and_choices_are_validated():
    from app.schemas.consultation_case import CaseFactsPatch
    with pytest.raises(ValidationError):
        CaseCreate(kind='gift', title='x', question='x', tax_year=2024,
                   reference_date=date(2025, 1, 1))
    with pytest.raises(ValidationError):
        CaseFactsPatch(relation='unsupported')
    assert CaseFactsPatch(is_minor=False).model_dump(exclude_unset=True) == {'is_minor': False}


def test_conditional_questions_only_ask_relevant_calculator_inputs():
    assert 'is_minor' not in {q['key'] for q in cases._questions({'relation': '배우자'}, 'gift')}
    assert 'is_minor' in {q['key'] for q in cases._questions({'relation': '직계존비속'}, 'gift')}
    assert 'business_type' not in {q['key'] for q in cases._questions({'is_simplified': False}, 'vat')}
    assert 'business_type' in {q['key'] for q in cases._questions({'is_simplified': True}, 'vat')}
    assert 'days_late' in {q['key'] for q in cases._questions({'penalty_type': '납부지연'}, 'penalty_tax')}
    assert 'is_negligent' not in {q['key'] for q in cases._questions({'penalty_type': '납부지연'}, 'penalty_tax')}
