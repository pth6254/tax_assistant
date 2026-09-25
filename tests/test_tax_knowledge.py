from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.graph import knowledge_service as knowledge
from app.services.law.history_parser import sha, tree
from app.services.law.history_structure import article_excerpt
from app.services.law.reference_parser import parse_law_reference
from app.services.search import history_search


def sample():
    import xml.etree.ElementTree as ET
    xml = '''<조문단위><조문내용>제1조의2(정의)</조문내용>
      <항><항번호>①</항번호><항내용>① 용어의 뜻은 다음과 같다.</항내용>
        <호><호번호>1.</호번호><호내용>1. "거주자"란 국내에 주소를 둔 개인을 말한다.</호내용></호>
        <호><호번호>2.</호번호><호내용>2. "비거주자"란 거주자가 아닌 개인을 말한다.</호내용></호>
        <호><호번호>3.</호번호><호내용>3. 「법인세법」 제2조제1호에 따른다.</호내용>
          <목><목번호>가.</목번호><목내용>가. 해당하는 법인</목내용></목></호>
      </항></조문단위>'''
    root = ET.fromstring(xml)
    tags = {'조문내용', '항번호', '항내용', '호번호', '호내용', '목번호', '목내용'}
    body = '\n'.join((node.text or '').strip() for node in root.iter()
                     if node.tag in tags and (node.text or '').strip())
    version = dict(id=7, law_id='001', law_name='소득세법', snapshot_id=9,
                   source_url='https://www.law.go.kr/', effective_date=date(2026, 1, 1),
                   promulgation_date=date(2025, 12, 31))
    article = dict(article_number='1', article_branch='2', unit_kind='조문', body=body,
                   content_hash=sha(body), structure=tree(root))
    return version, article


def test_provision_identity_and_explicit_relations_are_version_scoped():
    version, article = sample()
    provisions, concepts, references, assertions = knowledge.build(version, [article])
    assert len(provisions) == 6
    assert {p['reference'] for p in provisions} == {
        '제1조의2', '제1조의2 제1항', '제1조의2 제1항 제1호',
        '제1조의2 제1항 제2호', '제1조의2 제1항 제3호',
        '제1조의2 제1항 제3호 가목'}
    assert {c['name'] for c in concepts} == {'거주자', '비거주자'}
    assert len(references) == 1 and references[0]['law_name'] == '법인세법'
    assert {a['kind'] for a in assertions} == {'DEFINES', 'CITES'}
    assert knowledge.build(version | {'snapshot_id': 10}, [article])[0][0]['key'] != provisions[0]['key']
    assert knowledge._matched_terms('비거주자 정의', ['거주자', '비거주자']) == {'비거주자'}


@pytest.mark.asyncio
async def test_only_reviewed_exact_snapshot_definition_becomes_evidence(monkeypatch):
    version, article = sample()
    provisions, concepts, _, assertions = knowledge.build(version, [article])
    definition = next(a for a in assertions if a['kind'] == 'DEFINES'
                      and a['target'] == next(c['key'] for c in concepts if c['name'] == '거주자'))
    provision = next(p for p in provisions if p['key'] == definition['source'])
    driver = AsyncMock()
    driver.execute_query.return_value = ([dict(provision=provision, assertion=definition, term='거주자')], None, None)
    connection = MagicMock()
    connection.__aenter__ = AsyncMock(return_value=driver)
    connection.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(knowledge, 'connect', lambda: connection)
    pool = AsyncMock()
    pool.fetchrow.return_value = article
    monkeypatch.setattr(knowledge, 'get_pool', AsyncMock(return_value=pool))

    assert await knowledge.reviewed_definitions(version, '비거주자 정의') == []
    found = await knowledge.reviewed_definitions(version, '거주자 정의')
    assert len(found) == 1
    assert found[0]['requested_reference'] == '제1조의2 제1항 제1호'
    assert found[0]['knowledge_assertion_id'] == definition['key']
    assert '국내에 주소' in found[0]['content']
    article['content_hash'] = 'changed'
    assert await knowledge.reviewed_definitions(version, '거주자 정의') == []


