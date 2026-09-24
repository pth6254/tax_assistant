from unittest.mock import AsyncMock
import pytest
from app.services.law import history_answer as service
from app.services.search.history_search import HistoryUnavailable


@pytest.mark.asyncio
async def test_missing_history_never_generates(monkeypatch):
    monkeypatch.setattr(service,'retrieve',AsyncMock(side_effect=HistoryUnavailable('조회 기준일 필요')))
    model=AsyncMock(side_effect=AssertionError('must not generate'))
    monkeypatch.setattr(service,'call_llm_structured',model)
    events=[]
    answer=await service.answer('2010년 기준',events.append)
    assert '유보' in answer and events[-1]['status']=='needs_input'
    model.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('source,quote,accepted',[(1,'원문에 실제로 있는 문장입니다.',True),
    (9,'원문에 실제로 있는 문장입니다.',False),(1,'원문에는 존재하지 않는 문장입니다.',False)])
async def test_generated_evidence_must_match(monkeypatch,source,quote,accepted):
    item=dict(content='원문에 실제로 있는 문장입니다.',law_name='시험법',article_no='제1조',
        version_id=1,source_url='https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=1&efYd=20100101',
        promulgation_date='2009-01-01',effective_date='2010-01-01',graph_evidence='')
    monkeypatch.setattr(service,'retrieve',AsyncMock(return_value={'results':[item],'as_of':'2010-01-01','graph_status':'checked'}))
    monkeypatch.setattr(service,'call_llm_structured',AsyncMock(return_value={'claims':[
        {'explanation':'검증 대상 설명','source':source,'quote':quote}]}))
    answer=await service.answer('질문')
    assert ('검증 대상 설명' in answer)==accepted
    assert 'efYd=20100101' in answer
    assert '[법률]' not in answer
