"""Version-scoped, review-gated knowledge relations from preserved law XML."""
import hashlib
import json
import re

from neo4j import Query

import config
from app.database import get_pool
from app.services.graph.store import connect
from app.services.law.history_parser import sha
from app.services.law.history_structure import article_excerpt, lead, number, units
from app.services.law.reference_parser import format_article_no, parse_law_reference
from app.services.law.relation_extractor import extract_relations


_DEFINITION = re.compile(r'["“](?P<term>[^"”\n]{2,40})["”](?:이|가|은|는)?란\b')
_KINDS = ('항', '호', '목')


def _key(*parts):
    return hashlib.sha256('|'.join(map(str, parts)).encode('utf-8')).hexdigest()


def _walk(node, reference, snapshot_id, parent=None, seen=None):
    """Only numbered XML units become provisions; no text-only guessed units."""
    if seen is None:
        seen = {}
    own = lead(node)
    if not own.strip():
        return
    natural_key = _key('provision', snapshot_id, reference)
    occurrence = seen.get(natural_key, 0)
    seen[natural_key] = occurrence + 1
    key = natural_key if occurrence == 0 else _key('provision-occurrence', natural_key, occurrence)
    yield dict(key=key, parent=parent, reference=reference, quote=own,
               source_hash=sha(own), snapshot_id=snapshot_id, occurrence=occurrence)
    for kind in _KINDS:
        for child in units(node, kind):
            value = number(child, kind)
            if value is None or value == '':
                continue
            if kind == '항':
                label = f'제{value}항'
            elif kind == '호':
                label = f'제{value[0]}호' + (f'의{value[1]}' if value[1] else '')
            else:
                label = f'{value}목'
            yield from _walk(child, f'{reference} {label}', snapshot_id, key, seen)


def build(version, articles):
    """Extract explicit definitions and named citations as review candidates."""
    provisions, concepts, references, assertions = [], {}, {}, []
    seen = {}
    for row in articles:
        if row['unit_kind'] != '조문' or not row['article_number'].isdigit():
            continue
        if sha(row['body']) != row['content_hash']:
            raise ValueError('Source article body hash mismatch')
        article_no = format_article_no(int(row['article_number']), int(row['article_branch'] or 0) or None)
        structure = json.loads(row['structure']) if isinstance(row['structure'], str) else row['structure']
        for provision in _walk(structure, article_no, version['snapshot_id'], seen=seen):
            provision.update(version_id=version['id'], law_id=version['law_id'],
                             law_name=version['law_name'], article_no=article_no,
                             article_number=row['article_number'], article_branch=row['article_branch'],
                             article_hash=row['content_hash'], source_url=version['source_url'],
                             source_article_id=row['id'], source_order=row['source_order'])
            provisions.append(provision)
            quote = provision['quote']
            for match in _DEFINITION.finditer(quote):
                term = match['term'].strip()
                if not term or len(term) > 40:
                    continue
                target = _key('concept', version['law_id'], term)
                concepts[target] = dict(key=target, law_id=version['law_id'], name=term)
                assertions.append(dict(key=_key('assertion', provision['key'], 'DEFINES', target, quote),
                    source=provision['key'], target=target, kind='DEFINES', quote=quote,
                    source_hash=provision['source_hash']))
            for ref in extract_relations(quote):
                target = _key('reference', ''.join(ref['law_name'].split()), ref['reference'])
                references[target] = dict(key=target, law_name=ref['law_name'], reference=ref['reference'])
                assertions.append(dict(key=_key('assertion', provision['key'], 'CITES', target, ref['evidence']),
                    source=provision['key'], target=target, kind='CITES', quote=ref['evidence'],
                    source_hash=provision['source_hash']))
    return provisions, list(concepts.values()), list(references.values()), assertions


