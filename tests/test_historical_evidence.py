"""Archived text in force on the event date may support a dated legal claim; nothing else may."""
from datetime import date
import hashlib

import pytest

from app.schemas.reliability import AnswerClaim, AnswerDraft, ClaimCitation, Issue, QuestionPlan
from app.services import claim_verification as claims
from app.services.evidence import context_from_records, is_official, record_from_result
from app.services.historical_evidence import ArchivedArticle, attach_event_versions, in_force_versions, version_texts
from app.services.temporal_scope import unresolved_dates
from tests.test_reliability_workflow import source

TODAY = date(2026, 10, 8)
OLD = '① 사업자가 장부를 비치·기록하지 아니한 경우 가산세를 더한다.'


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def row(body=OLD, content_hash=None):
    return {'title': '무기장가산세', 'body': body, 'content_hash': content_hash or sha(body)}


def test_article_text_must_be_present_and_intact_in_every_in_force_version():
    assert version_texts([row(), row()]) == [(0, row())]
    assert version_texts([row(), None]) is None                            # missing in one version
    assert version_texts([row(), row(OLD + ' 다만'), row(OLD + ' 다만')]) == [   # amended inside the interval
        (0, row()), (1, row(OLD + ' 다만'))]
    assert version_texts([row(content_hash=sha('다른 본문'))]) is None        # stored hash does not match
    assert version_texts([]) is None


def archived(effective_from=date(2024, 1, 1), effective_to=date(2024, 12, 31), body=OLD, content_hash=None,
             version_id=300):
    return ArchivedArticle(version_id=version_id, law_name='소득세법', effective_from=effective_from,
                           effective_to=effective_to, title='무기장가산세', body=body,
                           content_hash=content_hash or sha(body), source_url='https://www.law.go.kr/history/300')


def dated_context(dates):
    current = record_from_result(source(law_name='소득세법', article_no='제81조의5', effective_date='2026-01-01'))
    plan = QuestionPlan(issues=[Issue(id='I1', request_quote='질문', law='소득세법', question='무기장가산세')],
                        dates=dates)
    coverage = {'I1': {'status': 'sufficient', 'evidence_ids': [current.id], 'relevant_ids': [current.id]}}
    return current, context_from_records([current], plan=plan, coverage=coverage)


def fake_lookup(result):
    calls = []

    async def lookup(law_name, reference, start, end):
        calls.append((law_name, reference.article_no, start, end))
        return result if isinstance(result, list) else [result] if result else []
    return lookup, calls


def legal(record, text='장부를 기록하지 않으면 가산세가 부과됩니다.'):
    return AnswerDraft(claims=[AnswerClaim(id='C1', issue_id='I1', text=text, kind='legal', citations=[
        ClaimCitation(evidence_id=record.id, quote=record.text.splitlines()[-1])])])


@pytest.mark.asyncio
async def test_version_in_force_on_the_event_date_lets_a_legal_claim_through():
    current, ctx = dated_context(['2024년 6월 1일'])
    lookup, calls = fake_lookup(archived())
    result = await attach_event_versions(ctx, lookup=lookup, today=TODAY)
    assert calls == [('소득세법', '제81조의5', date(2024, 6, 1), date(2024, 6, 1))]
    old = next(r for r in result.records if r.id != current.id)
    assert is_official(old) and old.integrity == 'verified'
    assert (old.effective_from, old.effective_to, old.location) == ('2024-01-01', '2024-12-31', '2024-01-01 시행본')
    assert old.id in result.coverage['I1']['evidence_ids'] and old.id in result.coverage['I1']['relevant_ids']
    assert unresolved_dates(['2024년 6월 1일'], [old], TODAY) == []
    assert unresolved_dates(['2024년 6월 1일'], [current], TODAY) == ['2024년 6월 1일']
    assert 'historical_version_required' not in claims.check_claims(legal(old), result, '질문')['C1']
    assert 'historical_version_required' in claims.check_claims(legal(current), result, '질문')['C1']


@pytest.mark.asyncio
async def test_nothing_is_attached_when_the_archive_cannot_determine_the_text():
    _, ctx = dated_context(['2024년 6월 1일'])
    for result in (None, archived(content_hash=sha('변조'))):   # not determined / fails integrity
        lookup, _ = fake_lookup(result)
        assert await attach_event_versions(ctx, lookup=lookup, today=TODAY) is ctx

    async def broken(*args):
        raise RuntimeError('archive unavailable')
    assert await attach_event_versions(ctx, lookup=broken, today=TODAY) is ctx


@pytest.mark.asyncio
async def test_a_version_that_covers_only_part_of_the_event_interval_does_not_govern_it():
    _, ctx = dated_context(['2024년'])   # whole year; the version starts in March
    lookup, _ = fake_lookup(archived(effective_from=date(2024, 3, 1)))
    result = await attach_event_versions(ctx, lookup=lookup, today=TODAY)
    old = next(r for r in result.records if r.effective_from == '2024-03-01')
    assert unresolved_dates(['2024년'], [old], TODAY) == ['2024년']


