"""Explicit automatic publishing of frozen public/synthetic evaluation artifacts."""
import json
import math
import os
from pathlib import Path

from evaluation.auto_cards import load_cards, save_json
from evaluation.auto_pipeline import validate_experiment
from evaluation.langsmith_bridge import ENDPOINTS, publish
from evaluation.schema import digest


def prepare(root, run_dir, *, region='us'):
    dataset = load_cards(root)
    experiment = json.loads((Path(run_dir) / 'experiment.json').read_text(encoding='utf-8'))
    if experiment.get('schema_version') != 'auto-eval-1' or experiment['options']['dataset_hash'] != dataset.fingerprint():
        raise ValueError('automatic_experiment_dataset_mismatch')
    validate_experiment(experiment, build_failures=dataset.failures)
    cards = {c.id: c for c in dataset.cards}
    selected = experiment['options']['selected_ids']
    records = experiment['records']
    if not selected or len(selected) != len(set(selected)) or {r['case_id'] for r in records} != set(selected) or len(records) != len(selected):
        raise ValueError('automatic_experiment_coverage')
    examples, uploads = [], []
    packages = {p.id: p for p in dataset.packages}
    for row in records:
        card = cards.get(row['case_id'])
        if card is None or row['card_hash'] != digest(card.model_dump(mode='json')) or row.get('status') == 'pending_judge':
            raise ValueError('automatic_card_mismatch')
        observation = row['observation']
        if row.get('observation_hash') != digest(observation):
            raise ValueError('automatic_observation_changed')
        # A synthetic-only isolated worker must never return private document evidence.
        if any(r.get('origin') == 'user_document' for key in ('contexts', 'generation')
               for f in observation.get(key, []) for r in f.get('records', [])) or any(
               r.get('origin_kind') == 'user_document' for f in observation.get('retrieval', [])
               for r in f.get('results', [])):
            raise ValueError('private_evidence_in_automatic_upload')
        package = packages[card.package_id]
        used = {c.source_id for i in card.draft.issues for e in i.required + i.forbidden for c in e.citations}
        examples.append({'case_id': card.id, 'split': card.split,
            'inputs': {'case_id': card.id, 'question': card.draft.question},
            'outputs': {'review_status': 'draft', 'human_approved': False,
                'auto_validation': 'auto_validated', 'specification': card.draft.model_dump(mode='json'),
                'reference_sources': [s.model_dump(mode='json', exclude={'snapshot_file'})
                                      for s in package.sources if s.id in used]}})
        feedback = [{'key': 'evaluation_status', 'value': row['status']}]
        for item in row['criteria']:
            status = item['verdict']
            if status not in {'pass', 'fail', 'unknown', 'error', 'not_applicable'}:
                raise ValueError('automatic_feedback_verdict')
            feedback.append({'key': 'diagnostic.auto.' + item['criterion_id'],
                **({'score': int(status == 'pass')} if status in {'pass', 'fail'} else {'value': status})})
        elapsed = observation.get('elapsed_seconds')
        if isinstance(elapsed, (float, int)) and math.isfinite(elapsed) and elapsed >= 0:
            feedback.append({'key': 'observed_elapsed_seconds', 'score': elapsed})
        uploads.append({'case_id': card.id, 'variant': 'system', 'repeat': 1,
            'review_status': 'draft', 'stage': 'answer', 'basis': 'official_source',
            'outputs': {'status': row['status'], 'answer': observation.get('answer', ''),
                        'criteria': row['criteria'], 'verification': observation.get('verification', {}),
                        'error': observation.get('error'), 'human_approved': False}, 'feedback': feedback})
    return {'schema_version': '1.0', 'endpoint': ENDPOINTS[region], 'include_content': True,
            'annotation_queue': False, 'examples': examples, 'records': uploads,
            'dataset_key': digest(examples), 'dataset_hash': dataset.fingerprint(),
            'observations_hash': digest(records), 'scorer_version': 'auto-diagnostic-1',
            'gate': 'incomplete', 'split': experiment['options']['split'], 'mode': 'recorded', 'repeats': 1,
            'judge': {key: experiment['options'][key] for key in (
                'provider', 'model', 'prompt_hash', 'code_hash', 'runtime', 'collection_mode',
                'generation_code_hash', 'observation_source_hash') if key in experiment['options']},
            'notice': 'Public official sources and synthetic cases. Automatic diagnostic, no human legal approval. '
                      'Use observed_elapsed_seconds for actual execution latency.'}


def publish_automatic(root, run_dir, *, region='us', client_factory=None):
    """--publish authorizes this fixed public/synthetic scope; no manual hash prompt."""
    run_dir = Path(run_dir)
    plan = prepare(root, run_dir, region=region)
    plan_path, receipt_path = run_dir / 'langsmith-plan.json', run_dir / 'langsmith-receipt.json'
    if plan_path.exists():
        if digest(json.loads(plan_path.read_text(encoding='utf-8'))) != digest(plan):
            raise ValueError('automatic_publish_plan_changed')
    else:
        save_json(plan_path, plan)
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        if receipt.get('status') == 'complete' and receipt.get('plan_hash') == digest(plan):
            return receipt  # No duplicate uploads after a completed batch.
        raise ValueError('inspect_partial_langsmith_receipt')
    if client_factory is None:
        from langsmith import Client
        key = os.environ.get('TAX_EVAL_LANGSMITH_API_KEY') or os.environ.get('LANGSMITH_API_KEY')
        if not key:
            raise ValueError('automatic_langsmith_key_missing')
        if os.environ.get('LANGSMITH_RUNS_ENDPOINTS') or os.environ.get('LANGCHAIN_RUNS_ENDPOINTS'):
            raise ValueError('automatic_langsmith_replicas_enabled')
        client_factory = lambda: Client(api_url=plan['endpoint'], api_key=key,
            auto_batch_tracing=False, omit_traced_runtime_info=True, otel_enabled=False,
            hide_inputs=False, hide_outputs=False, hide_metadata=False)
    return publish(plan, approved_sha256=digest(plan), receipt_path=receipt_path, client_factory=client_factory)
