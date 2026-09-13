"""Real Cypher/driver regression tests. Default pytest skips without Docker access."""
import json
import subprocess

import pytest

from app.services.graph.index_service import build_graph
from app.services.graph.store import neighbors, save_graph

pytestmark = pytest.mark.integration


async def assert_roundtrip(nodes, edges):
    assert edges
    seed = edges[0]['source']
    expected = {(e['target'], e['reference']) for e in edges if e['source'] == seed}
    for _ in range(2):
        await save_graph(nodes, edges)
        found = await neighbors([seed])
        assert {(e['target_key'], e['reference']) for e in found} == expected
        assert len(found) == len(expected)
    await save_graph(nodes, [])
    assert await neighbors([seed]) == []


@pytest.mark.asyncio
async def test_synthetic_roundtrip(isolated_neo4j):
    rows = [dict(law_name='그래프검증법', article_no='제1조', article_title='',
                 article_text='「그래프검증법」 제2조에 따른다.', effective_date='20200101', amendment_date=''),
            dict(law_name='그래프검증법', article_no='제2조', article_title='',
                 article_text='제2조(대상) 검증용 합성 원문', effective_date='20200101', amendment_date='')]
    nodes, edges, unresolved = build_graph(rows)
    assert unresolved == 0
    assert len(edges) == 1
    await assert_roundtrip(nodes, edges)


@pytest.fixture
def public_sample(request):
    if not request.config.getoption('--run-neo4j') or not request.config.getoption('--graph-real-sample'):
        pytest.skip('Requires --run-neo4j --graph-real-sample and running tax_backend')
    # Existing backend is read-only; all writes use isolated_neo4j.
    code = '''import asyncio, json
from app.services.graph.index_service import load_articles, build_graph
from app.database import close_pool
async def main():
    try:
        nodes, edges, _ = build_graph(await load_articles())
        edges = edges[:20]
        keys = {e[k] for e in edges for k in ('source', 'target')}
        print(json.dumps([[n for n in nodes if n['key'] in keys], edges]))
    finally:
        await close_pool()
asyncio.run(main())
'''
    try:
        result = subprocess.run(['docker', 'exec', 'tax_backend', 'python', '-c', code],
                                capture_output=True, text=True, check=True, timeout=60)
        nodes, edges = json.loads(result.stdout)
    except (subprocess.SubprocessError, OSError, ValueError):
        pytest.fail('Could not read public-law sample from tax_backend', pytrace=False)
    assert edges, 'No resolvable public-law sample'
    return nodes, edges


@pytest.mark.asyncio
async def test_public_law_roundtrip(public_sample, isolated_neo4j):
    await assert_roundtrip(*public_sample)
