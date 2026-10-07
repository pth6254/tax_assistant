"""Which release checks withhold claims, cross-tabulated with the claim Judge.

Read-only over stored automatic experiments; no model calls. A claim the Judge
marked supported but a code check still withheld is a *candidate* false block:
the Judge is the same model family and not an independent tax answer, so the
table ranks checks to inspect, it does not prove a check wrong.
"""
from collections import Counter, defaultdict
import json
from pathlib import Path

from app.services.claim_verification import error_category

JUDGE_CODE = 'semantic_check_not_passed'
CASCADE_CODE = 'dependency_withheld'


def load_experiments(paths):
    experiments = []
    for value in paths:
        path = Path(value)
        if path.is_dir():
            path = path / 'experiment.json'
        experiments.append((str(path), json.loads(path.read_text(encoding='utf-8'))))
    return experiments


def claim_rows(experiment, source=''):
    for record in experiment.get('records', []):
        verification = (record.get('observation') or {}).get('verification') or {}
        judge = verification.get('judge') or {}
        verdicts = {row['claim_id']: row for row in judge.get('claims', [])}
        for claim in verification.get('claims', []):
            verdict = verdicts.get(claim['id'])
            yield {
                'experiment': source,
                'case_id': record['case_id'],
                'case_status': record.get('status'),
                'claim_id': claim['id'],
                'released': bool(claim.get('released')),
                'errors': list(dict.fromkeys(claim.get('errors', []))),
                'judge': ('missing' if verdict is None else
                          'supported' if verdict.get('support') == 'supported'
                          and verdict.get('applicability') == 'supported' else 'not_supported'),
            }


def cases_without_claims(experiment, source=''):
    """No claim at all means the answer never reached claim release (routing, tool or plan)."""
    return [{'experiment': source, 'case_id': record['case_id'], 'answer_start': (
                (record.get('observation') or {}).get('answer') or '')[:80]}
            for record in experiment.get('records', [])
            if not (((record.get('observation') or {}).get('verification') or {}).get('claims'))]


def summarize(rows, unreleased_cases=()):
    rows = list(rows)
    withheld = [row for row in rows if not row['released']]
    codes = defaultdict(lambda: Counter(claims=0, judge_supported=0, judge_not_supported=0,
                                        judge_missing=0, sole_blocker=0))
    for row in withheld:
        code_errors = [code for code in row['errors'] if code != JUDGE_CODE]
        for code in row['errors']:
            counts = codes[code]
            counts['claims'] += 1
            counts['judge_' + row['judge']] += 1
            if code_errors == [code] and row['judge'] == 'supported':
                counts['sole_blocker'] += 1
    # The Judge supported it and only deterministic checks (not cascades) blocked it.
    candidates = [row for row in withheld if row['judge'] == 'supported'
                  and set(row['errors']) - {JUDGE_CODE, CASCADE_CODE}]
    cascades = [row for row in withheld if row['errors'] == [CASCADE_CODE]]
    by_code = sorted(
        ({'code': code, 'category': error_category(code), **counts} for code, counts in codes.items()),
        key=lambda item: (-item['sole_blocker'], -item['judge_supported'], -item['claims'], item['code']))
    return {
        'note': 'Judge 판정은 독립 세무 정답이 아니며, 오탐 후보는 검사 항목 점검 순서일 뿐입니다.',
        'cases_with_claims': len({(row['experiment'], row['case_id']) for row in rows}),
        'cases_without_claims': list(unreleased_cases),
        'claims': len(rows),
        'released': len(rows) - len(withheld),
        'withheld': len(withheld),
        'false_block_candidates': len(candidates),
        'cascade_only': len(cascades),
        'by_code': by_code,
        'candidates': [{key: row[key] for key in ('experiment', 'case_id', 'claim_id', 'errors')}
                       for row in candidates],
    }


def block_report(paths):
    experiments = load_experiments(paths)
    report = summarize((row for path, experiment in experiments for row in claim_rows(experiment, path)),
                       [case for path, experiment in experiments for case in cases_without_claims(experiment, path)])
    report['experiments'] = [path for path, _ in experiments]
    return report
