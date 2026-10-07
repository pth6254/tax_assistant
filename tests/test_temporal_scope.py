"""Event dates decide version applicability by date comparison only."""
from datetime import date

import pytest

from app.schemas.reliability import Issue, QuestionPlan
from app.services import claim_verification as claims, question_planning as planning
from app.services.evidence import context_from_records, record_from_result
from app.services.temporal_scope import event_interval, is_event_date, unresolved_dates
from tests.test_reliability_workflow import draft, source

TODAY = date(2026, 10, 7)


def record(effective='2026-04-21', **changes):
    return record_from_result(source(effective_date=effective, **changes))


@pytest.mark.parametrize('value, expected', [
    ('2026년', (date(2026, 1, 1), date(2026, 12, 31))),
    ('2026년 2월', (date(2026, 2, 1), date(2026, 2, 28))),
    ('2026년 6월 1일', (date(2026, 6, 1), date(2026, 6, 1))),
    ('2026-06-01', (date(2026, 6, 1), date(2026, 6, 1))),
    ('2026년 13월', None), ('3년 6개월', None), ('10년', None), ('증여일 2026년', None),
])
def test_event_interval(value, expected):
    assert event_interval(value) == expected
    assert is_event_date(value) == (expected is not None)


def test_only_events_inside_the_current_version_period_are_resolved():
    current = [record()]
    assert unresolved_dates(['2026년 6월 1일', '2026-04-21'], current, TODAY) == []
    # Part of the year, an earlier day, or a future day predates or outlives the evidence.
    for value in ('2026년', '2026년 4월', '2026년 3월 1일', '2027년 1월 1일', '3년 6개월'):
        assert unresolved_dates([value], current, TODAY) == [value]
    # The latest effective date among the cited versions governs.
    assert unresolved_dates(['2026년 3월 1일'], [record('2026-01-01'), record('2026-04-21', source_id='18')], TODAY)
    assert unresolved_dates(['2026년 6월 1일'], [], TODAY) == ['2026년 6월 1일']
    assert unresolved_dates(['2026년 6월 1일'], [record(None)], TODAY) == ['2026년 6월 1일']
    assert unresolved_dates(['2026년 6월 1일'], [record(origin_kind='user_document')], TODAY) == ['2026년 6월 1일']


def dated_context(dates, effective='2026-01-01'):
    plan = QuestionPlan(issues=[Issue(id='I1', request_quote='질문', question='질문')], dates=dates)
    return context_from_records([record(effective)], plan=plan)


def test_legal_claim_about_an_event_under_the_cited_version_is_not_held_back():
    ctx = dated_context(['2026년 6월 1일'])
    assert claims.check_claims(draft(ctx), ctx, '질문')['C1'] == []
    answer = claims.render_claims(draft(ctx).claims, ctx)
    assert answer.count('적용 시점:') == 1 and '2026년 6월 1일' in answer
    assert '부칙의 적용례' in answer and '아직 확인되지 않았습니다' not in answer


def test_legal_claim_about_an_earlier_event_still_needs_the_historical_version():
    ctx = dated_context(['2025년 6월 1일'])
    assert 'historical_version_required' in claims.check_claims(draft(ctx), ctx, '질문')['C1']
    summary = draft(ctx, '확보한 원문은 조건을 충족한 경우에만 적용한다고 정합니다.').claims[0]
    summary.kind = 'source_summary'
    assert claims.version_undetermined(summary, ctx)
    assert '아직 확인되지 않았습니다' in claims.render_claims([summary], ctx)


def test_durations_are_not_kept_as_event_dates():
    query = 'A는 토지를 3년 6개월 보유한 뒤 양도했습니다. 장기보유 특별공제 기준을 설명해 주세요.'
    plan = QuestionPlan(issues=[Issue(id='I1', request_quote='장기보유 특별공제 기준을 설명해 주세요.',
                                      subject='A', law='소득세법', question='장기보유 특별공제 기준')],
                        dates=['3년 6개월'])
    plan = planning.validate_plan(plan, query, ['소득세법'])
    assert plan.dates == []
    assert '거래·사건의 적용 시점' in plan.missing_inputs
