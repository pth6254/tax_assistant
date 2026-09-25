"""Regression contracts for the six 2026-09-25 archive runtime defects."""
from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4
import xml.etree.ElementTree as ET

import pytest

from app.services.law.history_context import route, temporal_request
from app.services.law.history_parser import tree
from app.services.law.history_structure import article_excerpt, HistoricalStructureError
from app.services.law.reference_parser import parse_law_reference, extract_law_reference
from app.services.law import history_answer as answer
from app.services.search import history_search as search


STATE = dict(law_id='001', law_name='소득세법', version_id=529, snapshot_id=10,
             as_of='1949-07-15', article=1, article_branch=None, paragraph=1, item=2, item_branch=None)
HISTORY = [dict(role='user', content='1949-07-15 소득세법 제1조'),
           dict(role='assistant', content='LLM 내용은 라우팅에 사용하지 않음', history_context=STATE)]


@pytest.mark.parametrize('query', ['2025년 귀속 종합소득세 계산해줘', '2025년 계약서에서 보증금을 찾아줘',
                                  '2026년 연말정산 준비서류를 알려줘', '당시 업로드한 PDF 검색해줘',
                                  '2025년 서류에서 보증금을 찾아줘'])
def test_year_is_not_a_legal_intent(query):
    assert not temporal_request(query)
    assert route(query, HISTORY) is None


@pytest.mark.parametrize('query', ['2025년 소득세법 제55조', '2025-01-01 소득세법 시행령', '구법 기준'])
def test_law_time_intent_still_goes_to_archive(query):
    assert temporal_request(query)


def test_followup_retains_version_date_and_structured_reference():
    query = route('그럼 제2조는?', HISTORY)
    assert '법령버전 529' in query and '1949-07-15' in query
    assert extract_law_reference(query).article == 2
    query = route('그럼 제2항은?', HISTORY)
    assert extract_law_reference(query).canonical == '제1조 제2항'
    query = route('그럼 가목은?', HISTORY)
    assert extract_law_reference(query).canonical == '제1조 제1항 제2호 가목'


def test_new_scope_overrides_previous_scope_and_other_turn_clears_it():
    assert '법령버전 529' not in route('1950-01-01 기준 제2조', HISTORY)
    assert '소득세법' in route('1950-01-01 기준 제2조', HISTORY)
    query = route('그럼 부가가치세법 제2조는?', HISTORY)
    assert '1949-07-15' in query and '법령버전 529' not in query
    assert route('법령버전 530 제1조', HISTORY) == '법령버전 530 제1조'
    assert route('현행 소득세법 제2조', HISTORY) is None
    changed = HISTORY + [dict(role='user', content='계약서 검색'), dict(role='assistant', content='검색 결과')]
    assert route('그럼 제2조는?', changed) is None


def test_old_conversation_without_structured_scope_asks_instead_of_current_law():
    assert route('그럼 제2조는?', HISTORY[:1]).startswith('과거 법령')


XML = '''<조문단위><조문내용>제59조의4(특별세액공제)</조문내용>
<항><항번호>①</항번호><항내용>① 해당 과세기간의 다음 각 호를 공제한다. 다만 한도를 적용한다.</항내용>
  <호><호번호>1.</호번호><호내용>1. 장애인전용보험료</호내용></호>
  <호><호번호>2의2.</호번호><호내용>2의2. 다음 각 목의 보험료</호내용>
    <목><목번호>가.</목번호><목내용>가. 실제 첫 번째 목의 내용</목내용></목>
    <목><목번호>나.</목번호><목내용>나. 실제 두 번째 목의 내용</목내용></목>
  </호>
</항>
<항><항번호>②</항번호><항내용>② 의료비 규정</항내용>
  <호><호번호>1.</호번호><호내용>1. 다른 항의 의료비</호내용></호></항></조문단위>'''


