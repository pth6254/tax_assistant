"""A keyword miss must not exclude a law; the planner chooses among the known laws."""
import json
from unittest.mock import AsyncMock

import pytest

from app.schemas.reliability import Issue, QuestionPlan
from app.services import question_planning as planning
from app.services.chat_service import _match_laws_by_keyword
from app.services.tax_laws import KNOWN_LAWS, LAW_KEYWORDS

QUERY = '복식부기의무자가 장부를 작성하지 않았을 때 무기장가산세와 신고불성실가산세는 중복 적용되나요?'


def issue(key, law):
    return Issue(id=key, request_quote=QUERY, law=law, question=f'{law} 가산세 요건')


def test_keywords_alone_find_only_the_procedural_law_for_this_question():
    # The reason a keyword-bound plan could never reach the income tax act.
    assert _match_laws_by_keyword(QUERY) == ['국세기본법']
    assert KNOWN_LAWS == tuple(LAW_KEYWORDS) and '소득세법' in KNOWN_LAWS


def test_plan_may_add_a_known_law_the_keywords_missed():
    plan = QuestionPlan(issues=[issue('I1', '소득세법'), issue('I2', '국세기본법')])
    checked = planning.validate_plan(plan, QUERY, ['국세기본법'])
    assert [i.law for i in checked.issues] == ['소득세법', '국세기본법']


def test_unknown_law_names_are_still_rejected():
    plan = QuestionPlan(issues=[issue('I1', '없는법'), issue('I2', '국세기본법')])
    with pytest.raises(ValueError, match='unapproved_law_filter'):
        planning.validate_plan(plan, QUERY, ['국세기본법'])


def test_keyword_candidates_must_still_be_kept():
    plan = QuestionPlan(issues=[issue('I1', '소득세법')])
    query = '소득세 신고와 증여세 공제를 설명해 주세요.'
    plan.issues[0] = plan.issues[0].model_copy(update={'request_quote': query})
    with pytest.raises(ValueError, match='missing_tax'):
        planning.validate_plan(plan, query, ['소득세법', '상속세 및 증여세법'])


def test_the_number_of_added_laws_is_bounded():
    added = ['소득세법', '법인세법', '부가가치세법', '지방세법']
    plan = QuestionPlan(issues=[issue(f'I{n}', law) for n, law in enumerate(added, 1)])
    with pytest.raises(ValueError, match='too_many_added_laws'):
        planning.validate_plan(plan, QUERY, [])
    ok = QuestionPlan(issues=[issue(f'I{n}', law) for n, law in enumerate(added[:3], 1)])
    assert len(planning.validate_plan(ok, QUERY, []).issues) == 3


@pytest.mark.asyncio
async def test_planner_is_offered_every_known_law_with_keyword_hits_first(monkeypatch):
    plan = QuestionPlan(issues=[issue('I1', '소득세법'), issue('I2', '국세기본법')])
    llm = AsyncMock(return_value=json.loads(plan.model_dump_json()))
    monkeypatch.setattr(planning, 'call_llm_structured', llm)
    result = await planning.plan_question(QUERY, ['국세기본법'])
    assert [i.law for i in result.issues] == ['소득세법', '국세기본법']
    messages, schema = llm.call_args.args[:2]
    enum = schema['$defs']['Issue']['properties']['law']['enum']
    assert enum[0] == '국세기본법' and set(enum) == {*KNOWN_LAWS, 'ALL'}
    payload = json.loads(messages[1]['content'])
    assert payload['law_candidates'] == ['국세기본법'] and payload['allowed_laws'] == list(KNOWN_LAWS)
    assert '개별 세법' in messages[0]['content'] and '법별 쟁점' in messages[0]['content']


@pytest.mark.asyncio
async def test_rejected_plan_still_falls_back_to_keyword_candidates(monkeypatch):
    bad = QuestionPlan(issues=[issue('I1', '없는법')])
    monkeypatch.setattr(planning, 'call_llm_structured',
                        AsyncMock(return_value=json.loads(bad.model_dump_json())))
    result = await planning.plan_question(QUERY, ['국세기본법'])
    assert result.status == 'fallback' and {i.law for i in result.issues} == {'국세기본법'}
