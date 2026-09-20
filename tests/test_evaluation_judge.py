from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from evaluation.judge import assess


def inputs(status='approved'):
    return (SimpleNamespace(id='test', input={'query':'q','context':'reference'},
        review=SimpleNamespace(status=status, basis='synthetic_contract'),
        rubric=[SimpleNamespace(id='core', critical=True, instruction='check')]),
        SimpleNamespace(payload={'answer':'answer'},error=None))


@pytest.mark.asyncio
async def test_draft_never_self_approves():
    provider = SimpleNamespace(structured=AsyncMock())
    result = await assess(provider, *inputs('draft'))
    assert result[0]['verdict'] == 'unknown'
    provider.structured.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('quote,expected', [('A1','pass'),('invented','error')])
async def test_exact_evidence(quote, expected):
    provider = SimpleNamespace(structured=AsyncMock(return_value=dict(
        verdict='pass', rationale='reason', mode='support', answer_ids=[quote], reference_ids=['R1'])))
    result = await assess(provider, *inputs())
    assert result[0]['verdict'] == expected
    assert provider.structured.call_count == (1 if expected == 'pass' else 2)


@pytest.mark.asyncio
async def test_error_does_not_leak_secrets():
    provider = SimpleNamespace(structured=AsyncMock(side_effect=RuntimeError('secret')))
    result = await assess(provider, *inputs())
    assert result[0]['verdict'] == 'error'
    assert 'secret' not in str(result)
    assert provider.structured.call_count == 1


@pytest.mark.asyncio
async def test_repair_once():
    valid = dict(verdict='pass', rationale='reason', mode='support', answer_ids=['A1'], reference_ids=['R1'])
    provider = SimpleNamespace(structured=AsyncMock(side_effect=[valid | {'answer_ids':['A99']}, valid]))
    result = await assess(provider, *inputs())
    assert result[0]['attempts'] == 2
    assert result[0]['answer_evidence'] == {'A1':'answer'}


@pytest.mark.asyncio
async def test_behavior_absence_requires_full_answer():
    case, obs = inputs()
    case.id = 'answer-insufficient-context'
    case.rubric[0].id = 'no-invented-amount'
    valid = dict(verdict='pass', rationale='reason', mode='absence', answer_ids=['A1'], reference_ids=[])
    provider = SimpleNamespace(structured=AsyncMock(return_value=valid))
    assert (await assess(provider, case, obs))[0]['verdict'] == 'pass'
    provider.structured.return_value = valid | {'answer_ids':[]}
    assert (await assess(provider, case, obs))[0]['verdict'] == 'error'


@pytest.mark.asyncio
async def test_paired_omission_needs_reference_but_not_answer():
    valid = dict(verdict='fail', rationale='missing condition', mode='omission', answer_ids=[], reference_ids=['R1'])
    provider = SimpleNamespace(structured=AsyncMock(return_value=valid))
    assert (await assess(provider, *inputs()))[0]['verdict'] == 'fail'
    provider.structured.return_value = valid | {'reference_ids':[]}
    assert (await assess(provider, *inputs()))[0]['verdict'] == 'error'