@pytest.mark.asyncio
async def test_no_lookup_for_current_or_future_events_or_without_dates():
    for dates in ([], ['2026년 6월 1일'], ['2027년 1월 1일'], ['3년 6개월']):
        _, ctx = dated_context(dates)
        lookup, calls = fake_lookup(archived())
        assert await attach_event_versions(ctx, lookup=lookup, today=TODAY) is ctx
        assert calls == []


@pytest.mark.asyncio
async def test_the_same_article_retrieved_twice_is_looked_up_once_and_linked_to_both_issues():
    first = record_from_result(source(law_name='소득세법', article_no='제81조의5', effective_date='2026-01-01'))
    second = record_from_result(source(law_name='소득세법', article_no='제81조의5', effective_date='2026-01-01',
                                       source_id='other-row'))
    plan = QuestionPlan(issues=[Issue(id='I1', request_quote='질문', law='소득세법', question='a'),
                                Issue(id='I2', request_quote='질문', law='소득세법', question='b')],
                        dates=['2024년 6월 1일'])
    coverage = {'I1': {'evidence_ids': [first.id]}, 'I2': {'evidence_ids': [second.id]}}
    ctx = context_from_records([first, second], plan=plan, coverage=coverage)
    lookup, calls = fake_lookup(archived())
    result = await attach_event_versions(ctx, lookup=lookup, today=TODAY)
    old = [r for r in result.records if r.effective_from == '2024-01-01']
    assert len(calls) == 1 and len(old) == 1
    assert all(old[0].id in result.coverage[key]['evidence_ids'] for key in ('I1', 'I2'))


@pytest.mark.asyncio
async def test_archived_citation_is_labelled_by_version_and_not_as_a_current_law_link():
    current, ctx = dated_context(['2024년 6월 1일'])
    lookup, _ = fake_lookup(archived())
    result = await attach_event_versions(ctx, lookup=lookup, today=TODAY)
    old = next(r for r in result.records if r.id != current.id)
    draft = legal(old)
    answer = claims.render_structured_answer(draft.claims, result, '질문')
    assert '소득세법 제81조의5 (2024-01-01 시행본)' in answer
    assert '[법률] 소득세법 제81조의5' not in answer   # the web would open today's text for it
    assert '사건일(2024년 6월 1일)에 시행 중이던 법령 시행본' in answer and '조문별 시행일' in answer
    current_only = claims.render_structured_answer(legal(current).claims, ctx, '질문')
    assert '[법률] 소득세법 제81조의5' in current_only


AMENDED = OLD + ' 다만, 소규모사업자는 제외한다.'


@pytest.mark.asyncio
async def test_an_article_amended_during_the_year_governs_it_only_through_every_version():
    current, ctx = dated_context(['2024년'])
    lookup, _ = fake_lookup([archived(effective_to=date(2024, 2, 27)),
                             archived(effective_from=date(2024, 2, 28), effective_to=None, body=AMENDED,
                                      version_id=301)])
    result = await attach_event_versions(ctx, lookup=lookup, today=TODAY)
    before, after = [r for r in result.records if r.id != current.id]
    assert (before.effective_to, after.effective_from) == ('2024-02-27', '2024-02-28')
    assert {before.id, after.id} <= set(result.coverage['I1']['evidence_ids'])
    assert unresolved_dates(['2024년'], [before], TODAY) == ['2024년']
    assert unresolved_dates(['2024년'], [before, after], TODAY) == []
    assert unresolved_dates(['2024년'], [before, after, current], TODAY) == ['2024년']   # not in force in 2024
    both = AnswerDraft(claims=[AnswerClaim(id='C1', issue_id='I1', text='장부를 기록하지 않으면 가산세가 부과됩니다.',
                                           kind='legal', citations=[
        ClaimCitation(evidence_id=r.id, quote=r.text.splitlines()[-1]) for r in (before, after)])])
    assert 'historical_version_required' not in claims.check_claims(both, result, '질문')['C1']
    assert 'historical_version_required' in claims.check_claims(legal(before), result, '질문')['C1']
    aliases = {before.id: 'E1', after.id: 'E2', current.id: 'E3'}
    fields = claims.event_date_fields(['2024년'], before, result.records, aliases)
    assert fields == {'governs_event_dates': False, 'governs_with': ['E1', 'E2']}
    assert 'governs_with' not in claims.event_date_fields(['2024년'], current, result.records, aliases)


@pytest.mark.asyncio
async def test_a_gap_between_versions_does_not_cover_the_year():
    _, ctx = dated_context(['2024년'])
    lookup, _ = fake_lookup([archived(effective_to=date(2024, 2, 27)),
                             archived(effective_from=date(2024, 3, 5), effective_to=None, body=AMENDED,
                                      version_id=301)])
    result = await attach_event_versions(ctx, lookup=lookup, today=TODAY)
    old = [r for r in result.records if r.source_id.startswith('history:')]
    assert len(old) == 2 and unresolved_dates(['2024년'], old, TODAY) == ['2024년']


def test_of_amendments_taking_effect_the_same_day_the_last_promulgated_is_in_force():
    versions = [{'id': 1, 'effective_date': date(2025, 1, 1)}, {'id': 2, 'effective_date': date(2025, 1, 1)},
                {'id': 3, 'effective_date': date(2025, 2, 28)}]   # ordered by promulgation within a day
    assert [v['id'] for v in in_force_versions(versions)] == [2, 3]
