"""Read-only verification of the graph against current PostgreSQL law text.

Run: docker exec tax_backend python scripts/audit_law_graph.py
Reports consistency, not legal correctness or retrieval quality.
"""
import asyncio
from collections import Counter
import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from app.database import close_pool
from app.services.graph.index_service import article_key, build_graph, effective_now, law_key, load_articles
from app.services.graph.store import connect
from app.services.law.reference_parser import parse_law_reference
from app.services.law.relation_extractor import extract_relations
from app.services.law.structure_parser import resolve_reference_target


async def main():
    try:
        rows = await load_articles()
        nodes, edges, unresolved = build_graph(rows)
        current = {article_key(r): r for r in rows if effective_now(r)}
        expected = {(e['source'], e['target'], e['reference']) for e in edges}
        async with connect() as driver:
            stored, _, _ = await driver.execute_query(
                'MATCH (n:TaxArticle) RETURN n.key AS key', database_=config.NEO4J_DATABASE)
            links, _, _ = await driver.execute_query('''
                MATCH (s:TaxArticle)-[r:CITES]->(t:TaxArticle)
                RETURN s.key AS source, t.key AS target,
                       r.reference AS reference, r.evidence AS evidence,
                       r.status AS status
                ORDER BY source, target, reference
            ''', database_=config.NEO4J_DATABASE)
        actual = {(r['source'], r['target'], r['reference']) for r in links}
        node_keys = {r['key'] for r in stored}
        problems = Counter()
        samples, sample_groups = [], set()
        for edge in links:
            source, target = current.get(edge['source']), current.get(edge['target'])
            if not source or not target:
                problems['noncurrent_endpoint'] += 1
                continue
            if not edge['evidence'] or edge['evidence'] not in source['article_text']:
                problems['evidence_not_in_source'] += 1
            ref = parse_law_reference(edge['reference'])
            if ref.article_no != target['article_no']:
                problems['wrong_article'] += 1
            resolved = resolve_reference_target(target['article_text'], ref)
            if resolved is not None and not resolved.exists:
                problems['missing_subdivision'] += 1
            if edge['status'] != 'resolved':
                problems['unexpected_status'] += 1
            group = (source['law_name'], target['law_name'], bool(ref.paragraph), bool(ref.article_branch))
            if group not in sample_groups and len(samples) < 20:
                sample_groups.add(group)
                pos = source['article_text'].find(edge['evidence'])
                samples.append({
                    'source': source['law_name'] + ' ' + source['article_no'],
                    'target': target['law_name'] + ' ' + edge['reference'],
                    'evidence': edge['evidence'],
                    'context': source['article_text'][max(0, pos-35):pos+len(edge['evidence'])+70],
                })
        lookup = {}
        for row in current.values():
            lookup.setdefault((law_key(row['law_name']), row['article_no']), []).append(row)
        reasons, missing_laws = Counter(), Counter()
        for row in current.values():
            for candidate in extract_relations(row['article_text']):
                targets = lookup.get((law_key(candidate['law_name']), candidate['article_no']), [])
                if not targets:
                    reasons['target_absent_from_eligible_snapshot'] += 1
                    missing_laws[candidate['law_name']] += 1
                elif len(targets) > 1:
                    reasons['ambiguous_target'] += 1
                else:
                    resolved = resolve_reference_target(targets[0]['article_text'], parse_law_reference(candidate['reference']))
                    if resolved is not None and not resolved.exists:
                        reasons['missing_' + resolved.level] += 1
        result = dict(
            graph_rag_enabled=config.GRAPH_RAG_ENABLED,
            expected_nodes=len(nodes), stored_nodes=len(stored),
            missing_nodes=len(set(current)-node_keys), stale_nodes=len(node_keys-set(current)),
            raw_candidates=len(edges), expected_unique_edges=len(expected), stored_edges=len(links),
            duplicate_nodes=len(stored)-len(node_keys), duplicate_edges=len(links)-len(actual),
            missing_edges=len(expected-actual), unexpected_edges=len(actual-expected),
            integrity_problems=dict(problems), unresolved=unresolved,
            unresolved_reasons=dict(reasons), missing_target_laws=missing_laws.most_common(10),
            law_count=len({r['law_name'] for r in current.values()}), samples=samples,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if (problems or result['missing_nodes'] or result['stale_nodes'] or result['duplicate_nodes']
                or result['duplicate_edges'] or result['missing_edges'] or result['unexpected_edges']):
            return 1
        return 0
    finally:
        await close_pool()


if __name__ == '__main__':
    logging.getLogger('neo4j').setLevel(logging.ERROR)
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as error:
        print('Graph audit failed: ' + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
