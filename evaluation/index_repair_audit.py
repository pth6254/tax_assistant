"""Read-only verification of actual vector input lineage after a repair."""
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import get_pool, close_pool
from app.services.evidence import digest
from app.services.law.clause_splitter import build_clause_embed_text, should_split, split_into_clauses
from app.services.law.index_repair import as_article
from app.services.law.ingestion_service import _build_embed_text
from app.services.law.index_metadata import validate_vectors


async def main():
    pool = await get_pool()
    errors, count, clauses_count = [], 0, 0
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM law_articles WHERE index_metadata ? 'repair_run_id' ORDER BY id")
            for row in rows:
                count += 1
                metadata = row['index_metadata']
                text = _build_embed_text(as_article(row), row['tax_type'])
                if (digest(row['article_text']) != row['content_hash']
                        or metadata['source_hash'] != row['content_hash']
                        or metadata['input_hash'] != digest(text)):
                    errors.append([row['id'], 'article_lineage'])
                expected = {c.label: c.text for c in split_into_clauses(row['article_text'])} if should_split(row['article_text']) else {}
                clauses = await conn.fetch('SELECT * FROM law_article_clauses WHERE article_id=$1', row['id'])
                if {c['clause_label']: c['clause_text'] for c in clauses} != expected:
                    errors.append([row['id'], 'clause_structure'])
                for unit, content in [(row, text)] + [(c, build_clause_embed_text(row['law_name'], row['article_no'],
                        row['article_title'], row['article_text'], c['clause_text'])) for c in clauses]:
                    meta = unit['index_metadata']
                    if meta['source_hash'] != row['content_hash'] or meta['input_hash'] != digest(content):
                        errors.append([row['id'], 'clause_lineage'])
                    for col, version in (('embedding', 'v1'), ('embedding_v2', 'v2')):
                        if unit[col] is not None:
                            validate_vectors([unit[col]], 1)
                            if version not in meta or meta[version]['input_hash'] != digest(content):
                                errors.append([row['id'], 'untracked_vector'])
                clauses_count += len(clauses)
        output = {'articles': count, 'clauses': clauses_count, 'errors': errors}
        print(json.dumps(output), flush=True)
        if errors:
            raise SystemExit(1)
    finally:
        await close_pool()


if __name__ == '__main__':
    asyncio.run(main())
