"""Explicit artifact publishing, never production tracing or model execution."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from evaluation.schema import Dataset, Run, Adjudication, digest
from evaluation.scoring import score_run, SCORER_VERSION

ENDPOINTS = {'us': 'https://api.smith.langchain.com', 'eu': 'https://eu.api.smith.langchain.com'}


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def prepare(run_dir, *, include_content=False, region='us', annotation_queue=False):
    """Construct exactly the application data to upload, without a Client/network."""
    directory = Path(run_dir)
    read = lambda name: json.loads((directory/name).read_text(encoding='utf-8'))
    dataset = Dataset.model_validate(read('dataset.json'))
    run = Run.model_validate(read('observations.json'))
    adjudications = [Adjudication.model_validate(item) for item in read('adjudications.json')]
    saved = read('report.json')
    report = score_run(dataset, run, adjudications)
    if digest(saved) != digest(report):
        raise ValueError('Report differs from current scorer; rescore to a new directory first')
    if annotation_queue and not include_content:
        raise ValueError('Human review requires explicitly approved content')
    examples = []
    cases = {case.id: case for case in dataset.cases}
    for identity in run.selected_ids:
        case = cases[identity]
        reference = dict(review_status=case.review.status, basis=case.review.basis, stage=case.stage)
        inputs = {'case_id': identity}
        if include_content:
            inputs['input'] = case.input
            reference['specification'] = case.model_dump(mode='json')
        examples.append(dict(case_id=identity, inputs=inputs, outputs=reference, split=case.split))
    observations = {(o.case_id, o.variant, o.repeat): o for o in run.observations}
    records = []
    for row in report['rows']:
        observation = observations.get((row['case_id'], row['variant'], row['repeat']))
        output = {'status': row['status'], 'review_status': row['review_status'], 'basis': row['basis']}
        if include_content:
            output.update(payload=observation.payload if observation else None, reasons=row['reasons'])
        namespace = 'approved' if row['review_status'] == 'approved' else 'diagnostic'
        feedback = [{'key': 'evaluation_status', 'value': row['status']}]
        for key, value in row['metrics'].items():
            if isinstance(value, (int, float)) and math.isfinite(value):
                feedback.append({'key': f'{namespace}.{row["basis"]}.{key}', 'score': value})
        if observation:
            feedback.append({'key': 'observed_elapsed_seconds', 'score': observation.elapsed_seconds})
        records.append(dict(case_id=row['case_id'], variant=row['variant'], repeat=row['repeat'],
                            outputs=output, feedback=feedback, review_status=row['review_status'],
                            stage=row['stage'], basis=row['basis']))
    return dict(schema_version='1.0', endpoint=ENDPOINTS[region], include_content=include_content,
                annotation_queue=annotation_queue, examples=examples, records=records,
                dataset_key=digest(examples), dataset_hash=dataset.fingerprint(),
                observations_hash=report['observations_hash'], scorer_version=SCORER_VERSION,
                gate=report['gate'], split=run.split, mode=run.mode, repeats=run.repeats,
                notice='Stored artifact import, not a new inference run. Drafts are diagnostic, not tax accuracy.')


def publish(plan, *, approved_sha256, receipt_path, client_factory=None, env_file='.env.example'):
    """Publish only a byte-content-approved plan. A receipt guards accidental retries."""
    fingerprint = digest(plan)
    if fingerprint != approved_sha256:
        raise ValueError('Approval hash mismatch')
    if plan['endpoint'] not in ENDPOINTS.values() or plan['schema_version'] != '1.0':
        raise ValueError('Unsupported endpoint or plan version')
    if not plan['examples'] or not plan['records'] or plan['dataset_key'] != digest(plan['examples']):
        raise ValueError('Invalid plan')
    if plan['annotation_queue'] and not plan['include_content']:
        raise ValueError('Review queue requires content')
    if Path(receipt_path).exists():
        raise FileExistsError('Receipt exists; inspect prior publication before retrying')
    if client_factory is None:
        from dotenv import dotenv_values
        from langsmith import Client
        settings = dotenv_values(env_file) if Path(env_file).is_file() else {}
        key = os.environ.get('TAX_EVAL_LANGSMITH_API_KEY') or settings.get('LANGSMITH_API_KEY')
        if not key or not key.strip():
            raise ValueError('Set the evaluation-only API key in .env.example')
        if os.environ.get('LANGSMITH_RUNS_ENDPOINTS') or os.environ.get('LANGCHAIN_RUNS_ENDPOINTS'):
            raise ValueError('Disable trace replicas before publishing to one approved endpoint')
        # No load_dotenv: never turn on application tracing as a side effect.
        client_factory = lambda: Client(api_url=plan['endpoint'], api_key=key,
                                        auto_batch_tracing=False, omit_traced_runtime_info=True,
                                        tracing_sampling_rate=1.0, otel_enabled=False,
                                        hide_inputs=False, hide_outputs=False, hide_metadata=False)
    receipt = dict(plan_hash=fingerprint, status='started', dataset=None, projects=[], runs=[], queue=None)
    write_new(receipt_path, receipt)

    def checkpoint():
        # Only this newly created receipt is updated; gold/run artifacts are never edited.
        Path(receipt_path).write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

    client = None
    try:
        client = client_factory()
        dataset_name = 'tax-eval-' + plan['dataset_key']
        variants = sorted({record['variant'] for record in plan['records']})
        project_names = {variant: f'tax-eval-{variant}-{fingerprint[:24]}' for variant in variants}
        # Never append duplicate observations to a previous or partially uploaded experiment.
        if any(client.has_project(project_name=name) for name in project_names.values()):
            raise FileExistsError('Experiment already exists; inspect receipt and remote state')
        if client.has_dataset(dataset_name=dataset_name):
            dataset = client.read_dataset(dataset_name=dataset_name)
            remote = list(client.list_examples(dataset_id=dataset.id))
            expected = {str(uuid5(NAMESPACE_URL, dataset_name + ':' + e['case_id'])): e for e in plan['examples']}
            if len(remote) != len(expected) or any(str(e.id) not in expected
                or digest(e.inputs) != digest(expected[str(e.id)]['inputs'])
                or digest(e.outputs) != digest(expected[str(e.id)]['outputs']) for e in remote):
                raise ValueError('Remote reference dataset changed; do not overwrite it')
        else:
            dataset = client.create_dataset(dataset_name=dataset_name, description=plan['notice'])
            receipt['dataset'] = str(dataset.id)
            checkpoint()
            for example in plan['examples']:
                client.create_example(dataset_id=dataset.id,
                    example_id=uuid5(NAMESPACE_URL, dataset_name + ':' + example['case_id']),
                    inputs=example['inputs'], outputs=example['outputs'], split=example['split'])
        receipt['dataset'] = str(dataset.id)
        inputs = {e['case_id']: e['inputs'] for e in plan['examples']}
        metadata = {key: plan[key] for key in ('dataset_hash', 'observations_hash', 'scorer_version', 'gate', 'split', 'mode')}
        metadata.update(artifact_import=True, plan_hash=fingerprint, timing='Use observed_elapsed_seconds; native timing is import time')
        for variant, name in project_names.items():
            project = client.create_project(name, reference_dataset_id=dataset.id,
                                            description=plan['notice'], metadata=metadata, upsert=False)
            receipt['projects'].append({'id': str(project.id), 'name': name})
            checkpoint()
            for record in (r for r in plan['records'] if r['variant'] == variant):
                run_id = uuid4()
                now = datetime.now(timezone.utc)
                client.create_run(name=record['case_id'], id=run_id, run_type='chain', project_name=name,
                    reference_example_id=uuid5(NAMESPACE_URL, dataset_name + ':' + record['case_id']),
                    inputs=inputs[record['case_id']], outputs=record['outputs'], start_time=now, end_time=now,
                    extra={'metadata': metadata | {k: record[k] for k in ('variant', 'repeat', 'review_status', 'stage', 'basis')}})
                receipt['runs'].append(str(run_id))
                checkpoint()
                for feedback in record['feedback']:
                    client.create_feedback(run_id=run_id, **feedback)
        if plan['annotation_queue']:
            queue = client.create_annotation_queue(name='tax-eval-review-' + fingerprint[:24],
                description='Human review only; local gold and gate are not automatically updated.',
                rubric_instructions='Review inputs, reference specification and actual outputs. Distinguish required/supporting/irrelevant/hard_negative; record source, date and rationale. Never approve missing evidence. Export and reconcile human reviews locally before rescoring.')
            receipt['queue'] = str(queue.id)
            checkpoint()
            client.add_runs_to_annotation_queue(queue.id, run_ids=[UUID(value) for value in receipt['runs']])
        receipt['status'] = 'complete'
        checkpoint()
        return receipt
    except Exception as error:
        receipt.update(status='partial_or_failed', error_type=type(error).__name__)
        checkpoint()
        raise RuntimeError('LangSmith publication failed; inspect the local receipt') from None
    finally:
        if client is not None:
            client.close()
