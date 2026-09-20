"""Test the evaluator itself: deliberately wrong outputs must not receive a pass."""
import asyncio
from copy import deepcopy
from datetime import date
import json

import pytest
from pydantic import ValidationError

from evaluation.schema import Case, Dataset, Observation, Run, Review, Adjudication, digest
from evaluation.scoring import score_case, score_run, check_value
from evaluation.runner import load_dataset, collect, compare, write_artifacts


REVIEW = dict(status='approved', basis='synthetic_contract', reviewer='test-spec',
              reviewer_kind='contract_author', reviewed_on='2026-09-19')


def document(ref='제1조', law='합성법', **kwargs):
    return dict(law=law, reference=ref, **kwargs)


def retrieval_case(**overrides):
    values = dict(id='retrieval-case', group='one-question', split='test', stage='retrieval',
                  adapter='retrieval', review=REVIEW, input={'query': '합성 질문'},
                  judgments=[dict(evidence=document(), label='required', reason='Required synthetic target'),
                             dict(evidence=document('제10조'), label='hard_negative', reason='Not article 1', confusion='same_terms')])
    return Case.model_validate(values | overrides)


def result(case, documents, **payload):
    return score_case(case, Observation(case_id=case.id, variant='base', payload={'results': documents, **payload}))


def dataset(case):
    return Dataset(name='test', version='1', description='Synthetic evaluator checks', cases=[case])


def run_for(data, observations, **kwargs):
    return Run(dataset_hash=data.fingerprint(), split='test', mode='recorded', selected_ids=[c.id for c in data.cases],
               observations=observations, **kwargs)


def test_exact_article_not_substring_and_wrong_law():
    case = retrieval_case()
    assert result(case, [document()])['status'] == 'pass'
    for wrong in [document('제10조'), document('제1조의2'), document(law='다른법')]:
        assert result(case, [wrong])['status'] == 'fail'
        assert result(case, [wrong])['metrics']['recall_at_k'] == 0


def test_unknown_does_not_become_negative_or_correct():
    row = result(retrieval_case(), [document(), document('제2조')])
    assert row['status'] == 'incomplete'
    assert row['metrics']['judged_precision'] == 1
    assert row['metrics']['precision_lower_bound'] == 0.5
    assert row['metrics']['judgment_coverage'] == 0.5


def test_hard_negative_fails_even_when_gold_found_and_outside_top_k():
    row = result(retrieval_case(k=1), [document(), document('제10조')])
    assert row['status'] == 'fail'
    assert row['metrics']['recall_at_k'] == 1
    assert row['critical_failures'] == ['hard_negative_returned']


def test_negative_ranks_above_positive():
    row = result(retrieval_case(), [document('제10조'), document()])
    assert row['metrics']['hard_negative_outranks_positive'] is True
    assert row['metrics']['mrr'] == 0.5


def test_duplicate_hits_do_not_inflate_precision_or_recall():
    row = result(retrieval_case(), [document(), document(), document('제10조')])
    assert row['metrics']['duplicate_count'] == 1
    assert row['metrics']['judged_precision'] == 0.5


def test_graph_added_metrics_separate_from_base():
    row = result(retrieval_case(), [document(), document('제10조')], base_results=[document()])
    assert row['metrics']['added_required_gain'] == 0
    assert row['metrics']['added_hard_negative_count'] == 1
    assert row['metrics']['added_judged_precision'] == 0


def test_branch_and_paragraph_identity_are_distinct():
    case = retrieval_case(judgments=[dict(evidence=document('제59조의4'), label='required', reason='Branch, not paragraph')])
    assert result(case, [document('제59조 제4항')])['metrics']['recall_at_k'] == 0


def test_version_specific_hard_negative():
    case = retrieval_case(judgments=[
        dict(evidence=document(version='new'), label='required', reason='Required version'),
        dict(evidence=document(version='old'), label='hard_negative', reason='Wrong date', confusion='wrong_date')])
    assert result(case, [document(version='old')])['status'] == 'fail'
    assert result(case, [document(version='new')])['status'] == 'pass'


