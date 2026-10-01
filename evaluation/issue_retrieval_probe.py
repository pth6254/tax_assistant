"""Read-only issue-search probe over the existing draft retrieval examples.

Records exact required-article recall for the application issue search path.
The draft labels are diagnostics, not approved legal answers.
"""
import asyncio
import json
from pathlib import Path
import sys
import time
import statistics
import os

# Local A/B diagnostics must not consume the operator's tracing quota. Opt in
# explicitly when publishing these public draft examples is desired.
if '--trace' not in sys.argv:
    os.environ['LANGSMITH_TRACING'] = 'false'
    os.environ['LANGCHAIN_TRACING_V2'] = 'false'

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path.cwd()))

import config
from evaluation.adapters import close_live_clients
from app.services.search import hybrid_search_service as search_service
from app.services.search.bm25_search_service import warm_bm25_index, close_bm25_index


CASES = {'inc-01', 'inc-02', 'inc-03', 'cg-02', 'inh-04', 'gift-01',
         'vat-02', 'vat-04', 'corp-01', 'corp-02', 'basic-01', 'basic-04'}


async def main(output):
    config.SEARCH_LEXICAL_BACKEND = 'trigram' if '--trigram' in sys.argv else 'bm25'
    if '--no-algorithms' in sys.argv:
        config.SEARCH_FUZZY_ENABLED = False
        config.SEARCH_REGEX_ENABLED = False
        config.SEARCH_MMR_ENABLED = False
    if config.SEARCH_LEXICAL_BACKEND == 'bm25':
        await warm_bm25_index()
    if '--instruction' in sys.argv:
        config.SEARCH_QUERY_INSTRUCTION_ENABLED = True
    search_service.ISSUE_TITLE_RESCUE = '--no-title-rescue' not in sys.argv
    dataset = json.loads(Path('evaluation/datasets/retrieval.json').read_text(encoding='utf-8'))
    records = []
    try:
        for case in dataset['cases']:
            if case['id'] not in CASES and '--all' not in sys.argv:
                continue
            query = case['input']['query']
            required = [(j['evidence']['law'], j['evidence']['reference'])
                        for j in case['judgments'] if j['label'] == 'required']
            start = time.perf_counter()
            diagnostic = {}
            try:
                hits = await search_service.hybrid_search([query, query + ' 적용 요건 예외'],
                                           case['input'].get('law_filter', 'ALL'),
                                           original_query=query, official_only=True,
                                           issue_mode=True, diagnostics=diagnostic)
                result = [(r.law_name, r.article_no) for r in hits]
                ranks = [next((i + 1 for i, key in enumerate(result) if key == wanted), None)
                         for wanted in required]
                negatives = [(j['evidence']['law'], j['evidence']['reference'])
                             for j in case['judgments'] if j['label'] == 'hard_negative']
                item = {'id': case['id'], 'ranks': ranks, 'returned': len(hits),
                        'hard_negative_hits': sum(key in result for key in negatives),
                        'seconds': round(time.perf_counter() - start, 3),
                        'candidates': diagnostic}
            except Exception as error:
                item = {'id': case['id'], 'error': type(error).__name__,
                        'ranks': [None] * len(required),
                        'seconds': round(time.perf_counter() - start, 3)}
            records.append(item)
            print(json.dumps({key: value for key, value in item.items() if key != 'candidates'},
                             ensure_ascii=False), flush=True)
        checked = [r for r in records if r.get('ranks')]
        latencies = sorted(row['seconds'] for row in records)
        output_data = {'dataset': dataset['name'], 'status': 'draft_diagnostic',
                       'lexical_backend': config.SEARCH_LEXICAL_BACKEND,
                       'algorithms': {'fuzzy': config.SEARCH_FUZZY_ENABLED,
                                      'regex': config.SEARCH_REGEX_ENABLED,
                                      'mmr': config.SEARCH_MMR_ENABLED},
                       'fusion': {'k': config.SEARCH_RRF_K if config.SEARCH_LEXICAL_BACKEND == 'bm25' else 60,
                                  'lexical_weight': config.SEARCH_LEXICAL_WEIGHT if config.SEARCH_LEXICAL_BACKEND == 'bm25' else 1},
                       'p50_seconds': statistics.median(latencies) if latencies else None,
                       'p95_seconds': latencies[min(len(latencies)-1, int(len(latencies)*0.95))] if latencies else None,
                       'cases': records, 'recall': sum(all(rank is not None for rank in row['ranks'])
                                                      for row in checked) / len(checked) if checked else None,
                       'mrr': sum(1 / min(rank for rank in row['ranks'] if rank is not None)
                                  if any(rank is not None for rank in row['ranks']) else 0
                                  for row in checked) / len(checked) if checked else None,
                       'hard_negative_hits': sum(row.get('hard_negative_hits', 0) for row in records),
                       'errors': sum('error' in row for row in records)}
        output_data['fallback_cases'] = sum(row.get('candidates', {}).get('lexical_backend') == 'trigram'
                                           for row in records) if config.SEARCH_LEXICAL_BACKEND == 'bm25' else 0
        Path(output).write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        await close_bm25_index()
        await close_live_clients()


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1]))
