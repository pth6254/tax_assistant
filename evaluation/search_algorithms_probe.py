"""Public, read-only A/B diagnostics for typos, exact references and diversity.

No law/chat writes or model Judge calls. Labels are existing draft retrieval
labels, not independently approved tax answers. The same corpus and BM25
snapshot are used for both algorithm configurations.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
import time

os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from evaluation.adapters import close_live_clients
from app.services.search.hybrid_search_service import hybrid_search
from app.services.search.bm25_search_service import close_bm25_index, warm_bm25_index

TYPOS = [('inc-01', '종합소득세', '종합소득새'),
         ('vat-03', '세금계산서', '세금계산소'),
         ('corp-02', '업무용승용차', '업무용승요차'),
         ('gift-01', '증여재산공제', '증여재산공재'),
         ('basic-01', '경정청구', '경정청구구'),
         ('basic-04', '기한후신고', '기한후신구')]


async def main(output):
    dataset = json.loads(Path('evaluation/datasets/retrieval.json').read_text(encoding='utf-8'))
    by_id = {case['id']: case for case in dataset['cases']}
    cases = []
    for case_id, correct, typo in TYPOS:
        original = by_id[case_id]
        expected = [(j['evidence']['law'], j['evidence']['reference']) for j in original['judgments']
                    if j['label'] == 'required']
        for spelling, term in [('correct', correct), ('typo', typo)]:
            cases.append({'id': f'{case_id}-{spelling}',
                          'query': original['input']['query'].replace(correct, term),
                          'required': expected})
    cases += [
        {'id': 'raw-multiple', 'query': '소득세법 제55조와 부가가치세법 제39조 원문 보여줘',
         'required': [('소득세법','제55조'), ('부가가치세법','제39조')], 'exact': True},
        {'id': 'raw-quoted', 'query': '「소득세법」 제55조 원문 보여줘',
         'required': [('소득세법','제55조')], 'exact': True},
        {'id': 'raw-unknown', 'query': '가짜소득세법 제55조 원문 보여줘',
         'required': [], 'exact': True},
        {'id': 'polarity', 'query': by_id['vat-02']['input']['query'],
         'required': [(j['evidence']['law'], j['evidence']['reference'])
                      for j in by_id['vat-02']['judgments'] if j['label']=='required']},
    ]
    results = []
    original = (config.SEARCH_FUZZY_ENABLED, config.SEARCH_REGEX_ENABLED, config.SEARCH_MMR_ENABLED)
    try:
        await warm_bm25_index()
        for case in cases:
            record = {'id': case['id'], 'query': case['query'], 'required': case['required']}
            for mode, enabled in [('baseline', False), ('algorithms', True)]:
                config.SEARCH_FUZZY_ENABLED = enabled
                config.SEARCH_REGEX_ENABLED = enabled
                config.SEARCH_MMR_ENABLED = enabled
                diagnostic = {}
                started = time.perf_counter()
                try:
                    hits = await hybrid_search([case['query'], case['query']+' 적용 요건 예외'],
                        original_query=case['query'], official_only=True, issue_mode=True,
                        diagnostics=diagnostic)
                    keys = [(r.law_name,r.article_no) for r in hits]
                    record[mode] = {'ids': keys, 'seconds': round(time.perf_counter()-started, 3),
                        'all_required_found': all(key in keys for key in case['required']),
                        'unexpected_raw_hits': sum(key not in case['required'] for key in keys)
                                               if case.get('exact') else None,
                        'diagnostics': diagnostic}
                except Exception as error:
                    record[mode] = {'error':type(error).__name__, 'all_required_found':False}
            results.append(record)
            print(json.dumps({'id': case['id'], 'baseline_found':record['baseline']['all_required_found'],
                'algorithms_found':record['algorithms']['all_required_found'],
                'fuzzy': record['algorithms'].get('diagnostics', {}).get('fuzzy', {}),
                'exact': record['algorithms'].get('diagnostics', {}).get('exact_reference_route', False)},
                ensure_ascii=False), flush=True)
        summary = {}
        for mode in ['baseline','algorithms']:
            summary[mode] = {'required_cases_found':sum(r[mode]['all_required_found'] for r in results if r['required']),
                             'required_cases':sum(bool(r['required']) for r in results),
                             'unexpected_raw_hits':sum(r[mode].get('unexpected_raw_hits') or 0 for r in results),
                             'errors':sum('error' in r[mode] for r in results)}
        Path(output).write_text(json.dumps({'status':'draft_diagnostic','summary':summary, 'cases':results},
                                          ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    finally:
        config.SEARCH_FUZZY_ENABLED, config.SEARCH_REGEX_ENABLED, config.SEARCH_MMR_ENABLED = original
        await close_bm25_index()
        await close_live_clients()


if __name__=='__main__':
    asyncio.run(main(sys.argv[1]))