async def source_version(version_id, article_no=None, *, allow_empty=False):
    pool = await get_pool()
    version = await pool.fetchrow('''SELECT v.id,v.law_id,v.law_name,v.law_type,
        v.effective_date,v.promulgation_date,s.id AS snapshot_id,s.source_url
        FROM law_history.versions v JOIN law_history.snapshots s ON s.version_id=v.id
        WHERE v.id=$1 AND v.fetch_status='complete' ORDER BY s.collected_at DESC,s.id DESC LIMIT 1''', version_id)
    if not version:
        raise ValueError('Completed law version with snapshot required')
    version = dict(version)
    sql = '''SELECT id,source_order,article_number,article_branch,unit_kind,body,content_hash,structure
        FROM law_history.articles WHERE snapshot_id=$1 AND unit_kind='조문' '''
    args = [version['snapshot_id']]
    if article_no:
        ref = parse_law_reference(article_no)
        if ref.article is None or ref.paragraph is not None or ref.item is not None or ref.subitem:
            raise ValueError('Select one complete article, without a subdivision')
        sql += ' AND article_number=$2 AND article_branch=$3'
        args.extend([str(ref.article), str(ref.article_branch or '')])
    sql += ' ORDER BY article_number,article_branch,source_order,id'
    articles = [dict(r) for r in await pool.fetch(sql, *args)]
    if not articles and not allow_empty:
        raise ValueError('No source articles in selected scope')
    return version, articles


async def _ensure_constraints(driver):
    for label in ('TaxProvision', 'TaxConcept', 'TaxReference', 'KnowledgeAssertion'):
        await driver.execute_query(f'CREATE CONSTRAINT {label.lower()}_key IF NOT EXISTS '
                                   f'FOR (n:{label}) REQUIRE n.key IS UNIQUE',
                                   database_=config.NEO4J_DATABASE)
    await driver.execute_query('''CREATE CONSTRAINT knowledgesync_snapshot IF NOT EXISTS
        FOR (n:KnowledgeSync) REQUIRE n.snapshot_id IS UNIQUE''',
        database_=config.NEO4J_DATABASE)


async def _write(driver, version, provisions, concepts, references, assertions, counts,
                 *, complete, replace=False):
    async with driver.session(database=config.NEO4J_DATABASE) as session:
        async def write(tx):
            if replace:
                result = await tx.run('''MATCH (s:HistorySnapshot {id:$snapshot})
                    -[:HAS_KG_PROVISION]->(p:TaxProvision)
                    -[:SUBJECT_OF]->(a:KnowledgeAssertion {review_status:'reviewed'})
                    RETURN count(a) AS total''', snapshot=version['snapshot_id'])
                if (await result.single())['total']:
                    raise ValueError(f'Snapshot {version["snapshot_id"]} has reviewed relations')
                await (await tx.run('''MATCH (s:HistorySnapshot {id:$snapshot})
                    -[:HAS_KG_PROVISION]->(p:TaxProvision)
                    -[:SUBJECT_OF]->(a:KnowledgeAssertion) DETACH DELETE a''',
                    snapshot=version['snapshot_id'])).consume()
                await (await tx.run('''MATCH (s:HistorySnapshot {id:$snapshot})
                    -[:HAS_KG_PROVISION]->(p:TaxProvision)
                    DETACH DELETE p''', snapshot=version['snapshot_id'])).consume()
            await (await tx.run('''UNWIND $rows AS row
                MATCH (s:HistorySnapshot {id:row.snapshot_id})
                MERGE (p:TaxProvision {key:row.key}) SET p += row
                MERGE (s)-[:HAS_KG_PROVISION]->(p)''', rows=provisions)).consume()
            await (await tx.run('''UNWIND $rows AS row
                WITH row WHERE row.parent IS NOT NULL
                MATCH (p:TaxProvision {key:row.key})
                MATCH (parent:TaxProvision {key:row.parent})
                MERGE (p)-[:CHILD_OF]->(parent)''', rows=provisions)).consume()
            await (await tx.run('UNWIND $rows AS row MERGE (c:TaxConcept {key:row.key}) SET c += row',
                                rows=concepts)).consume()
            await (await tx.run('UNWIND $rows AS row MERGE (c:TaxReference {key:row.key}) SET c += row',
                                rows=references)).consume()
            await (await tx.run('''UNWIND $rows AS row
                MATCH (source:TaxProvision {key:row.source})
                MATCH (target {key:row.target})
                WHERE target:TaxConcept OR target:TaxReference
                MERGE (a:KnowledgeAssertion {key:row.key})
                ON CREATE SET a.review_status='candidate'
                SET a.kind=row.kind,a.quote=row.quote,a.source_hash=row.source_hash
                MERGE (source)-[:SUBJECT_OF]->(a)
                MERGE (a)-[:OBJECT]->(target)''', rows=assertions)).consume()
            if complete:
                await (await tx.run('''MERGE (m:KnowledgeSync {snapshot_id:$snapshot})
                    SET m.version_id=$version,m.article_count=$articles,
                        m.provision_count=$provisions,m.assertion_count=$assertions,
                        m.unique_assertion_count=$unique_assertions,
                        m.duplicate_repaired=$replaced,
                        m.completed_at=datetime()''', snapshot=version['snapshot_id'],
                    version=version['id'], articles=counts['articles'],
                    provisions=counts['provisions'], assertions=counts['assertions'],
                    unique_assertions=len({a['key'] for a in assertions}), replaced=replace)).consume()
        await session.execute_write(write)


