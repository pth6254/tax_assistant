"""Publishing boundary tests: no actual LangSmith account or network required."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import create_autospec
from uuid import uuid4

import pytest

from evaluation.langsmith_bridge import prepare, publish, write_new
from evaluation.runner import write_artifacts
from evaluation.schema import Case, Dataset, Observation, Run, digest


@pytest.fixture
def artifacts(tmp_path):
    case = Case.model_validate(dict(id='example-one', group='one', split='dev', stage='retrieval', adapter='retrieval',
        review=dict(status='draft',basis='official_source'), input={'query':'PRIVATE QUESTION'},
        judgments=[dict(evidence=dict(law='합성법',reference='제1조'),label='required',reason='PRIVATE REASON')]))
    data = Dataset(name='test',version='1',description='test',cases=[case])
    records = [Observation(case_id=case.id,variant=variant,payload={'results':[dict(law='합성법',reference='제1조',quote='PRIVATE QUOTE')]},elapsed_seconds=2.5) for variant in ('base','graph')]
    run = Run(dataset_hash=data.fingerprint(),split='dev',mode='recorded',selected_ids=[case.id],observations=records,
              metadata={'secret':'DO NOT UPLOAD THIS METADATA'})
    directory=tmp_path/'run'
    write_artifacts(directory,data,run)
    return directory


def fake_client():
    from langsmith import Client
    client=create_autospec(Client,instance=True)
    client.has_project.return_value=False
    client.has_dataset.return_value=False
    client.create_dataset.return_value=SimpleNamespace(id=uuid4())
    client.create_project.side_effect=lambda *a,**kw:SimpleNamespace(id=uuid4())
    client.create_annotation_queue.return_value=SimpleNamespace(id=uuid4())
    return client


def test_prepare_default_redacts_content_and_preserves_draft(artifacts):
    plan=prepare(artifacts)
    encoded=json.dumps(plan)
    assert 'PRIVATE' not in encoded
    assert 'DO NOT UPLOAD' not in encoded
    assert plan['gate']=='incomplete'
    assert all(r['review_status']=='draft' for r in plan['records'])
    assert any(f['key'].startswith('diagnostic.') for f in plan['records'][0]['feedback'])
    assert not any(f['key'].startswith('approved.') for f in plan['records'][0]['feedback'])


def test_content_opt_in_and_annotation_requirement(artifacts):
    plan=prepare(artifacts,include_content=True,annotation_queue=True)
    assert 'PRIVATE QUESTION' in json.dumps(plan)
    assert 'PRIVATE QUOTE' in json.dumps(plan)
    assert 'DO NOT UPLOAD' not in json.dumps(plan)
    with pytest.raises(ValueError): prepare(artifacts,annotation_queue=True)


def test_tampered_artifact_rejected(artifacts):
    path=artifacts/'report.json'
    value=json.loads(path.read_text());value['gate']='pass'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):prepare(artifacts)


def test_approval_before_client_or_receipt(artifacts,tmp_path):
    plan=prepare(artifacts)
    with pytest.raises(ValueError):
        publish(plan,approved_sha256='wrong',receipt_path=tmp_path/'receipt.json',client_factory=lambda:pytest.fail('Network attempted'))
    assert not (tmp_path/'receipt.json').exists()


def test_publish_experiments_feedback_queue_and_no_source_edits(artifacts,tmp_path):
    before={p.name:p.read_bytes() for p in artifacts.iterdir()}
    plan=prepare(artifacts,include_content=True,annotation_queue=True)
    client=fake_client()
    receipt=publish(plan,approved_sha256=digest(plan),receipt_path=tmp_path/'receipt.json',client_factory=lambda:client)
    assert receipt['status']=='complete'
    assert client.create_project.call_count==2
    assert client.create_example.call_count==1
    assert client.create_run.call_count==2
    assert client.add_runs_to_annotation_queue.call_count==1
    assert client.close.call_count==1
    assert len({str(c.kwargs['reference_example_id']) for c in client.create_run.call_args_list})==1
    assert all(c.kwargs['start_time']==c.kwargs['end_time'] for c in client.create_run.call_args_list)
    assert before=={p.name:p.read_bytes() for p in artifacts.iterdir()}
    with pytest.raises(FileExistsError):
        publish(plan,approved_sha256=digest(plan),receipt_path=tmp_path/'receipt.json',client_factory=lambda:pytest.fail('Retry'))


def test_remote_error_receipt_does_not_leak(artifacts,tmp_path):
    plan=prepare(artifacts);client=fake_client()
    client.create_run.side_effect=RuntimeError('PRIVATE TOKEN')
    path=tmp_path/'receipt.json'
    with pytest.raises(RuntimeError,match='publication failed') as error:
        publish(plan,approved_sha256=digest(plan),receipt_path=path,client_factory=lambda:client)
    assert 'PRIVATE TOKEN' not in str(error.value)
    assert 'PRIVATE TOKEN' not in path.read_text()
    assert json.loads(path.read_text())['status']=='partial_or_failed'


def test_remote_dataset_mutation_rejected(artifacts,tmp_path):
    plan=prepare(artifacts);client=fake_client()
    client.has_dataset.return_value=True
    client.read_dataset.return_value=SimpleNamespace(id=uuid4())
    client.list_examples.return_value=[]
    with pytest.raises(RuntimeError):publish(plan,approved_sha256=digest(plan),receipt_path=tmp_path/'r.json',client_factory=lambda:client)
    client.create_run.assert_not_called()
    client.create_example.assert_not_called()


def test_missing_key_and_no_overwrite(artifacts,tmp_path,monkeypatch):
    monkeypatch.delenv('TAX_EVAL_LANGSMITH_API_KEY',raising=False)
    plan=prepare(artifacts)
    with pytest.raises(ValueError):publish(plan,approved_sha256=digest(plan),receipt_path=tmp_path/'r.json',env_file=tmp_path/'missing')
    assert not (tmp_path/'r.json').exists()
    path=tmp_path/'plan.json';write_new(path,plan)
    with pytest.raises(FileExistsError):write_new(path,plan)


def test_existing_project_not_appended(artifacts,tmp_path):
    plan=prepare(artifacts);client=fake_client();client.has_project.return_value=True
    with pytest.raises(RuntimeError):publish(plan,approved_sha256=digest(plan),receipt_path=tmp_path/'r.json',client_factory=lambda:client)
    client.create_run.assert_not_called()
    client.create_dataset.assert_not_called()


def test_default_key_file_is_env_example(artifacts,tmp_path,monkeypatch):
    import langsmith
    monkeypatch.chdir(tmp_path)
    for name in ('TAX_EVAL_LANGSMITH_API_KEY','LANGSMITH_RUNS_ENDPOINTS','LANGCHAIN_RUNS_ENDPOINTS'):
        monkeypatch.delenv(name,raising=False)
    (tmp_path/'.env.example').write_text('LANGSMITH_API_KEY=synthetic-test-key\n',encoding='utf-8')
    client=fake_client()
    captured={}
    def factory(**kwargs):
        captured.update(kwargs)
        return client
    monkeypatch.setattr(langsmith,'Client',factory)
    plan=prepare(artifacts)
    receipt=publish(plan,approved_sha256=digest(plan),receipt_path=tmp_path/'receipt.json')
    assert receipt['status']=='complete'
    assert captured['api_key']=='synthetic-test-key'
    assert captured['auto_batch_tracing'] is False
