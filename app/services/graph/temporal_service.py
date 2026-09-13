"""Observed graph snapshots, NOT inferred legal validity intervals.

Only exact recorded dates are queryable. No carry-forward/backward substitution.
Law-level publication/effect dates cannot establish article-level applicability.
"""
import hashlib
import json
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from neo4j import Query
import config
from app.services.graph.store import connect


def parse_date(value: str) -> date:
    if re.fullmatch(r'\d{8}', value):
        value = f'{value[:4]}-{value[4:6]}-{value[6:]}'
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Expected YYYY-MM-DD or YYYYMMDD')
    return date.fromisoformat(value)


def prepare_snapshot(nodes, edges, observed_on: date):
    selected = {}
    for node in nodes:
        try:
            published = parse_date(node.get('amendment_date', ''))
            effective = parse_date(node.get('effective_date', ''))
        except (ValueError, TypeError):
            continue
        if published > observed_on or effective > observed_on:
            continue
        selected[node['key']] = dict(node, published_on=published.isoformat(),
                                     effective_on=effective.isoformat())
    eligible_edges = {(e['source'], e['target'], e['reference']): dict(e)
                      for e in edges if e['source'] in selected and e['target'] in selected}
    canonical = {'observed_on': observed_on.isoformat(),
                 'nodes': sorted(selected.values(), key=lambda n: n['key']),
                 'edges': sorted(eligible_edges.values(), key=lambda e: (e['source'], e['target'], e['reference']))}
    key = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return key, list(selected.values()), list(eligible_edges.values())


async def save_snapshot(nodes, edges):
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    key, selected, links = prepare_snapshot(nodes, edges, now.date())
    if not selected:
        raise ValueError('No dated nodes eligible for snapshot')
    async with connect() as driver:
        for label in ('TaxGraphSnapshot', 'TaxTemporalArticle'):
            await driver.execute_query(
                f'CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.key IS UNIQUE',
                database_=config.NEO4J_DATABASE)
        async def write(tx):
            result = await tx.run('''
                MERGE (s:TaxGraphSnapshot {key:$key})
                ON CREATE SET s.observed_on=$day, s.recorded_at=$now,
                  s.basis='observed_snapshot', s.scope='all',
                  s.node_count=$count, s.edge_count=$edge_count
                WITH s UNWIND $nodes AS row
                MERGE (n:TaxTemporalArticle {key:$key + ':' + row.key})
                ON CREATE SET n.version_key=row.key, n.law_name=row.law_name,
                  n.article_no=row.article_no, n.published_on=row.published_on,
                  n.effective_on=row.effective_on
                MERGE (s)-[:HAS_VERSION]->(n)
            ''', key=key, day=now.date().isoformat(), now=now.isoformat(),
                count=len(selected), edge_count=len(links), nodes=selected)
            await result.consume()
            result = await tx.run('''
                UNWIND $edges AS row
                MATCH (a:TaxTemporalArticle {key:$key + ':' + row.source})
                MATCH (b:TaxTemporalArticle {key:$key + ':' + row.target})
                MERGE (a)-[r:CITES_AT {reference:row.reference}]->(b)
                ON CREATE SET r.evidence=row.evidence, r.snapshot_key=$key
            ''', key=key, edges=links)
            await result.consume()
        async with driver.session(database=config.NEO4J_DATABASE) as session:
            await session.execute_write(write)
    return {'snapshot_key': key, 'observed_on': now.date().isoformat(),
            'nodes': len(selected), 'edges': len(links), 'excluded_nodes': len(nodes)-len(selected)}


async def query_snapshot(as_of: str, law_name: str, article_no: str, limit: int = 50):
    day = parse_date(as_of).isoformat()
    if not 1 <= limit <= 100:
        raise ValueError('limit must be 1..100')
    response = {'as_of': day, 'basis': 'observed_snapshot',
                'legal_applicability_verified': False, 'nodes': [], 'edges': []}
    async with connect() as driver:
        snapshots, _, _ = await driver.execute_query(Query('''
            MATCH (s:TaxGraphSnapshot {observed_on:$day, scope:'all'})
            RETURN s.key AS key, s.recorded_at AS recorded_at
            ORDER BY recorded_at DESC, key LIMIT 1
        ''', timeout=2), day=day, database_=config.NEO4J_DATABASE, routing_='r')
        if not snapshots:
            return response | {'status': 'unknown', 'reason': 'no_snapshot_for_date'}
        snapshot = dict(snapshots[0])
        rows, _, _ = await driver.execute_query(Query('''
            MATCH (s:TaxGraphSnapshot {key:$key})-[:HAS_VERSION]->(a:TaxTemporalArticle)
            WHERE a.law_name=$law AND a.article_no=$article
              AND a.published_on <= $day AND a.effective_on <= $day
            OPTIONAL MATCH (a)-[r:CITES_AT]->(b:TaxTemporalArticle)
            WHERE r.snapshot_key=$key AND b.published_on <= $day AND b.effective_on <= $day
              AND EXISTS { MATCH (s)-[:HAS_VERSION]->(b) }
            RETURN properties(a) AS source, properties(r) AS edge, properties(b) AS target
            ORDER BY b.key, r.reference LIMIT $limit
        ''', timeout=2), key=snapshot['key'], law=law_name, article=article_no, day=day,
            limit=limit+1, database_=config.NEO4J_DATABASE, routing_='r')
        if not rows:
            return response | {'status': 'unknown', 'reason': 'article_not_in_snapshot', 'snapshot': snapshot}
        nodes = {}
        for row in rows[:limit]:
            nodes[row['source']['key']] = row['source']
            if row['target']:
                nodes[row['target']['key']] = row['target']
                response['edges'].append(row['edge'] | {'source': row['source']['key'], 'target': row['target']['key']})
        return response | {'status': 'observed', 'snapshot': snapshot,
                           'nodes': list(nodes.values()), 'truncated': len(rows)>limit}
