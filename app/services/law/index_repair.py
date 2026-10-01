"""Prepare and atomically apply bounded, reversible current-law index repairs.

Official immutable same-version XML supplies restored text. No LLM rewrites it.
All network embedding work is finished before a row is locked or changed.
"""
from dataclasses import dataclass

from app.schemas.law import LawArticle
from app.services.evidence import digest, has_missing_items
from app.services.graph.index_service import effective_now
from app.services.law.clause_splitter import build_clause_embed_text, should_split, split_into_clauses
from app.services.law.index_metadata import validate_vectors, vector_metadata
from app.services.law.ingestion_service import _build_embed_text
from app.services.law.source_recovery import recover_article

CORE_LAWS = ('소득세법', '법인세법', '부가가치세법', '상속세 및 증여세법', '국세기본법')
SOURCE_FIELDS = ('id', 'content_hash', 'law_name', 'law_type', 'tax_type', 'article_no',
                 'article_title', 'article_text', 'effective_date', 'amendment_date', 'source_url')
_LOAD = '''SELECT a.*, (SELECT count(*) FROM law_article_clauses c WHERE c.article_id=a.id) AS clause_count
    FROM law_articles a WHERE is_current=TRUE AND law_type <> '법령해석례'
    ORDER BY law_name, article_no, id'''


def as_article(row):
    return LawArticle(**{k: row[k] for k in LawArticle.__dataclass_fields__})


def snapshot_row(row):
    """JSON backup includes both vector columns; no credentials/user documents."""
    return {k: (v.tolist() if hasattr(v, 'tolist') else v.isoformat() if hasattr(v, 'isoformat') else v)
            for k, v in dict(row).items() if k != 'clause_count'}


async def repair_candidates(conn, *, clauses=False, core_only=True):
    rows = await conn.fetch(_LOAD)
    candidates, rejected = [], []
    for record in rows:
        row = dict(record)
        if (core_only and row['law_name'] not in CORE_LAWS) or not effective_now(row):
            continue
        if digest(row['article_text']) != row['content_hash']:
            rejected.append({'article_id': row['id'], 'reason': 'stored_hash_mismatch'})
            continue
        restored = await recover_article(row, conn)
        changed = restored['content_hash'] != row['content_hash']
        missing_clauses = clauses and not row['clause_count'] and should_split(restored['article_text'])
        if not changed and not missing_clauses:
            continue
        if has_missing_items(restored['article_text']):
            rejected.append({'article_id': row['id'], 'reason': 'unrecoverable_original'})
            continue
        # Updating a hash in place must not collide with an existing canonical row.
        conflicts = [r for r in rows if r['id'] != row['id'] and r['law_name'] == row['law_name']
                     and r['article_no'] == row['article_no'] and r['content_hash'] == restored['content_hash']]
        if conflicts:
            rejected.append({'article_id': row['id'], 'reason': 'duplicate_restored_hash',
                             'conflicting_ids': [r['id'] for r in conflicts]})
            continue
        candidates.append({'before': row, 'after': dict(restored) | {'id': row['id']},
                           'snapshot_source_id': str(restored['id']) if changed else '',
                           'kind': 'restore_original' if changed else 'missing_clauses'})
    return candidates, rejected


@dataclass
class PreparedRepair:
    before: dict
    after: dict
    embedding: object
    embedding_v2: object
    metadata: dict
    clauses: list


async def prepare_repair(candidate, embedder, run_id):
    before, after = candidate['before'], candidate['after']
    article = as_article(after)
    inputs = [_build_embed_text(article, after['tax_type'])]
    clauses = split_into_clauses(article.article_text) if should_split(article.article_text) else []
    inputs += [build_clause_embed_text(article.law_name, article.article_no, article.article_title,
                                      article.article_text, c.text) for c in clauses]
    v1, v2 = await embedder(inputs)
    if v1 is None and v2 is None:
        raise ValueError('no_embedding_vectors')
    validate_vectors(v1, len(inputs))
    validate_vectors(v2, len(inputs))
    metadata = [vector_metadata(article.article_text, text, v1=v1 is not None, v2=v2 is not None,
                               source_id=candidate['snapshot_source_id'], run_id=run_id) for text in inputs]
    prepared_clauses = [(before['id'], clause.label, clause.text,
                         v1[i] if v1 is not None else None, v2[i] if v2 is not None else None, metadata[i])
                        for i, clause in enumerate(clauses, 1)]
    return PreparedRepair(before, after, v1[0] if v1 is not None else None,
                          v2[0] if v2 is not None else None, metadata[0], prepared_clauses)


async def apply_repair(conn, prepared, persist_backup):
    """Compare-and-swap body and every derivative in one PostgreSQL transaction."""
    async with conn.transaction():
        current = await conn.fetchrow('SELECT * FROM law_articles WHERE id=$1 FOR UPDATE', prepared.before['id'])
        if (not current or not current['is_current']
                or any(current[k] != prepared.before[k] for k in SOURCE_FIELDS)):
            raise ValueError('repair_parent_changed')
        old_clauses = await conn.fetch('SELECT * FROM law_article_clauses WHERE article_id=$1 ORDER BY id', current['id'])
        backup = {'article': snapshot_row(current), 'clauses': [snapshot_row(c) for c in old_clauses]}
        # Durable backup must succeed before the first mutation.
        persist_backup(backup)
        # NULL the unwritten vector version: a vector of the old text is not reusable.
        await conn.execute('''UPDATE law_articles SET article_title=$2, article_text=$3, content_hash=$4,
            embedding=$5, embedding_v2=$6, index_metadata=$7, updated_at=NOW() WHERE id=$1''', current['id'],
            prepared.after['article_title'], prepared.after['article_text'], prepared.after['content_hash'],
            prepared.embedding, prepared.embedding_v2, prepared.metadata)
        await conn.execute('DELETE FROM law_article_clauses WHERE article_id=$1', current['id'])
        if prepared.clauses:
            await conn.executemany('''INSERT INTO law_article_clauses
                (article_id, clause_label, clause_text, embedding, embedding_v2, index_metadata)
                VALUES ($1,$2,$3,$4,$5,$6)''', prepared.clauses)
    return backup


async def restore_backup(conn, backup, expected_hash, run_id):
    """Never overwrite a subsequent ingestion or another repair while rolling back."""
    old = backup['article']
    async with conn.transaction():
        current = await conn.fetchrow('SELECT * FROM law_articles WHERE id=$1 FOR UPDATE', old['id'])
        if (not current or current['content_hash'] != expected_hash
                or current['index_metadata'].get('repair_run_id') != run_id):
            raise ValueError('rollback_parent_changed')
        await conn.execute('''UPDATE law_articles SET article_title=$2, article_text=$3, content_hash=$4,
            embedding=$5, embedding_v2=$6, index_metadata=$7, updated_at=NOW() WHERE id=$1''', old['id'], old['article_title'],
            old['article_text'], old['content_hash'], old['embedding'], old['embedding_v2'], old['index_metadata'])
        await conn.execute('DELETE FROM law_article_clauses WHERE article_id=$1', old['id'])
        if backup['clauses']:
            await conn.executemany('''INSERT INTO law_article_clauses
                (id, article_id, clause_label, clause_text, embedding, embedding_v2, index_metadata)
                VALUES ($1,$2,$3,$4,$5,$6,$7)''',
                [(c['id'], c['article_id'], c['clause_label'], c['clause_text'], c['embedding'],
                  c['embedding_v2'], c['index_metadata']) for c in backup['clauses']])
