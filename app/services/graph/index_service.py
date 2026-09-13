"""Build a bounded current-law graph; never modify PostgreSQL or embeddings."""
import hashlib
import json
import re
from datetime import date

from app.database import get_pool
from app.services.law.relation_extractor import extract_relations
from app.services.law.reference_parser import parse_law_reference
from app.services.law.structure_parser import resolve_reference_target


def article_key(row) -> str:
    fields = [str(row.get(k) or '') for k in (
        'law_name', 'article_no', 'article_title', 'article_text',
        'effective_date', 'amendment_date')]
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False).encode()).hexdigest()


def law_key(name: str) -> str:
    return re.sub(r'\s+', '', name)


def effective_now(row) -> bool:
    value = str(row.get('effective_date') or '').replace('-', '')
    try:
        effective = date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except (ValueError, TypeError):
        return False
    return len(value) == 8 and effective <= date.today()


async def load_articles(law_name: str | None = None):
    pool = await get_pool()
    return await pool.fetch('''
        SELECT DISTINCT ON (law_name, article_no)
            law_name, article_no, article_title, article_text, law_type, tax_type,
            effective_date, amendment_date, source_url
        FROM law_articles
        WHERE is_current = TRUE AND law_type <> '법령해석례'
          AND ($1::text IS NULL OR law_name = $1)
        ORDER BY law_name, article_no,
                 (article_text LIKE article_no || '%') DESC,
                 length(article_text) DESC, updated_at DESC
    ''', law_name)


def build_graph(rows):
    rows = [row for row in rows if effective_now(row)]
    # Ambiguous names are deliberately not resolved.
    lookup = {}
    for row in rows:
        lookup.setdefault((law_key(row['law_name']), row['article_no']), []).append(row)
    nodes, edges, unresolved = [], [], 0
    for row in rows:
        source = article_key(row)
        nodes.append({key: str(row.get(key) or '') for key in (
            'law_name', 'article_no', 'effective_date', 'amendment_date')}
                     | {'key': source})
        for candidate in extract_relations(row['article_text']):
            targets = lookup.get((law_key(candidate['law_name']), candidate['article_no']), [])
            if len(targets) != 1:
                unresolved += 1
                continue
            target = targets[0]
            ref = parse_law_reference(candidate['reference'])
            resolved = resolve_reference_target(target['article_text'], ref)
            if resolved is not None and not resolved.exists:
                unresolved += 1
                continue
            if article_key(target) == source:
                continue
            edges.append({'source': source, 'target': article_key(target),
                          'reference': candidate['reference'], 'evidence': candidate['evidence']})
    return nodes, edges, unresolved