@pytest.mark.parametrize('law_name', ['소득세법', '소득세법 시행령', '소득세법 시행규칙'])
def test_xml_numbers_are_metadata_not_empty_paragraphs(law_name):
    root = tree(ET.fromstring(XML))
    ref = parse_law_reference(law_name + ' 제59조의4 제1항 제1호')
    result = article_excerpt(root, '①\n① 잘못된 평문', ref)
    assert '장애인전용보험료' in result
    assert '다만 한도를 적용한다.' in result  # Preserve parent qualification.
    assert '의료비' not in result and '2의2.' not in result
    assert '①\n①' not in result
    subitem = article_excerpt(root, '', parse_law_reference('제59조의4 제1항 제2호의2 가목'))
    assert '실제 첫 번째 목' in subitem and '실제 두 번째 목' not in subitem


def test_xml_missing_or_ambiguous_target_cannot_fall_back_to_other_paragraph():
    root = ET.fromstring(XML)
    with pytest.raises(HistoricalStructureError):
        article_excerpt(tree(root), '① 3. 가짜 내용', parse_law_reference('제59조의4 제1항 제3호'))
    root.append(ET.fromstring(ET.tostring(root.find('항'), encoding='unicode')))
    with pytest.raises(HistoricalStructureError):
        article_excerpt(tree(root), '', parse_law_reference('제59조의4 제1항'))


def test_unnumbered_paragraph_container_has_article_level_items():
    root = tree(ET.fromstring('<조문단위><조문내용>제1조(정의)</조문내용><항><항내용>이 법에서 사용하는 용어</항내용><호><호번호>1.</호번호><호내용>1. 정의 원문</호내용></호></항></조문단위>'))
    assert '정의 원문' in article_excerpt(root, '', parse_law_reference('제1조 제1호'))


@pytest.mark.asyncio
async def test_version_name_conflict_rejected_before_snapshot_or_article(monkeypatch):
    pool = AsyncMock()
    pool.fetchrow.return_value = dict(id=529, law_id='income', law_name='소득세법')
    pool.fetch.return_value = [dict(law_id='income', law_name='소득세법'), dict(law_id='vat', law_name='부가가치세법')]
    monkeypatch.setattr(search, 'get_pool', AsyncMock(return_value=pool))
    snapshot = AsyncMock()
    monkeypatch.setattr(search, 'with_snapshot', snapshot)
    with pytest.raises(search.HistoryUnavailable, match='소속'):
        await search.query_version('법령버전 529 부가가치세법 제1조 원문')
    snapshot.assert_not_called()


@pytest.mark.asyncio
async def test_longest_law_name_per_occurrence_and_matching_version(monkeypatch):
    pool = AsyncMock()
    pool.fetch.return_value = [dict(law_id='law', law_name='소득세법'), dict(law_id='decree', law_name='소득세법 시행령')]
    assert await search.named_law_ids(pool, '소득세법 시행령 제1조') == {'decree'}
    assert await search.named_law_ids(pool, '소득세법 제1조와 소득세법 시행령 제2조') == {'law', 'decree'}
    version = dict(id=10, law_id='decree', law_name='소득세법 시행령', effective_date=date(2000, 1, 1))
    pool.fetchrow.return_value = version
    monkeypatch.setattr(search, 'get_pool', AsyncMock(return_value=pool))
    monkeypatch.setattr(search, 'with_snapshot', AsyncMock(return_value=version))
    assert (await search.query_version('법령버전 10 소득세법 시행령 제1조'))[0] == version


def evidence(**changes):
    return dict(content='원문에 실제로 있는 문장입니다.', law_name='소득세법', article_no='제1조',
                version_id=529, source_url='https://www.law.go.kr/', promulgation_date='1949-07-15',
                effective_date='1949-07-15', graph_evidence='', required=True) | changes