def test_interpretation_identifiers_are_not_law_articles():
    case = retrieval_case(judgments=[dict(evidence=document('10-0075', kind='interpretation'), label='required', reason='Case ID')])
    assert result(case, [document('10-0075', kind='interpretation')])['status'] == 'pass'


def test_unanswerable_requires_empty_results():
    case = retrieval_case(answerable=False, judgments=[])
    assert result(case, [])['status'] == 'pass'
    assert result(case, [document()])['status'] == 'fail'


def test_missing_observation_is_not_passing_skip():
    data = dataset(retrieval_case())
    report = score_run(data, run_for(data, []))
    assert report['gate'] == 'incomplete'
    assert len(report['rows']) == 2


def test_runtime_error_does_not_disappear_from_denominator():
    data = dataset(retrieval_case())
    report = score_run(data, run_for(data, [Observation(case_id='retrieval-case', variant='base', error='TimeoutError')]))
    assert report['gate'] == 'fail'
    assert report['rows'][0]['status'] == 'error'


def test_draft_perfect_run_cannot_pass_gate():
    case = retrieval_case(review={'status':'draft','basis':'official_source'})
    data = dataset(case)
    records = [Observation(case_id=case.id, variant=v, payload={'results':[document()]}) for v in ('base','graph')]
    assert score_run(data, run_for(data, records))['gate'] == 'incomplete'


def test_changed_dataset_duplicate_observations_and_split_leakage_rejected():
    data = dataset(retrieval_case())
    run = run_for(data, [])
    run.dataset_hash = 'wrong'
    with pytest.raises(ValueError):
        score_run(data, run)
    obs = Observation(case_id='retrieval-case', variant='base', payload={'results':[]})
    with pytest.raises(ValueError):
        score_run(data, run_for(data, [obs,obs]))
    other = data.cases[0].model_copy(update={'id':'other-case','split':'dev'})
    with pytest.raises(ValidationError):
        Dataset(name='bad',version='1',description='bad split',cases=[data.cases[0],other])


def test_legal_approval_needs_human_and_sources():
    with pytest.raises(ValidationError):
        Review.model_validate(REVIEW | {'basis':'official_source'})
    with pytest.raises(ValidationError):
        retrieval_case(review=REVIEW | {'basis':'official_source','reviewer_kind':'human'})


def test_conflicting_evidence_and_unexplained_hard_negative_rejected():
    case = retrieval_case().model_dump(mode='json')
    case['judgments'].append(dict(evidence=document(), label='irrelevant', reason='conflict'))
    with pytest.raises(ValidationError):
        Case.model_validate(case)
    case = retrieval_case().model_dump(mode='json')
    case['judgments'][1]['confusion'] = 'none'
    with pytest.raises(ValidationError):
        Case.model_validate(case)


def answer_case():
    return Case(id='answer-case', group='answer', split='test', stage='answer', adapter='recorded',
                review=REVIEW, input={'query':'합성 질문'},
                rubric=[{'id':'grounded','dimension':'grounding','instruction':'All claims supported by fixed context','critical':True}])


def test_answer_keywords_never_auto_approve_and_judgment_binds_exact_output():
    case = answer_case()
    obs = Observation(case_id=case.id, payload={'answer':'법 제1조를 인용하지만 다른 주장은 틀린 답변'})
    assert score_case(case, obs)['status'] == 'incomplete'
    review = Adjudication(case_id=case.id, variant='system', repeat=1, payload_hash=digest(obs.payload),
                          reviewer='human-test-fixture', reviewed_on=date(2026,9,19),
                          criteria={'grounded': {'passed':False,'rationale':'Unsupported claim','evidence':'다른 주장'}})
    assert score_case(case, obs, review)['status'] == 'fail'
    obs.payload['answer'] = '수정한 답변'
    assert score_case(case, obs, review)['status'] == 'incomplete'


def test_money_is_exact_and_missing_zero_is_not_equivalent():
    from evaluation.schema import Check
    check = Check(path='amount', op='number', expected=100)
    assert check_value({'amount':100},check)
    for value in [101, 99, True, 'NaN']:
        assert not check_value({'amount':value}, check)
    assert not check_value({}, check)
    assert not check_value({'amount':0}, Check(path='amount',op='absent',expected=None))