@pytest.mark.asyncio
async def test_review_rechecks_source_and_relation(monkeypatch):
    version, article = sample()
    provisions, concepts, _, assertions = knowledge.build(version, [article])
    term = next(c for c in concepts if c['name'] == '거주자')
    claim = next(a for a in assertions if a['kind'] == 'DEFINES' and a['target'] == term['key'])
    provision = next(p for p in provisions if p['key'] == claim['source'])
    driver = AsyncMock()
    driver.execute_query.side_effect = [([dict(provision=provision, assertion=claim,
        target_labels=['TaxConcept'], target=term)], None, None), ([], None, None)]
    connection = MagicMock()
    connection.__aenter__ = AsyncMock(return_value=driver)
    connection.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(knowledge, 'connect', lambda: connection)
    pool = AsyncMock()
    pool.fetchrow.return_value = article
    monkeypatch.setattr(knowledge, 'get_pool', AsyncMock(return_value=pool))
    assert (await knowledge.review(claim['key'], approve=True, reviewer='test-reviewer'))['status'] == 'reviewed'
    assert driver.execute_query.await_count == 2


@pytest.mark.asyncio
async def test_reviewed_citation_requires_source_quote_and_resolved_version(monkeypatch):
    version, article = sample()
    provisions, _, _, assertions = knowledge.build(version, [article])
    citation = next(a for a in assertions if a['kind'] == 'CITES')
    provision = next(p for p in provisions if p['key'] == citation['source'])
    claim = dict(provision=provision, assertion=citation,
                 target_law='법인세법', target_reference='제2조 제1호')
    monkeypatch.setattr(history_search, 'reviewed_citations', AsyncMock(return_value=[claim]))
    pool = AsyncMock()
    pool.fetchrow.return_value = article
    pool.fetch.return_value = [dict(law_id='corporation')]
    monkeypatch.setattr(history_search, 'get_pool', AsyncMock(return_value=pool))
    monkeypatch.setattr(history_search, 'select_version', AsyncMock(return_value={'id': 99}))
    target = dict(version_id=99, article_no='제2조', requested_reference='제2조 제1호',
                  content='1. 내국법인', graph_evidence='')
    monkeypatch.setattr(history_search, 'direct_article', AsyncMock(return_value=target))
    full = article_excerpt(article['structure'], article['body'], parse_law_reference('제1조의2'))
    seed = dict(version_id=version['id'], article_no='제1조의2', content=full)

    added = await history_search.expand_reviewed_citations(version, [seed], date(2026, 1, 1))
    assert len(added) == 1
    assert added[0]['knowledge_assertion_id'] == citation['key']
    assert await history_search.expand_reviewed_citations(
        version, [seed | {'content': '요청 범위에 인용 없음'}], date(2026, 1, 1)) == []


@pytest.mark.asyncio
async def test_full_sync_resumes_from_atomic_snapshot_checkpoints(monkeypatch):
    pool = AsyncMock()
    pool.fetch.return_value = [dict(id=7, snapshot_id=9), dict(id=8, snapshot_id=10)]
    monkeypatch.setattr(knowledge, 'get_pool', AsyncMock(return_value=pool))
    driver = AsyncMock()
    driver.execute_query.return_value = ([dict(snapshot_id=9)], None, None)
    connection = MagicMock()
    connection.__aenter__ = AsyncMock(return_value=driver)
    connection.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(knowledge, 'connect', lambda: connection)
    version, article = sample()
    version['id'], version['snapshot_id'] = 8, 10
    monkeypatch.setattr(knowledge, 'source_version', AsyncMock(return_value=(version, [article])))
    write = AsyncMock()
    monkeypatch.setattr(knowledge, '_write', write)
    monkeypatch.setattr(knowledge, '_ensure_constraints', AsyncMock())

    preview = await knowledge.sync_all()
    assert (preview['total'], preview['already_complete'], preview['pending']) == (2, 1, 1)
    assert write.await_count == 0
    applied = await knowledge.sync_all(apply=True)
    assert applied['completed'] == 1
    assert applied['provisions'] == 6
    assert write.await_args.kwargs['complete'] is True
