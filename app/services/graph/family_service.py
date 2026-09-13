"""Explicit law families verified against official purpose clauses.

Family topology is not article delegation or a legal as-of-date determination.
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

import config
from app.services.graph.store import connect
from app.services.law.api_service import search_law, get_law_detail
from app.services.law.parser_service import parse_articles


def family_evidence(source, target, base_name):
    text = target['purpose']
    direct = f'「{source["law_name"]}」' in text
    relative = (source['law_name'] == base_name + ' 시행령' and
                re.search(re.escape(f'「{base_name}」') + r'\s*및\s*(?:같은\s*법|동법)\s*시행령', text))
    if (direct or relative) and '위임된 사항' in text and '목적' in text:
        return text, 'purpose_verified'
    alias = '영' if source['law_name'].endswith(' 시행령') else '법'
    pattern = re.escape(f'「{source["law_name"]}」') + r'\s*\(이하\s*["“]' + alias + r'["”]이라\s*한다\)'
    for text in target.get('alias_evidence', []):
        if re.search(pattern, text):
            return text, 'alias_verified'
    raise ValueError('Official purpose/alias does not confirm family')


def group_stored_families(names):
    names = set(names)
    bases = sorted(n for n in names if not n.endswith((' 시행령', ' 시행규칙')))
    complete = [n for n in bases if n + ' 시행령' in names and n + ' 시행규칙' in names]
    covered = {n + suffix for n in complete for suffix in ('', ' 시행령', ' 시행규칙')}
    return complete, sorted(names - covered)


async def stored_families():
    async with connect() as driver:
        rows, _, _ = await driver.execute_query(
            'MATCH (n:TaxArticle) RETURN DISTINCT n.law_name AS name',
            database_=config.NEO4J_DATABASE, routing_='r')
    return group_stored_families(r['name'] for r in rows)


def verify_family(members):
    if len(members) != 3 or len({m['law_id'] for m in members}) != 3:
        raise ValueError('Three distinct official law IDs required')
    base, decree, rule = members
    if (decree['law_name'] != base['law_name'] + ' 시행령'
            or rule['law_name'] != base['law_name'] + ' 시행규칙'):
        raise ValueError('Unexpected family names')
    links = []
    for source, target, relation in (
        (base, decree, 'HAS_ENFORCEMENT_DECREE'),
        (base, rule, 'HAS_ENFORCEMENT_RULE'),
        (decree, rule, 'HAS_IMPLEMENTING_RULE'),
    ):
        evidence, status = family_evidence(source, target, base['law_name'])
        links.append(dict(source=source['law_id'], target=target['law_id'],
                          relation=relation, evidence=evidence, status=status,
                          source_url=target['source_url'], evidence_mst=target['mst'],
                          published_on=target['published_on'], effective_on=target['effective_on']))
    return links


async def prepare_family(base_name):
    members = []
    for suffix in ('', ' 시행령', ' 시행규칙'):
        name = base_name + suffix
        matches = await search_law(name, exact=True, display=20)
        if not matches:
            raise ValueError('Official exact-name match missing')
        summary = matches[0]
        detail = await get_law_detail(summary.mst)
        root = ET.fromstring(detail['raw_xml'])
        basic = root.find('기본정보')
        if basic is None:
            raise ValueError('Official metadata missing')
        law_id = basic.findtext('법령ID', '').strip()
        if not re.fullmatch(r'\d+', law_id):
            raise ValueError('Invalid official law ID')
        articles = parse_articles(detail['raw_xml'])
        purpose = next((a for a in articles if a.article_no == '제1조'), None)
        if purpose is None or purpose.law_name != name:
            raise ValueError('Purpose/name verification failed')
        members.append(dict(law_id=law_id, law_name=name, law_type=purpose.law_type,
                            mst=summary.mst, purpose=purpose.article_text,
                            alias_evidence=[a.article_text for a in articles
                                            if '이하' in a.article_text and '이라 한다' in a.article_text],
                            published_on=purpose.amendment_date, effective_on=purpose.effective_date,
                            source_url=f'https://www.law.go.kr/lsInfoP.do?lsiSeq={summary.mst}'))
    return members, verify_family(members)


async def save_family(members, links):
    if links != verify_family(members):
        raise ValueError('Unverified family links')
    now = datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    async with connect() as driver:
        await driver.execute_query('CREATE CONSTRAINT tax_law_id IF NOT EXISTS '
                                   'FOR (n:TaxLaw) REQUIRE n.law_id IS UNIQUE',
                                   database_=config.NEO4J_DATABASE)
        async def write(tx):
            # Missing stored article families abort before writes.
            result = await tx.run('''
                UNWIND $names AS name
                OPTIONAL MATCH (a:TaxArticle {law_name:name})
                RETURN name, count(a) AS articles
            ''', names=[m['law_name'] for m in members])
            if any(r['articles'] == 0 for r in await result.data()):
                raise ValueError('Stored article family missing')
            result = await tx.run('''
                UNWIND $members AS row
                MERGE (l:TaxLaw {law_id:row.law_id})
                SET l.law_name=row.law_name, l.law_type=row.law_type
                WITH l, row MATCH (a:TaxArticle {law_name:row.law_name})
                MERGE (l)-[:HAS_ARTICLE]->(a)
            ''', members=members)
            await result.consume()
            for link in links:
                # Relationship type comes exclusively from verified fixed set.
                result = await tx.run('''
                    MATCH (a:TaxLaw {law_id:$source}), (b:TaxLaw {law_id:$target})
                    MERGE (a)-[r:''' + link['relation'] + ''' {evidence_mst:$mst}]->(b)
                    ON CREATE SET r.recorded_at=$now
                    SET r.evidence=$evidence, r.source_url=$url,
                        r.published_on=$published, r.effective_on=$effective,
                        r.status=$status, r.basis=$basis,
                        r.legal_applicability_verified=false
                ''', source=link['source'], target=link['target'], mst=link['evidence_mst'],
                    evidence=link['evidence'], url=link['source_url'], now=now,
                    status=link['status'], basis='official_purpose_clause' if link['status']=='purpose_verified' else 'official_alias_definition',
                    published=link['published_on'], effective=link['effective_on'])
                await result.consume()
        async with driver.session(database=config.NEO4J_DATABASE) as session:
            await session.execute_write(write)
