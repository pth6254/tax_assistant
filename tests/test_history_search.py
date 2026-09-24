from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.services.search import history_search as search
from app.services.law.history_index import chunks,model_key


@pytest.mark.parametrize('query',['2010-01-01 소득세법','2010년 소득세법','법령버전 12 제1조','구법 기준'])
def test_history_routing(query):
    assert search.temporal_request(query)


def test_current_query_unchanged():
    assert not search.temporal_request('소득세법 제1조 알려줘')


@pytest.mark.parametrize('query',['2010년 소득세법','2010-02-30','2010-01-01과 2011-01-01 비교'])
def test_date_ambiguity_rejected(query):
    with pytest.raises(search.HistoryUnavailable):
        search.requested_date(query)


def test_korean_date():
    assert search.requested_date('2010년 1월 2일 기준')==date(2010,1,2)


def test_chunk_coverage_and_bound():
    text='가나다라마바사'*1000
    covered=set()
    for offset,body in chunks(text):
        assert len(body)<=1200
        assert text[offset:offset+len(body)]==body
        covered.update(range(offset,offset+len(body)))
    assert covered==set(range(len(text)))
    assert 'history-body-v1' in model_key()


@pytest.mark.asyncio
async def test_ambiguous_version_not_arbitrarily_chosen(monkeypatch):
    pool=AsyncMock()
    pool.fetch.return_value=[dict(id=1,promulgation_date='2010-01-01',mst='1'),dict(id=2,promulgation_date='2010-01-02',mst='2')]
    monkeypatch.setattr(search,'get_pool',AsyncMock(return_value=pool))
    with pytest.raises(search.HistoryUnavailable,match='법령버전 1'):
        await search.select_version('1',date(2010,1,3))
    pool.fetchrow.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('stream',[False,True])
async def test_chat_history_never_calls_current_rag(monkeypatch,stream):
    from app.services import chat_service as chat
    monkeypatch.setattr(chat,'_fetch_history',AsyncMock(return_value=[]))
    save=AsyncMock()
    monkeypatch.setattr(chat,'_save_history',save)
    monkeypatch.setattr(chat,'_fetch_rag_and_web_context',AsyncMock(side_effect=AssertionError('current path')))
    async def answer(query,event):
        event(dict(type='tool',id='history',tool='history_lookup',status='needs_input',context='기준일 필요'))
        return '시점 확인 필요'
    monkeypatch.setattr(chat,'history_answer',answer)
    if stream:
        events=[e async for e in chat.stream_chat_response('2010년 소득세법',str(uuid4()),str(uuid4()))]
        assert events[-1]['text']=='시점 확인 필요'
    else:
        result,_=await chat.process_chat('2010년 소득세법',str(uuid4()),str(uuid4()))
        assert result=='시점 확인 필요'
    save.assert_awaited_once()


@pytest.mark.asyncio
async def test_unprepared_vectors_abstain(monkeypatch):
    pool=AsyncMock()
    pool.fetch.return_value=[{'key':'a:test'}]
    pool.fetchval.return_value=1
    monkeypatch.setattr(search,'get_pool',AsyncMock(return_value=pool))
    embed=AsyncMock(side_effect=AssertionError('not ready'))
    monkeypatch.setattr(search,'embed_texts',embed)
    with pytest.raises(search.HistoryUnavailable,match='준비 중'):
        await search.semantic({'snapshot_id':1},'질문')
    embed.assert_not_called()
