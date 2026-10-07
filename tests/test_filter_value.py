"""Mutation measurement reads stored runs and never calls a model without judge=True."""
import json

import pytest

from app.schemas.reliability import Issue, QuestionPlan
from app.services.evidence import digest, record_from_result
from evaluation.filter_value import filter_report
from tests.test_reliability_workflow import source

TEXT = '제1조\n① 거주자의 이자소득은 원천징수된 경우 합산하지 않는다. 다만 예외 소득은 합산한다.'


def experiment(claims):
    record = record_from_result(source(content=TEXT, original_text=TEXT, content_hash=digest(TEXT),
                                       law_name='소득세법'))
    plan = QuestionPlan(issues=[Issue(id='I1', request_quote='합산하는지 판단해 주세요.', subject='A',
                                      law='소득세법', question='이자소득 합산')])
    return {'records': [{'case_id': 'case', 'status': 'fail', 'observation': {
        'answer': '', 'verification': {'claims': [], 'judge': None},
        'contexts': [{'plan': plan.model_dump(mode='json'), 'coverage': {}}],
        'generation': [{'issue_id': 'I1', 'records': [record.model_dump(mode='json')], 'generation_error': None,
                        'draft': {'claims': [dict(id=f'I1:C{n}', issue_id='I1', text=text, kind='legal',
                                                  citations=[{'evidence_id': record.id,
                                                              'quote': '거주자의 이자소득은 원천징수된 경우 합산하지 않는다.'}],
                                                  conditions=[], depends_on=['I1:C0'])
                                             for n, text in enumerate(claims, 1)]}}]}}]}


@pytest.mark.asyncio
async def test_known_errors_are_attributed_to_the_checks_that_catch_them(tmp_path):
    path = tmp_path / 'experiment.json'
    path.write_text(json.dumps(experiment([
        '원천징수된 이자소득은 합산하지 않습니다. 다만 예외 소득은 합산합니다.',
        '시험법 제7조에 따라 합산합니다.',   # already fails a check: never a seed
    ])), encoding='utf-8')
    report = await filter_report([str(path)])
    assert report['seeds'] == 1 and report['seed_judge'] == 'not_run'
    mutations = report['by_mutation']
    for name in ('unsupported_article', 'invented_tax_amount', 'tampered_quote'):
        assert mutations[name]['applied'] == mutations[name]['caught_by_block_code'] == 1, name
    assert mutations['other_tax_scope']['signalled_only'] == 1
    for name in ('flipped_conclusion', 'dropped_exception'):
        assert mutations[name]['judge_only_by_design'] and mutations[name]['not_caught_by_code'] == 1
    assert mutations['other_subject']['applied'] == 0  # A single subject has no one to swap with.
    codes = {row['code']: row for row in report['by_code']}
    assert codes['tax_scope_mismatch']['gate'] == 'signal'
    assert codes['prose_reference_mismatch']['catches'] == 1
