from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import chat_service as chat
from app.services.tools.executor import ToolRun


@pytest.mark.asyncio
@pytest.mark.parametrize('tool', ['law_lookup', 'document_search'])
@pytest.mark.parametrize('status', ['invalid_arguments','needs_input','not_found','timeout','error'])
@pytest.mark.parametrize('stream', [False,True])
async def test_lookup_failure_never_generates_or_searches(monkeypatch,tool,status,stream):
    async def run(*args,on_event,**kwargs):
        on_event({'type':'tool','id':'primary','tool':tool,'status':status,'context':'UNTRUSTED_ERROR'})
        return ToolRun(tool,status,'UNTRUSTED_ERROR')
    monkeypatch.setattr(chat,'run_tools_for_query',run)
    monkeypatch.setattr(chat,'_fetch_history',AsyncMock(return_value=[]))
    save=AsyncMock()
    monkeypatch.setattr(chat,'_save_history',save)
    blocked={}
    for name in ('_generate_answer','_stream_llm_skip_think','_append_source_list_if_missing','hybrid_search','tavily_search'):
        blocked[name]=AsyncMock(side_effect=AssertionError('must not call'))
        monkeypatch.setattr(chat,name,blocked[name])
    if stream:
        events=[e async for e in chat.stream_chat_response('질문',str(uuid4()),str(uuid4()))]
        answer=''.join(e['text'] for e in events if e['type']=='chunk')
        assert events[0]['status']==status
    else:
        events=[]
        answer,calculator=await chat.process_chat('질문',str(uuid4()),str(uuid4()),tool_events=events)
        assert calculator is None
    assert '판단은 유보' in answer
    assert 'UNTRUSTED_ERROR' not in answer
    save.assert_awaited_once()
    assert save.call_args.args[2]==answer
    assert save.call_args.kwargs['tools'][0]['status']==status
    for mock in blocked.values():
        mock.assert_not_called()


def test_success_and_progress_do_not_abstain():
    for status in ('ok','selecting','running'):
        assert chat._failed_tool_answer([{'tool':'law_lookup','status':status}]) is None


def test_failure_causes_have_distinct_actions():
    def answer(status):
        return chat._failed_tool_answer([{'tool':'law_lookup','status':status}])
    assert '번호를 확인' in answer('invalid_arguments')
    assert '공식 원문' in answer('not_found')
    assert '시간이 초과' in answer('timeout')
    assert '다시 시도' in answer('error')