async def sync(version_id, article_no=None, *, apply=False):
    version, articles = await source_version(version_id, article_no)
    provisions, concepts, references, assertions = build(version, articles)
    counts = dict(snapshot_id=version['snapshot_id'], articles=len(articles), provisions=len(provisions),
                  concepts=len(concepts), references=len(references), assertions=len(assertions))
    if not apply:
        return counts
    async with connect() as driver:
        await _ensure_constraints(driver)
        await _write(driver, version, provisions, concepts, references, assertions,
                     counts, complete=article_no is None)
    return counts


async def sync_all(*, apply=False, limit=None, progress=None):
    """Resume complete-version syncs; a checkpoint commits with each snapshot."""
    if limit is not None and limit < 1:
        raise ValueError('Limit must be positive')
    pool = await get_pool()
    versions = await pool.fetch('''SELECT v.id,s.id AS snapshot_id FROM law_history.versions v
        JOIN LATERAL (SELECT id FROM law_history.snapshots WHERE version_id=v.id
            ORDER BY collected_at DESC,id DESC LIMIT 1) s ON true
        WHERE v.fetch_status='complete' ORDER BY v.id''')
    async with connect() as driver:
        checkpoint_rows, _, _ = await driver.execute_query(Query('''MATCH (m:KnowledgeSync)
            RETURN m.snapshot_id AS snapshot_id''', timeout=10),
            database_=config.NEO4J_DATABASE, routing_='r')
        done = {row['snapshot_id'] for row in checkpoint_rows}
        pending = [row for row in versions if row['snapshot_id'] not in done]
        selected = pending[:limit] if limit is not None else pending
        report = dict(total=len(versions), already_complete=len(done.intersection(
            row['snapshot_id'] for row in versions)), pending=len(pending), selected=len(selected),
            next_version_id=selected[0]['id'] if selected else None,
            completed=0, empty_article_snapshots=0, articles=0, provisions=0, assertions=0)
        if not apply:
            return report
        await _ensure_constraints(driver)
        for row in selected:
            try:
                version, articles = await source_version(row['id'], allow_empty=True)
                provisions, concepts, references, assertions = build(version, articles)
            except ValueError as exc:
                raise ValueError(f'Version {row["id"]} source validation: {exc}') from exc
            counts = dict(snapshot_id=version['snapshot_id'], articles=len(articles),
                          provisions=len(provisions), concepts=len(concepts),
                          references=len(references), assertions=len(assertions))
            await _write(driver, version, provisions, concepts, references, assertions,
                         counts, complete=True)
            report['completed'] += 1
            if not articles:
                report['empty_article_snapshots'] += 1
            for name in ('articles', 'provisions', 'assertions'):
                report[name] += counts[name]
            if progress is not None:
                progress(report)
        return report


