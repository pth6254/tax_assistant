"""Read-only current-law search index audit; prints counts, never source bodies."""
import asyncio
import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path.cwd()))

import config
from app.database import close_pool, get_pool
from app.services.evidence import has_missing_items
from app.services.law.clause_splitter import should_split
from app.services.law.source_recovery import recover_article

TAX_LAWS = {'소득세법', '법인세법', '부가가치세법', '상속세 및 증여세법', '국세기본법'}


async def main():
    col = 'embedding_v2' if config.EMBEDDING_VERSION == 'v2' else 'embedding'
    pool = await get_pool()
    try:
        article = await pool.fetchrow(f'''SELECT COUNT(*) AS total,
            COUNT(*) FILTER (WHERE {col} IS NULL) AS missing_vectors
            FROM law_articles WHERE is_current = TRUE AND law_type <> '법령해석례' ''')
        clause = await pool.fetchrow(f'''SELECT COUNT(*) AS total,
            COUNT(*) FILTER (WHERE c.{col} IS NULL) AS missing_vectors
            FROM law_article_clauses c JOIN law_articles a ON a.id=c.article_id
            WHERE a.is_current = TRUE''')
        long_rows = await pool.fetch('''SELECT a.id, a.article_text, COUNT(c.id) AS clauses
            FROM law_articles a LEFT JOIN law_article_clauses c ON c.article_id=a.id
            WHERE a.is_current=TRUE AND a.law_type <> '법령해석례'
              AND length(a.article_text)>=300
            GROUP BY a.id ORDER BY a.id''')
        incomplete_rows = await pool.fetch('''SELECT id, content_hash, law_name, article_no, article_text,
            article_title, effective_date, amendment_date, source_url
            FROM law_articles WHERE is_current=TRUE AND article_text LIKE '%다음 각 호%'
            ORDER BY id''')
        incomplete = [r for r in incomplete_rows if has_missing_items(r['article_text'])]
        tax_incomplete = [r for r in incomplete if r['law_name'] in TAX_LAWS]
        recovered, manifest = [], []
        recovery_scope = tax_incomplete if '--all-core-recovery' in sys.argv else tax_incomplete[:40]
        async with pool.acquire() as conn:
            for row in recovery_scope:
                restored = await recover_article(row, conn)
                if len(restored['article_text']) > len(row['article_text']):
                    recovered.append((row['law_name'], row['article_no']))
                    manifest.append({'article_id': row['id'], 'law_name': row['law_name'],
                        'article_no': row['article_no'], 'source_url': row['source_url'],
                        'effective_date': row['effective_date'], 'amendment_date': row['amendment_date'],
                        'old_hash': row['content_hash'], 'restored_hash': restored['content_hash'],
                        'old_chars': len(row['article_text']), 'restored_chars': len(restored['article_text']),
                        'snapshot_source_id': restored['id']})
        if '--manifest' in sys.argv:
            output = Path(sys.argv[sys.argv.index('--manifest') + 1])
            output.write_text(json.dumps({'status': 'read_only_proposal', 'db_writes': 0,
                'requires': ['duplicate row review', 'scoped backup', 'approved retrieval labels',
                             'vector and clause reindex', 'graph hash refresh'],
                'articles': manifest}, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'active_embedding': config.EMBEDDING_VERSION,
            'current_articles': article['total'], 'articles_missing_active_vector': article['missing_vectors'],
            'current_clauses': clause['total'], 'clauses_missing_active_vector': clause['missing_vectors'],
            'long_articles': len(long_rows),
            'split_eligible_without_clauses': sum(r['clauses'] == 0 and should_split(r['article_text'])
                                                  for r in long_rows),
            'incomplete_current_text_candidates': len(incomplete),
            'core_tax_law_incomplete_candidates': len(tax_incomplete),
            'core_tax_law_candidates_by_law': dict(Counter(r['law_name'] for r in tax_incomplete)),
            'core_tax_recovery_checked': len(recovery_scope),
            'recoverable_core_tax_checked': len(recovered),
            'recoverable_core_tax_examples': recovered[:12]}, ensure_ascii=False))
    finally:
        await close_pool()


if __name__ == '__main__':
    asyncio.run(main())
