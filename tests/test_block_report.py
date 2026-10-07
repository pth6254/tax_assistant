"""Block tabulation reads stored observations only; it never re-judges."""
import json

from evaluation.block_report import block_report


def record(case_id, claims, verdicts, answer='답변'):
    return {'case_id': case_id, 'status': 'fail', 'observation': {
        'answer': answer, 'verification': {
            'claims': [{'id': key, 'released': not errors, 'errors': errors} for key, errors in claims],
            'judge': {'claims': [{'claim_id': key, 'support': value, 'applicability': value}
                                 for key, value in verdicts.items()]}}}}


def test_judge_supported_code_blocks_are_ranked_and_cascades_counted(tmp_path):
    experiment = {'records': [
        record('income', [('C1', ['prose_reference_mismatch', 'prose_reference_mismatch'])],
               {'C1': 'supported'}),
        record('gains', [('C1', []), ('C2', ['prose_reference_mismatch']), ('C3', ['dependency_withheld']),
                         ('C4', ['semantic_check_not_passed'])],
               {'C1': 'supported', 'C2': 'supported', 'C3': 'supported', 'C4': 'insufficient'}),
        {'case_id': 'gift', 'observation': {'answer': '조회할 법령명을 하나 지정해 주세요.', 'verification': None}},
    ]}
    (tmp_path / 'run').mkdir()
    (tmp_path / 'run' / 'experiment.json').write_text(json.dumps(experiment), encoding='utf-8')
    report = block_report([str(tmp_path / 'run')])
    assert (report['claims'], report['released'], report['withheld']) == (5, 1, 4)
    assert report['cases_with_claims'] == 2
    assert [case['case_id'] for case in report['cases_without_claims']] == ['gift']
    assert report['false_block_candidates'] == 2 and report['cascade_only'] == 1
    top = report['by_code'][0]
    assert top['code'] == 'prose_reference_mismatch' and top['category'] == 'repairable'
    assert (top['claims'], top['judge_supported'], top['sole_blocker']) == (2, 2, 2)
    semantic = next(row for row in report['by_code'] if row['code'] == 'semantic_check_not_passed')
    assert semantic['judge_not_supported'] == 1 and semantic['sole_blocker'] == 0


def test_same_case_id_in_two_runs_is_not_merged(tmp_path):
    paths = []
    for name in ('a', 'b'):
        path = tmp_path / f'{name}.json'
        path.write_text(json.dumps({'records': [record('gains', [('C1', [])], {'C1': 'supported'})]}),
                        encoding='utf-8')
        paths.append(str(path))
    assert block_report(paths)['cases_with_claims'] == 2