async def repair_duplicate_provisions(*, apply=False, progress=None):
    """Rebuild only snapshots where source references collide; reconcile assertion counts."""
    pool = await get_pool()
    rows = await pool.fetch('''SELECT v.id FROM law_history.versions v
        WHERE v.fetch_status='complete' ORDER BY v.id''')
    report = dict(total=len(rows), scanned=0, ambiguous_snapshots=0, duplicate_provisions=0,
                  repaired=0, already_repaired=0, reconciled=0)
    async with connect() as driver:
        done_rows, _, _ = await driver.execute_query(Query('''MATCH (m:KnowledgeSync)
            WHERE m.duplicate_repaired=true RETURN m.snapshot_id AS snapshot_id''', timeout=10),
            database_=config.NEO4J_DATABASE, routing_='r')
        done = {record['snapshot_id'] for record in done_rows}
        if apply:
            await _ensure_constraints(driver)
        updates = []
        for row in rows:
            version, articles = await source_version(row['id'], allow_empty=True)
            provisions, concepts, references, assertions = build(version, articles)
            duplicates = sum(bool(p['occurrence']) for p in provisions)
            report['scanned'] += 1
            if duplicates:
                report['ambiguous_snapshots'] += 1
                report['duplicate_provisions'] += duplicates
                if version['snapshot_id'] in done:
                    report['already_repaired'] += 1
                elif apply:
                    counts = dict(articles=len(articles), provisions=len(provisions),
                                  assertions=len(assertions))
                    await _write(driver, version, provisions, concepts, references,
                                 assertions, counts, complete=True, replace=True)
                    report['repaired'] += 1
            elif apply:
                updates.append(dict(snapshot=version['snapshot_id'],
                                    unique=len({a['key'] for a in assertions})))
                if len(updates) >= 250:
                    await driver.execute_query('''UNWIND $rows AS row
                        MATCH (m:KnowledgeSync {snapshot_id:row.snapshot})
                        SET m.unique_assertion_count=row.unique''',
                        rows=updates, database_=config.NEO4J_DATABASE)
                    report['reconciled'] += len(updates)
                    updates.clear()
            if progress is not None:
                progress(report)
        if apply and updates:
            await driver.execute_query('''UNWIND $rows AS row
                MATCH (m:KnowledgeSync {snapshot_id:row.snapshot})
                SET m.unique_assertion_count=row.unique''',
                rows=updates, database_=config.NEO4J_DATABASE)
            report['reconciled'] += len(updates)
    return report