def test_all_counterexamples_and_actual_offline_contracts():
    data = load_dataset('evaluation/datasets/contracts.json')
    run = asyncio.run(collect(data, split='all'))
    report = score_run(data, run)
    assert report['gate'] == 'pass'
    assert len(run.observations) == len(data.cases)
    assert all(c.counterexamples for c in data.cases)


def test_report_is_reproducible_and_never_overwrites(tmp_path):
    data = dataset(answer_case())
    run = run_for(data, [])
    report = write_artifacts(tmp_path/'run',data,run)
    assert report['gate'] == 'incomplete'
    assert json.loads((tmp_path/'run'/'report.json').read_text())['dataset_hash'] == data.fingerprint()
    with pytest.raises(FileExistsError):
        write_artifacts(tmp_path/'run',data,run)


def test_comparison_rejects_changed_coverage():
    data = dataset(retrieval_case())
    report = score_run(data, run_for(data, []))
    candidate = deepcopy(report)
    candidate['selected_ids'] = []
    with pytest.raises(ValueError):
        compare(report,candidate)


def test_live_flag_restored_after_failure(monkeypatch):
    import config
    from unittest.mock import AsyncMock
    from evaluation.adapters import observe
    from app.services.search import hybrid_search_service
    monkeypatch.setattr(config,'GRAPH_RAG_ENABLED',False)
    monkeypatch.setattr(hybrid_search_service,'hybrid_search',AsyncMock(side_effect=RuntimeError('secret must not be logged')))
    records = asyncio.run(observe(retrieval_case(),'live','00000000-0000-0000-0000-000000000001',1,False,1))
    assert config.GRAPH_RAG_ENABLED is False
    assert all(r.error == 'RuntimeError' for r in records)
    assert 'secret' not in str(records)


def test_unrequested_generation_is_missing_not_synthetic_success():
    from evaluation.adapters import observe
    case = answer_case().model_copy(update={'adapter':'answer_fixed_context'})
    assert asyncio.run(observe(case,'live','unused',1,False,1)) == []


def test_draft_execution_error_still_fails_run():
    case = retrieval_case(review={'status':'draft','basis':'official_source'})
    data = dataset(case)
    run = run_for(data, [Observation(case_id=case.id,variant='base',error='TimeoutError')])
    assert score_run(data,run)['gate'] == 'fail'


def test_changed_source_blocks_pass():
    case = retrieval_case()
    data = dataset(case)
    records = [Observation(case_id=case.id,variant=v,payload={'results':[document()]}) for v in ('base','graph')]
    run = run_for(data,records,metadata={'source_stable':False})
    assert score_run(data,run)['gate'] == 'incomplete'


def test_all_dataset_files_validate():
    for name in ('contracts','retrieval','components'):
        load_dataset('evaluation/datasets/'+name+'.json')


def test_unknown_candidates_create_review_queue_not_new_gold(tmp_path):
    case = retrieval_case()
    data = dataset(case)
    original = data.fingerprint()
    run = run_for(data,[Observation(case_id=case.id,variant=v,payload={'results':[document(),document('제2조')]}) for v in ('base','graph')])
    write_artifacts(tmp_path/'run',data,run)
    queue = json.loads((tmp_path/'run'/'evidence_review_queue.json').read_text(encoding='utf-8'))
    assert len(queue) == 1
    assert queue[0]['label'] is None
    assert data.fingerprint() == original


def test_fixed_context_and_planner_do_not_require_database_snapshot(monkeypatch):
    from evaluation.runner import source_snapshot
    from app import database
    def forbidden():
        raise AssertionError('Unrelated database access')
    monkeypatch.setattr(database,'get_pool',forbidden)
    assert asyncio.run(source_snapshot({'tools','answer'})) == {}


def test_missing_gold_is_ungraded_not_a_wrong_answer():
    case = retrieval_case(review={'status':'draft','basis':'official_source'},judgments=[])
    row = result(case,[document()])
    assert row['status'] == 'incomplete'
    assert 'gold_evidence_not_defined' in row['reasons']
    assert row['metrics']['recall_at_k'] is None