def test_primary_evidence_cannot_be_displaced_by_smaller_graph_sources():
    main = evidence(content='긴 필수 원문' * 3000)
    graph = evidence(required=False, graph_evidence='명시적 인용', law_name='다른법')
    assert answer.select_evidence([main, graph]) == []
    main = evidence(content='① 요청한 항의 원문입니다.')
    assert answer.select_evidence([graph, main])[0] == main
    assert answer.select_evidence([graph]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['generation', 'quote', 'graph_only', 'none'])
async def test_final_status_tracks_generation_and_quote_validation(monkeypatch, failure):
    data = dict(results=[evidence(), evidence(required=False, graph_evidence='인용')],
                as_of='1949-07-15', graph_status='checked', history_context=STATE)
    monkeypatch.setattr(answer, 'retrieve', AsyncMock(return_value=data))
    quote = '원문에 실제로 있는 문장입니다.' if failure != 'quote' else '전혀 존재하지 않는 인용입니다.'
    model = AsyncMock(return_value={'claims': [dict(explanation='설명', source=2 if failure == 'graph_only' else 1, quote=quote)]})
    if failure == 'generation':
        model.side_effect = RuntimeError('injected')
    monkeypatch.setattr(answer, 'call_llm_structured', model)
    events = []
    result = await answer.answer('질문', events.append)
    terminal = [e for e in events if e['status'] != 'running']
    assert len(terminal) == 1
    assert terminal[0]['history_context'] == STATE
    assert terminal[0]['retrieval_status'] == 'ok'
    assert terminal[0]['status'] == ('ok' if failure == 'none' else 'error')
    assert ('요약을 보류' in result) == (failure != 'none')
    if failure != 'none':
        assert not any(e['status'] == 'ok' for e in events)


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
async def test_followup_in_both_chat_entrypoints_persists_scope(monkeypatch, stream):
    from app.services import chat_service as chat
    monkeypatch.setattr(chat, '_fetch_history', AsyncMock(return_value=HISTORY))
    save = AsyncMock()
    monkeypatch.setattr(chat, '_save_history', save)
    current = AsyncMock(side_effect=AssertionError('current-law path forbidden'))
    monkeypatch.setattr(chat, '_fetch_rag_and_web_context', current)
    async def historical(query, event):
        assert '법령버전 529' in query and '1949-07-15' in query and '제2조' in query
        event(dict(type='tool', id='history', tool='history_lookup', status='ok', history_context=STATE))
        return '구법 원문'
    monkeypatch.setattr(chat, 'history_answer', historical)
    if stream:
        events = [e async for e in chat.stream_chat_response('그럼 제2조는?', str(uuid4()), str(uuid4()))]
        assert events[-1]['text'] == '구법 원문'
    else:
        assert (await chat.process_chat('그럼 제2조는?', str(uuid4()), str(uuid4())))[0] == '구법 원문'
    assert save.call_args.args[1] == '그럼 제2조는?'
    assert save.call_args.kwargs['tools'][0]['history_context'] == STATE
    current.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('query', ['2025년 귀속 종합소득세 계산해줘', '2025년 계약서에서 보증금을 찾아줘'])
async def test_year_tasks_reach_normal_tool_path(monkeypatch, stream, query):
    from app.services import chat_service as chat
    monkeypatch.setattr(chat, '_save_history', AsyncMock())
    archive = AsyncMock(side_effect=AssertionError('archive forbidden'))
    monkeypatch.setattr(chat, 'history_answer', archive)
    async def normal(q, conv, user, on_tool_event=None):
        assert q == query
        on_tool_event(dict(type='tool', id='primary', tool='none', status='needs_input'))
        return '', '', [], None
    monkeypatch.setattr(chat, '_fetch_rag_and_web_context', normal)
    if stream:
        events = [e async for e in chat.stream_chat_response(query, str(uuid4()), str(uuid4()))]
        assert events[-1]['type'] == 'chunk'
    else:
        await chat.process_chat(query, str(uuid4()), str(uuid4()))
    archive.assert_not_called()