async def audit_all():
    """Read-only coverage and materialized-node audit against immutable source IDs."""
    pool = await get_pool()
    sources = await pool.fetch('''SELECT s.id AS snapshot_id FROM law_history.versions v
        JOIN LATERAL (SELECT id FROM law_history.snapshots WHERE version_id=v.id
            ORDER BY collected_at DESC,id DESC LIMIT 1) s ON true
        WHERE v.fetch_status='complete' ORDER BY v.id''')
    source_ids = {row['snapshot_id'] for row in sources}
    async with connect() as driver:
        rows, _, _ = await driver.execute_query(Query('''MATCH (m:KnowledgeSync)
            RETURN m.snapshot_id AS snapshot_id,m.article_count AS article_count,
                   m.provision_count AS provision_count,m.assertion_count AS assertion_count,
                   m.unique_assertion_count AS unique_assertion_count''', timeout=10),
            database_=config.NEO4J_DATABASE, routing_='r')
        markers = {row['snapshot_id']: dict(row) for row in rows}
        counts = {}
        for label in ('TaxProvision', 'KnowledgeAssertion'):
            records, _, _ = await driver.execute_query(Query(
                f'MATCH (n:{label}) RETURN count(n) AS total', timeout=120),
                database_=config.NEO4J_DATABASE, routing_='r')
            counts[label] = records[0]['total']
        records, _, _ = await driver.execute_query(Query('''MATCH (a:KnowledgeAssertion)
            RETURN a.review_status AS status,count(a) AS total''', timeout=120),
            database_=config.NEO4J_DATABASE, routing_='r')
        reviews = {row['status']: row['total'] for row in records}
    missing = sorted(source_ids - markers.keys())
    extra = sorted(markers.keys() - source_ids)
    expected_provisions = sum(markers[s]['provision_count'] for s in source_ids & markers.keys())
    expected_assertions = sum(markers[s]['unique_assertion_count']
                              if markers[s]['unique_assertion_count'] is not None
                              else markers[s]['assertion_count']
                              for s in source_ids & markers.keys())
    unreconciled = sum(markers[s]['unique_assertion_count'] is None
                       for s in source_ids & markers.keys())
    return dict(source_snapshots=len(source_ids), completed_snapshots=len(source_ids & markers.keys()),
                missing_snapshots=len(missing), missing_sample=missing[:10],
                unexpected_markers=len(extra), unexpected_sample=extra[:10],
                source_articles=sum(markers[s]['article_count'] for s in source_ids & markers.keys()),
                expected_provisions=expected_provisions, actual_provisions=counts['TaxProvision'],
                expected_assertions=expected_assertions, actual_assertions=counts['KnowledgeAssertion'],
                unreconciled_snapshots=unreconciled,
                review_status=reviews,
                complete=not missing and not extra and not unreconciled
                    and expected_provisions == counts['TaxProvision']
                    and expected_assertions == counts['KnowledgeAssertion'])


async def validate_all_sources(*, limit=None, progress=None):
    """Re-read every selected source snapshot; report XML/body or hash drift."""
    if limit is not None and limit < 1:
        raise ValueError('Limit must be positive')
    pool = await get_pool()
    rows = await pool.fetch('''SELECT v.id FROM law_history.versions v
        WHERE v.fetch_status='complete' ORDER BY v.id''')
    selected = rows[:limit] if limit is not None else rows
    report = dict(total=len(rows), checked=0, empty_article_snapshots=0, articles=0, provisions=0,
                  duplicate_provision_keys=0, conflicting_provision_keys=0,
                  duplicate_assertion_keys=0, ambiguous_versions=0,
                  hash_or_parse_errors=0, xml_body_mismatches=0, examples=[])
    for row in selected:
        try:
            version, articles = await source_version(row['id'], allow_empty=True)
            if not articles:
                report['empty_article_snapshots'] += 1
            provisions, _, _, assertions = build(version, articles)
            first_quotes = {}
            ambiguous = False
            for provision in provisions:
                reference = provision['reference']
                if provision['occurrence']:
                    ambiguous = True
                    report['duplicate_provision_keys'] += 1
                    if first_quotes[reference] != provision['quote']:
                        report['conflicting_provision_keys'] += 1
                    if len(report['examples']) < 10:
                        report['examples'].append(dict(version_id=row['id'],
                            reference=provision['reference'], issue='duplicate_provision'))
                else:
                    first_quotes[reference] = provision['quote']
            if ambiguous:
                report['ambiguous_versions'] += 1
            report['duplicate_assertion_keys'] += len(assertions) - len({a['key'] for a in assertions})
            # An historical snapshot can contain an amendment directive and the
            # consolidated article under the same number. Compare each provision
            # with the exact source row that produced it, not the last row with
            # that article number.
            bodies = {article['id']: article['body'] for article in articles}
            for provision in provisions:
                if provision['quote'] not in bodies.get(provision['source_article_id'], ''):
                    report['xml_body_mismatches'] += 1
                    if len(report['examples']) < 10:
                        report['examples'].append(dict(version_id=row['id'],
                                                       reference=provision['reference'], issue='xml_body'))
            report['articles'] += len(articles)
            report['provisions'] += len(provisions)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            report['hash_or_parse_errors'] += 1
            if len(report['examples']) < 10:
                report['examples'].append(dict(version_id=row['id'], issue='hash_or_parse'))
        report['checked'] += 1
        if progress is not None:
            progress(report)
    return report


