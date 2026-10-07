"""Read-only official XML collection, independent of BM25/vector/graph retrieval."""
from datetime import date
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse

from evaluation.card_schema import Source, SourcePackage, TAXES, TYPES
from app.services.law.history_parser import parse, sha
from app.services.law.parser_service import parse_articles

# These are sampling anchors, not legal conclusions or required-evidence labels.
CATALOG = {
    'corporate': ('법인세법', ('제19조', '제25조', '제27조', '제67조'), r'손비|기업업무추진비|소득처분|업무와 관련|복리후생'),
    'vat': ('부가가치세법', ('제26조', '제28조', '제38조', '제39조', '제48조', '제49조'), r'면세|매입세액|확정신고|예정신고'),
    'income': ('소득세법', ('제14조', '제16조', '제17조', '제50조', '제55조', '제62조'), r'기본공제|금융소득|이자소득|배당소득'),
    'capital_gains': ('소득세법', ('제94조', '제95조', '제97조', '제98조', '제100조', '제104조'), r'양도소득|취득시기|양도차익'),
    'inheritance': ('상속세 및 증여세법', ('제13조', '제18조', '제19조', '제20조', '제21조', '제60조', '제67조'), r'상속공제|상속세과세표준|평가의 원칙'),
    'gift': ('상속세 및 증여세법', ('제47조', '제53조', '제55조', '제56조', '제60조', '제68조'), r'증여재산공제|증여세과세표준|증여세 과세표준'),
}
SECONDARY = {'corporate': 'vat', 'vat': 'income', 'income': 'vat',
             'capital_gains': 'gift', 'inheritance': 'gift', 'gift': 'capital_gains'}


def validate_source_url(source):
    url = urlparse(source.source_url)
    args = parse_qs(url.query)
    if (url.scheme != 'https' or url.hostname not in {'www.law.go.kr', 'law.go.kr'}
            or url.username or url.password or url.port or url.fragment
            or url.path != '/LSW/lsInfoP.do'
            or args.get('lsiSeq') != [source.mst]
            or args.get('efYd') != [source.effective_from.strftime('%Y%m%d')]
            or any(key.casefold() in {'oc', 'key', 'api_key'} for key in args)):
        raise ValueError('untrusted_source_url')
    if (source.version != f'{source.mst}:{source.effective_from}'
            or source.id != f'S{source.snapshot_id}:{source.reference}'):
        raise ValueError('source_version_identity')


def validate_snapshot(source, root, cache=None):
    validate_source_url(source)
    base = Path(root).resolve()
    path = (base / source.snapshot_file).resolve()
    if not path.is_relative_to(base):
        raise ValueError('snapshot_path_escape')
    xml = path.read_bytes().decode('utf-8')
    if sha(xml) != source.snapshot_hash or sha(source.text) != source.text_hash:
        raise ValueError('source_hash_mismatch')
    key = (str(path), source.snapshot_hash, source.law_id, source.effective_from, source.promulgation_date)
    cached = (cache or {}).get(key)
    if cached is None:
        parsed = parse(xml, law_id=source.law_id, effective_date=source.effective_from,
                       promulgation_date=source.promulgation_date)
        articles = parse_articles(xml)
        if cache is not None:
            cache[key] = (parsed, articles)
    else:
        parsed, articles = cached
    if parsed['name'] != source.law:
        raise ValueError('snapshot_law_mismatch')
    if source.reference.startswith('부칙:'):
        texts = [s['body'] for s in parsed['supplements']]
    else:
        texts = [a.article_text for a in articles
                 if a.law_name == source.law and a.article_no == source.reference]
    if source.text not in texts:
        raise ValueError('source_not_in_snapshot')


