"""Failure injection only: never delete or modify actual tax tables."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.calculator import IncomeTaxRequest
from app.services.calculator import income_tax, gift_tax, inheritance, capital_gains, vat, penalty_tax, repository
from app.services.calculator.errors import CalculationError, require_value
from app.services.tools.executor import execute_tool
from app.services import chat_service
from app.routers.calculator import _calculate
from tests.test_calculator import _patch_repository


@pytest.mark.asyncio
@pytest.mark.parametrize('module,params', [
    (income_tax, {'income': 10000000}), (gift_tax, {'gift_amount': 10000000}),
    (inheritance, {'estate_value': 10000000}),
    (capital_gains, {'transfer_price': 10000000, 'acquisition_price': 0}),
    (vat, {'sales': 10000000}),
])
async def test_missing_brackets_never_become_zero(module, params, monkeypatch):
    with _patch_repository(module):
        monkeypatch.setattr(module, 'get_brackets', AsyncMock(return_value=[]))
        with pytest.raises(CalculationError, match='세율') as error:
            await module.calculate(**params)
        assert error.value.code == 'missing_tax_data'


@pytest.mark.asyncio
@pytest.mark.parametrize('module,params', [
    (income_tax, {'income': 10000000}),
    (gift_tax, {'gift_amount': 10000000, 'relation': '배우자'}),
    (inheritance, {'estate_value': 10000000}),
    (capital_gains, {'transfer_price': 10000000, 'acquisition_price': 0}),
    (penalty_tax, {'unpaid_tax': 10000000}),
])
async def test_missing_deduction_never_uses_default(module, params, monkeypatch):
    with _patch_repository(module):
        monkeypatch.setattr(module, 'get_deduction', AsyncMock(return_value=None))
        with pytest.raises(CalculationError):
            await module.calculate(**params)


@pytest.mark.asyncio
@pytest.mark.parametrize('exc,code', [(ConnectionError('secret'), 'database_unavailable'),
                                      (TimeoutError('secret'), 'timeout'),
                                      (RuntimeError('secret'), 'internal_error')])
async def test_repository_sanitizes_and_classifies(monkeypatch, exc, code, caplog):
    monkeypatch.setattr(repository, 'get_pool', AsyncMock(side_effect=exc))
    with pytest.raises(CalculationError) as error:
        await repository.get_brackets('test')
    assert error.value.code == code
    assert 'secret' not in str(error.value)
    assert 'secret' not in caplog.text


def test_zero_config_is_valid_and_negative_input_is_not():
    assert require_value({'amount': 0}, 'amount') == 0
    assert IncomeTaxRequest(income=0).income == 0
    with pytest.raises(ValidationError):
        IncomeTaxRequest(income=-1)


@pytest.mark.asyncio
@pytest.mark.parametrize('params,status', [({}, 'needs_input'), ({'income': -1}, 'invalid_arguments')])
async def test_tool_input_categories(params, status):
    result = await execute_tool('income_tax', params, user_id=str(uuid4()))
    assert result.status == status
    assert result.calculation is None


@pytest.mark.asyncio
async def test_unsupported_conditions():
    with pytest.raises(CalculationError) as error:
        await vat.calculate(sales=1000, is_simplified=True, business_type='unknown')
    assert error.value.code == 'unsupported_condition'


@pytest.mark.asyncio
async def test_api_safe_failure_contract():
    async def failed(**kwargs):
        raise ConnectionError('credentials-must-not-leak')
    with pytest.raises(HTTPException) as error:
        await _calculate(failed, IncomeTaxRequest(income=0))
    assert error.value.status_code == 503
    assert error.value.detail['retryable'] is True
    assert 'credentials' not in str(error.value.detail)


@pytest.mark.asyncio
@pytest.mark.parametrize('streaming', [False, True])
async def test_failed_calculation_bypasses_llm_and_preserves_failure(monkeypatch, streaming):
    async def prepare(*args, on_tool_event):
        on_tool_event({'type': 'tool', 'id': 'primary', 'tool': 'income_tax',
                       'status': 'error', 'context': '세율 데이터 확인 필요',
                       'error_code': 'missing_tax_data', 'retryable': False})
        return '', '', [], None
    monkeypatch.setattr(chat_service, '_fetch_rag_and_web_context', prepare)
    generate = AsyncMock(side_effect=AssertionError('LLM must not run'))
    monkeypatch.setattr(chat_service, '_generate_answer', generate)
    monkeypatch.setattr(chat_service, '_stream_llm_skip_think', generate)
    save = AsyncMock()
    monkeypatch.setattr(chat_service, '_save_history', save)
    args = ('계산', str(uuid4()), str(uuid4()))
    if streaming:
        events = [e async for e in chat_service.stream_chat_response(*args)]
        assert not any(e['type'] == 'calc' for e in events)
        answer = ''.join(e['text'] for e in events if e['type'] == 'chunk')
    else:
        answer, calc = await chat_service.process_chat(*args)
        assert calc is None
    assert '0원이라는 뜻이 아닙니다' in answer
    generate.assert_not_called()
    assert save.call_args.kwargs['tools'][0]['error_code'] == 'missing_tax_data'