async def candidates(version_id, article_no=None):
    version, _ = await source_version(version_id, article_no)
    async with connect() as driver:
        rows, _, _ = await driver.execute_query(Query('''MATCH (p:TaxProvision)-[:SUBJECT_OF]->
            (a:KnowledgeAssertion)-[:OBJECT]->(target)
            WHERE p.snapshot_id=$snapshot AND a.review_status='candidate'
              AND ($article IS NULL OR p.article_no=$article)
            RETURN a.key AS key,a.kind AS kind,p.reference AS source,
                   labels(target) AS target_labels,properties(target) AS target,
                   a.quote AS quote ORDER BY source,kind,key LIMIT 200''', timeout=3),
            snapshot=version['snapshot_id'], article=article_no,
            database_=config.NEO4J_DATABASE, routing_='r')
    return [dict(row) for row in rows]


async def review(assertion_key, *, approve, reviewer):
    """Review an exact source claim; source drift prevents approval."""
    if not reviewer.strip():
        raise ValueError('Reviewer identity required')
    async with connect() as driver:
        rows, _, _ = await driver.execute_query(Query('''MATCH (p:TaxProvision)-[:SUBJECT_OF]->
            (a:KnowledgeAssertion {key:$key})-[:OBJECT]->(target)
            RETURN properties(p) AS provision,properties(a) AS assertion,
                   labels(target) AS target_labels,properties(target) AS target''', timeout=2),
            key=assertion_key, database_=config.NEO4J_DATABASE, routing_='r')
        if len(rows) != 1:
            raise ValueError('Assertion not found or ambiguous')
        record = dict(rows[0])
        provision, assertion = record['provision'], record['assertion']
        pool = await get_pool()
        sources = await pool.fetch('''SELECT body,structure,content_hash FROM law_history.articles
            WHERE snapshot_id=$1 AND article_number=$2 AND article_branch=$3 AND unit_kind='조문' ''',
            provision['snapshot_id'], provision['article_number'], provision['article_branch'])
        if len(sources) != 1:
            raise ValueError('Source article is missing or ambiguous')
        source = sources[0]
        if (not source or source['content_hash'] != provision['article_hash']
                or sha(source['body']) != source['content_hash']):
            raise ValueError('Source snapshot no longer matches assertion')
        excerpt = article_excerpt(source['structure'], source['body'], parse_law_reference(provision['reference']))
        if (assertion['quote'] not in excerpt or assertion['source_hash'] != provision['source_hash']
                or provision['quote'] not in excerpt or provision['quote'] not in source['body']):
            raise ValueError('Source quote no longer matches assertion')
        if assertion['kind'] == 'DEFINES':
            if 'TaxConcept' not in record['target_labels'] or not any(
                    m['term'].strip() == record['target']['name'] for m in _DEFINITION.finditer(provision['quote'])):
                raise ValueError('Definition term does not match source')
        elif assertion['kind'] == 'CITES':
            if 'TaxReference' not in record['target_labels'] or not any(
                    r['evidence'] == assertion['quote'] and r['reference'] == record['target']['reference']
                    and r['law_name'] == record['target']['law_name']
                    for r in extract_relations(provision['quote'])):
                raise ValueError('Citation does not match source')
        else:
            raise ValueError('Unsupported assertion kind')
        await driver.execute_query('''MATCH (a:KnowledgeAssertion {key:$key})
            SET a.review_status=$status,a.reviewed_by=$reviewer,a.reviewed_at=datetime()
            RETURN a.key AS key''', key=assertion_key, status='reviewed' if approve else 'rejected',
            reviewer=reviewer, database_=config.NEO4J_DATABASE)
    return dict(key=assertion_key, status='reviewed' if approve else 'rejected')


