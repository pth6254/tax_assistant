"""Build a bounded current-law graph; never modify PostgreSQL or embeddings."""
import hashlib
import json
import re
from datetime import date

from app.database import get_pool
from app.services.law.relation_extractor import extract_relations, alias_definitions
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


def build_aliases(rows):
    """Unique global original-text definition + exact stored family identity.

    Any second/scoped definition disables the alias rather than guessing scope.
    """
    grouped = {}
    for row in rows:
        grouped.setdefault(row['law_name'], []).append(row)
    result = {}
    for name, articles in grouped.items():
        base = re.sub(r' 시행(?:령|규칙)$', '', name)
        expected = {'법': base, '영': base + ' 시행령'}
        safe, proofs = {}, {}
        definitions = [(r, *d) for r in articles for d in alias_definitions(r['article_text'])]
        for alias, target in expected.items():
            matches = [d for d in definitions if d[1] == alias]
            mentions = sum(len(re.findall(r'이하[^\n)]{0,80}["“「]' + alias + r'["”」]', r['article_text'])) for r in articles)
            if len(matches) != 1 or mentions != 1 or target not in grouped or name == target:
                continue
            definition, _, defined_name, offset, evidence = matches[0]
            if defined_name != target:
                continue
            safe[alias] = target
            proofs[alias] = {'key': article_key(definition), 'article_no': definition['article_no'],
                             'offset': offset, 'evidence': evidence}
        if safe:
            result[name] = (safe, proofs)
    return result


def extract_row_relations(row, aliases):
    """Shared by index and audit so scope exclusions cannot drift."""
    alias_map, proofs = aliases.get(row['law_name'], ({}, {}))
    for candidate in extract_relations(row['article_text'], alias_map):
        proof = proofs.get(candidate['alias'], {})
        if proof:
            current_ref = parse_law_reference(row['article_no'])
            definition_ref = parse_law_reference(proof['article_no'])
            if ((current_ref.article, current_ref.article_branch or 0) <
                    (definition_ref.article, definition_ref.article_branch or 0)):
                continue
            if row['article_no'] == proof['article_no'] and candidate['offset'] < proof['offset']:
                continue
        yield candidate, proof


def build_graph(rows):
    rows = [row for row in rows if effective_now(row)]
    aliases = build_aliases(rows)
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
        for candidate, proof in extract_row_relations(row, aliases):
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
                          'reference': candidate['reference'], 'evidence': candidate['evidence'],
                          'alias_definition_key': proof.get('key', ''),
                          'alias_definition_article': proof.get('article_no', ''),
                          'alias_definition_law': row['law_name'] if candidate['alias'] else ''})
    return nodes, edges, unresolved