async def collect_packages(root, *, as_of, taxes=TAXES, case_types=TYPES):
    from app.database import get_pool
    root = Path(root)
    (root / 'snapshots').mkdir(parents=True, exist_ok=True)
    pool = await get_pool()
    cache = {}

    async def read_law(law, cutoff):
        key = (law, cutoff)
        if key in cache:
            return cache[key]
        # Select version BEFORE checking fetch status. Never silently use an older
        # complete snapshot when the newest known applicable one is uncollected.
        row = await pool.fetchrow('''SELECT v.*, s.id AS snapshot_id, s.raw_xml,
            s.content_hash AS snapshot_hash, s.source_url AS snapshot_url
            FROM law_history.versions v
            LEFT JOIN LATERAL (SELECT * FROM law_history.snapshots s
                WHERE s.version_id=v.id ORDER BY s.collected_at DESC,s.id DESC LIMIT 1) s ON TRUE
            WHERE v.law_name=$1 AND v.effective_date<=$2
            ORDER BY v.effective_date DESC,v.promulgation_date DESC,v.id DESC LIMIT 1''', law, cutoff)
        if not row or row['fetch_status'] != 'complete' or not row['raw_xml']:
            cache[key] = None
            return None
        if sha(row['raw_xml']) != row['snapshot_hash']:
            raise ValueError('archive_snapshot_hash')
        parsed = parse(row['raw_xml'], law_id=row['law_id'], effective_date=row['effective_date'],
                       promulgation_date=row['promulgation_date'])
        if parsed['name'] != law:
            raise ValueError('archive_law_identity')
        relative = f'snapshots/{row["snapshot_id"]}.xml'
        path = root / relative
        if path.exists():
            if sha(path.read_bytes().decode('utf-8')) != row['snapshot_hash']:
                raise ValueError('existing_snapshot_changed')
        else:
            path.write_bytes(row['raw_xml'].encode('utf-8'))
        value = (dict(row), parse_articles(row['raw_xml']), parsed, relative)
        cache[key] = value
        return value

    async def provisions(tax, cutoff, historical=False, case_type='general'):
        law, anchors, titles = CATALOG[tax]
        sources, unresolved = [], []
        for family_law in (law, law + ' 시행령', law + ' 시행규칙'):
            archive = await read_law(family_law, cutoff)
            if not archive:
                unresolved.append('missing_snapshot:' + family_law)
                continue
            row, articles, parsed, relative = archive
            chosen = [a for a in articles if a.law_name == family_law
                      and ((family_law == law and a.article_no in anchors)
                           or (family_law != law and re.search(titles, a.article_title)))]
            # Full provisions only. Do not clip conditions to fit an input budget.
            if family_law == law and case_type in {'exception', 'missing_information'}:
                chosen = chosen[-4:]
            else:
                chosen = chosen[:4 if family_law == law else 2]
            common = dict(law=family_law, version=f'{row["mst"]}:{row["effective_date"]}',
                effective_from=row['effective_date'], source_url=row['snapshot_url'],
                snapshot_id=row['snapshot_id'], snapshot_hash=row['snapshot_hash'],
                snapshot_file=relative, law_id=row['law_id'], mst=row['mst'],
                promulgation_date=row['promulgation_date'])
            for article in chosen:
                if not article.article_text:
                    continue
                source = Source(id=f'S{row["snapshot_id"]}:{article.article_no}',
                    reference=article.article_no, text=article.article_text,
                    text_hash=sha(article.article_text), **common)
                validate_source_url(source)
                sources.append(source)
            # Recent supplement units are retained whole, with an explicit limit.
            # A temporal card cannot assert completeness of all historical clauses.
            supplements = parsed['supplements']
            chosen_supplements = supplements[-1:]
            for supplement in chosen_supplements:
                if len(supplement['body']) > 10000:
                    unresolved.append('supplement_budget:' + family_law)
                    continue
                ref = f'부칙:{supplement["source_order"]}'
                sources.append(Source(id=f'S{row["snapshot_id"]}:{ref}', reference=ref,
                    text=supplement['body'], text_hash=sha(supplement['body']), **common))
            if historical and len(supplements) > 1:
                unresolved.append('transition_scope_requires_review:' + family_law)
        return sources, unresolved

    packages, failures = [], []
    for tax in taxes:
        for case_type in case_types:
            identity = f'{tax}-{case_type}'
            try:
                sources, unresolved = await provisions(tax, as_of, case_type=case_type)
                if case_type == 'compound':
                    other, gaps = await provisions(SECONDARY[tax], as_of)
                    sources.extend(other)
                    unresolved.extend(gaps)
                if case_type == 'temporal':
                    law = CATALOG[tax][0]
                    latest = await read_law(law, as_of)
                    if latest:
                        from datetime import timedelta
                        cutoff = latest[0]['effective_date'] - timedelta(days=1)
                        older, gaps = await provisions(tax, cutoff, historical=True)
                        sources.extend(older)
                        unresolved.extend(gaps)
                    else:
                        unresolved.append('historical_snapshot_unavailable')
                sources = list({s.id: s for s in sources}.values())
                if not sources:
                    raise ValueError('no_official_sources')
                packages.append(SourcePackage(id=identity, tax=tax, case_type=case_type,
                    as_of=as_of, sources=sources, unresolved=sorted(set(unresolved))))
            except Exception as exc:
                failures.append({'package_id': identity, 'phase': 'source_collection',
                                 'status': 'error', 'error_type': type(exc).__name__})
    return packages, failures