def _matched_terms(query, terms):
    """Prefer longest matching term, so 비거주자 does not also match 거주자."""
    found = []
    for term in sorted(set(terms), key=len, reverse=True):
        if re.search(r'(?<![가-힣])' + re.escape(term), query) and not any(
                term in longer for longer in found):
            found.append(term)
    return set(found)


async def reviewed_definitions(version, query):
    """Return only reviewed definitions of this exact immutable snapshot."""
    async with connect() as driver:
        rows, _, _ = await driver.execute_query(Query('''MATCH (s:HistorySnapshot {id:$snapshot})
            -[:HAS_KG_PROVISION]->(p:TaxProvision)-[:SUBJECT_OF]->
            (a:KnowledgeAssertion {kind:'DEFINES',review_status:'reviewed'})-[:OBJECT]->(c:TaxConcept)
            WHERE p.version_id=$version AND $query CONTAINS c.name
            RETURN properties(p) AS provision,properties(a) AS assertion,c.name AS term
            ORDER BY size(c.name) DESC LIMIT 100''', timeout=2),
            snapshot=version['snapshot_id'], version=version['id'], query=query,
            database_=config.NEO4J_DATABASE, routing_='r')
    candidates = [dict(row) for row in rows]
    terms = _matched_terms(query, [row['term'] for row in candidates])
    pool = await get_pool()
    output = []
    for row in candidates:
        if row['term'] not in terms:
            continue
        p, a = row['provision'], row['assertion']
        sources = await pool.fetch('''SELECT body,structure,content_hash FROM law_history.articles
            WHERE snapshot_id=$1 AND article_number=$2 AND article_branch=$3 AND unit_kind='조문' ''',
            version['snapshot_id'], p['article_number'], p['article_branch'])
        if len(sources) != 1:
            continue
        source = sources[0]
        if (not source or source['content_hash'] != p['article_hash']
                or sha(source['body']) != source['content_hash'] or p['quote'] not in source['body']):
            continue
        try:
            content = article_excerpt(source['structure'], source['body'], parse_law_reference(p['reference']))
        except (ValueError, KeyError):
            continue
        if a['quote'] not in content or sha(p['quote']) != a['source_hash']:
            continue
        output.append(dict(content=content, article_no=p['article_no'], requested_reference=p['reference'],
            law_name=version['law_name'], version_id=version['id'], snapshot_id=version['snapshot_id'],
            text_key='a:' + p['article_hash'], effective_date=str(version['effective_date']),
            promulgation_date=str(version['promulgation_date']), source_url=version['source_url'],
            kind='article', graph_evidence=f'검수된 정의 관계: {row["term"]}',
            knowledge_assertion_id=a['key']))
    return output


async def reviewed_citations(version, article_numbers):
    """Return reviewed citation claims; the target version is resolved by the caller."""
    async with connect() as driver:
        rows, _, _ = await driver.execute_query(Query('''MATCH (s:HistorySnapshot {id:$snapshot})
            -[:HAS_KG_PROVISION]->(p:TaxProvision)-[:SUBJECT_OF]->
            (a:KnowledgeAssertion {kind:'CITES',review_status:'reviewed'})-[:OBJECT]->(t:TaxReference)
            WHERE p.version_id=$version AND p.article_no IN $articles
            RETURN properties(p) AS provision,properties(a) AS assertion,
                   t.law_name AS target_law,t.reference AS target_reference
            ORDER BY p.reference,a.key''', timeout=2),
            snapshot=version['snapshot_id'], version=version['id'], articles=list(article_numbers),
            database_=config.NEO4J_DATABASE, routing_='r')
    return [dict(row) for row in rows]