@pytest.mark.asyncio
async def test_scope_survives_db_message_reload_but_not_llm_tool_history(mock_pool, monkeypatch):
    import json
    from app.services import chat_service as chat
    from app.services.tools.executor import ToolRun
    pool, conn = mock_pool
    monkeypatch.setattr(chat, 'get_pool', AsyncMock(return_value=pool))
    tool = dict(tool='history_lookup', status='error', history_context=STATE)
    await chat._save_history(uuid4(), '질문', '요약 보류', tools=[tool])
    stored = json.loads(conn.executemany.call_args.args[1][1][1])
    conn.fetch.return_value = [{'message': stored}]
    history = await chat._fetch_history(uuid4())
    assert history[0]['history_context'] == STATE
    planner = AsyncMock(return_value=ToolRun('none', 'needs_input', '조건 필요'))
    monkeypatch.setattr(chat, 'run_tools_for_query', planner)
    await chat._fetch_rag_and_web_context('계산해줘', uuid4(), str(uuid4()))
    assert planner.call_args.kwargs['history'] == [dict(role='assistant', content='요약 보류')]


@pytest.mark.asyncio
async def test_over_budget_primary_abstains_without_generation(monkeypatch):
    monkeypatch.setattr(answer, 'retrieve', AsyncMock(return_value=dict(
        results=[evidence(content='긴 원문' * 10000), evidence(required=False, graph_evidence='인용')],
        history_context=STATE, as_of=STATE['as_of'], graph_status='checked')))
    model = AsyncMock()
    monkeypatch.setattr(answer, 'call_llm_structured', model)
    events = []
    result = await answer.answer('원문', events.append)
    assert events[-1]['status'] == 'needs_input' and events[-1]['history_context'] == STATE
    assert '항·호·목' in result
    model.assert_not_called()


@pytest.mark.asyncio
async def test_missing_target_keeps_resolved_version_scope(monkeypatch):
    monkeypatch.setattr(search, 'query_version', AsyncMock(return_value=(dict(
        id=529, law_id='001', law_name='소득세법', snapshot_id=10), date(1949, 7, 15))))
    monkeypatch.setattr(search, 'direct_article', AsyncMock(side_effect=search.HistoryUnavailable('항 확인 필요')))
    monkeypatch.setattr(answer, 'retrieve', search.retrieve)
    events = []
    await answer.answer('법령버전 529 제1조 제99항', events.append)
    assert events[-1]['history_context']['version_id'] == 529
    assert '법령버전 529' in route('그럼 제2조는?', [dict(role='assistant', tools=events[-1:])])


@pytest.mark.asyncio
async def test_graph_edges_outside_requested_excerpt_are_not_expanded(monkeypatch):
    from unittest.mock import MagicMock
    pool = AsyncMock()
    pool.fetchval.return_value = 'hash'
    monkeypatch.setattr(search, 'get_pool', AsyncMock(return_value=pool))
    driver = AsyncMock()
    driver.execute_query.return_value = ([dict(law_name='다른법', reference='제1조', evidence='다른 항의 인용')], None, None)
    connection = MagicMock()
    connection.__aenter__ = AsyncMock(return_value=driver)
    connection.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(search, 'connect', lambda: connection)
    seed = evidence(snapshot_id=1, text_key='a:hash', content='① 요청한 항의 원문')
    assert await search.expand([seed], date(2020, 1, 1)) == [seed]
    pool.fetch.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_explicit_law_name_is_not_silently_ignored(monkeypatch):
    pool = AsyncMock()
    pool.fetchrow.return_value = dict(id=529, law_id='income', law_name='소득세법')
    pool.fetch.return_value = [dict(law_id='income', law_name='소득세법')]
    monkeypatch.setattr(search, 'get_pool', AsyncMock(return_value=pool))
    with pytest.raises(search.HistoryUnavailable, match='법령명'):
        await search.query_version('법령버전 529 존재하지않는법 제1조')
