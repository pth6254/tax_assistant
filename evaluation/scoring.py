"""Deterministic metrics and fail-closed release decisions. No LLM self-grading."""
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import math

from evaluation.schema import Dataset, Evidence, Run, digest

SCORER_VERSION = '1.1'


def _labels(case, documents):
    judgments = {j.evidence.key(): j.label for j in case.judgments}
    unique, labels, seen = [], [], set()
    for document in documents:
        key = Evidence.model_validate(document).key()
        if key in seen:
            continue
        seen.add(key)
        label = judgments.get(key, judgments.get((*key[:2], ''), 'unjudged'))
        unique.append(key)
        labels.append(label)
    return unique, labels


def retrieval(case, payload):
    # Empty retrieval is a valid measured failure, but a missing field is not an empty result.
    if 'results' not in payload or not isinstance(payload['results'], list):
        raise ValueError('Missing retrieval results')
    keys, labels = _labels(case, payload['results'])
    required = [j.evidence.key() for j in case.judgments if j.label == 'required']

    def hit(target, found):
        return any(target[:2] == k[:2] and (not target[2] or target[2] == k[2]) for k in found)

    top = labels[:case.k]
    found = sum(hit(key, keys[:case.k]) for key in required)
    found_all = sum(hit(key, keys) for key in required)
    relevant = sum(label in {'required', 'supporting'} for label in labels)
    unknown = labels.count('unjudged')
    judged = len(labels) - unknown
    ranks = [i for i, label in enumerate(top, 1) if label in {'required', 'supporting'}]
    positives = [i for i, label in enumerate(labels, 1) if label in {'required', 'supporting'}]
    negatives = [i for i, label in enumerate(labels, 1) if label == 'hard_negative']
    gain = {'required': 3, 'supporting': 1}
    dcg = sum(gain.get(label, 0) / math.log2(i+2) for i, label in enumerate(top))
    ideal = sorted((gain.get(j.label, 0) for j in case.judgments), reverse=True)[:case.k]
    idcg = sum(value / math.log2(i+2) for i, value in enumerate(ideal))
    metrics = dict(recall_at_k=found/len(required) if required else None,
                   recall_all=found_all/len(required) if required else None,
                   mrr=1/min(ranks) if ranks else 0,
                   judged_precision=relevant/judged if judged else None,
                   precision_lower_bound=relevant/len(labels) if labels else None,
                   judgment_coverage=judged/len(labels) if labels else 1,
                   ndcg_lower_bound=dcg/idcg if idcg else None,
                   hard_negative_count=len(negatives), unjudged_count=unknown,
                   hard_negative_outranks_positive=bool(negatives and (not positives or min(negatives) < max(positives))),
                   returned_count=len(labels), duplicate_count=len(payload['results'])-len(labels))
    if 'base_results' in payload:
        base, _ = _labels(case, payload['base_results'])
        added = [(key, label) for key, label in zip(keys, labels) if key not in base]
        added_judged = [label for _, label in added if label != 'unjudged']
        metrics.update(added_count=len(added),
                       added_required_gain=sum(hit(key, keys) and not hit(key, base) for key in required),
                       added_judged_precision=sum(l in {'required', 'supporting'} for l in added_judged)/len(added_judged) if added_judged else None,
                       added_hard_negative_count=sum(l == 'hard_negative' for _, l in added),
                       added_unjudged_count=sum(l == 'unjudged' for _, l in added))
    reasons, pending = [], []
    if case.answerable:
        if not required:
            pending.append('gold_evidence_not_defined')
        elif metrics['recall_at_k'] < case.min_recall:
            reasons.append('required_evidence_missing_at_k')
    elif keys:
        reasons.append('unanswerable_case_returned_evidence')
    if len(negatives) > case.max_hard_negatives:
        reasons.append('hard_negative_returned')
    if judged and metrics['judged_precision'] < case.min_precision:
        reasons.append('insufficient_judged_precision')
    # Unknowns are not silently treated as irrelevant or correct.
    status = 'fail' if reasons else ('incomplete' if unknown or pending else 'pass')
    if unknown:
        reasons.append('unjudged_candidates_need_review')
    reasons.extend(pending)
    return status, metrics, reasons


def check_value(payload, check):
    value = payload
    for part in check.path.split('.'):
        if isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return check.op == 'absent'
    if check.op == 'absent':
        return False
    if check.op == 'equals':
        return type(value) is type(check.expected) and value == check.expected
    if check.op == 'contains':
        # A mechanical indicator, never semantic answer correctness.
        return isinstance(value, (str, list)) and check.expected in value
    if isinstance(value, bool) or isinstance(check.expected, bool):
        return False
    try:
        actual, expected = Decimal(str(value)), Decimal(str(check.expected))
        if not actual.is_finite() or not expected.is_finite():
            return False
        if check.op == 'number':
            return abs(actual-expected) <= Decimal(str(check.tolerance))
        return actual >= expected if check.op == 'min' else actual <= expected
    except (InvalidOperation, TypeError, ValueError):
        return False


def score_case(case, observation, adjudication=None):
    row = dict(case_id=case.id, stage=case.stage, variant=observation.variant,
               repeat=observation.repeat, basis=case.review.basis,
               review_status=case.review.status, elapsed_seconds=observation.elapsed_seconds,
               status='pass', metrics={}, reasons=[], critical_failures=[])
    if observation.error:
        row.update(status='error', reasons=[observation.error])
        return row
    payload = observation.payload
    if case.stage == 'retrieval':
        row['status'], row['metrics'], row['reasons'] = retrieval(case, payload)
        if row['metrics']['hard_negative_count'] > case.max_hard_negatives:
            row['critical_failures'].append('hard_negative_returned')
    elif not case.checks and not case.rubric:
        row.update(status='incomplete', reasons=['no_assertions'])
    checks = []
    for check in case.checks:
        passed = check_value(payload, check)
        checks.append(passed)
        if not passed:
            row['status'] = 'fail'
            row['reasons'].append('check_failed:' + check.path)
            if check.critical:
                row['critical_failures'].append(check.path)
    if checks:
        row['metrics']['assertion_pass_rate'] = sum(checks)/len(checks)
    if case.rubric:
        bound = (adjudication is not None and adjudication.payload_hash == digest(payload)
                 and set(adjudication.criteria) == {r.id for r in case.rubric})
        if not bound:
            if row['status'] != 'fail':
                row['status'] = 'incomplete'
            row['reasons'].append('missing_or_stale_human_adjudication')
        else:
            for criterion in case.rubric:
                verdict = adjudication.criteria[criterion.id]
                row['metrics']['rubric_' + criterion.id] = int(verdict.passed)
                if not verdict.passed:
                    row['status'] = 'fail'
                    row['reasons'].append('rubric_failed:' + criterion.id)
                    if criterion.critical:
                        row['critical_failures'].append(criterion.id)
    return row


def score_run(dataset: Dataset, run: Run, adjudications=()):
    if dataset.fingerprint() != run.dataset_hash:
        raise ValueError('Dataset changed; observations cannot be graded with different gold labels')
    cases = {c.id: c for c in dataset.cases}
    if not run.selected_ids or len(set(run.selected_ids)) != len(run.selected_ids):
        raise ValueError('Empty or duplicated selected case IDs')
    if any(i not in cases or (run.split != 'all' and cases[i].split != run.split) for i in run.selected_ids):
        raise ValueError('Unknown case or incorrect split')
    judgments = {}
    for item in adjudications:
        key = (item.case_id, item.variant, item.repeat)
        if key in judgments:
            raise ValueError('Duplicate adjudication')
        judgments[key] = item
    observations = {}
    for obs in run.observations:
        key = (obs.case_id, obs.variant, obs.repeat)
        variants = {'base', 'graph'} if cases.get(obs.case_id) and cases[obs.case_id].stage == 'retrieval' else {'system'}
        if (obs.case_id not in run.selected_ids or obs.repeat > run.repeats
                or obs.variant not in variants or key in observations):
            raise ValueError('Unexpected/duplicate observation')
        observations[key] = obs
    if any(key not in observations for key in judgments):
        raise ValueError('Adjudication does not match an observation in this run')
    rows = []
    for case_id in run.selected_ids:
        case = cases[case_id]
        variants = ['base', 'graph'] if case.stage == 'retrieval' else ['system']
        for repeat in range(1, run.repeats+1):
            for variant in variants:
                key = (case_id, variant, repeat)
                if key not in observations:
                    rows.append(dict(case_id=case_id, stage=case.stage, variant=variant, repeat=repeat,
                                     basis=case.review.basis, review_status=case.review.status,
                                     status='incomplete', metrics={}, reasons=['missing_observation'], critical_failures=[]))
                    continue
                try:
                    rows.append(score_case(case, observations[key], judgments.get(key)))
                except (ValueError, TypeError, KeyError) as error:
                    rows.append(dict(case_id=case_id, stage=case.stage, variant=variant, repeat=repeat,
                                     basis=case.review.basis, review_status=case.review.status,
                                     status='error', metrics={}, reasons=['invalid_observation:' + type(error).__name__], critical_failures=[]))
    buckets = defaultdict(list)
    for row in rows:
        buckets[(row['stage'], row['variant'], row['basis'], row['review_status'])].append(row)
    summaries = []
    for (stage, variant, basis, review), bucket in sorted(buckets.items()):
        metrics = defaultdict(list)
        for row in bucket:
            for key, value in row['metrics'].items():
                if value is not None:
                    metrics[key].append(float(value))
        summaries.append(dict(stage=stage, variant=variant, basis=basis, review_status=review,
                              total=len(bucket), statuses=dict(Counter(r['status'] for r in bucket)),
                              metrics={key: dict(mean=sum(values)/len(values), measured=len(values))
                                       for key, values in metrics.items()}))
    approved = [r for r in rows if r['review_status'] == 'approved']
    failed = any(r['status'] == 'fail' for r in approved) or any(r['status'] == 'error' for r in rows)
    pending = len(approved) != len(rows) or any(r['status'] == 'incomplete' for r in rows)
    gate = 'fail' if failed else ('incomplete' if pending or not approved else 'pass')
    if run.metadata.get('source_stable') is False and gate == 'pass':
        gate = 'incomplete'
    return dict(schema_version='1.0', scorer_version=SCORER_VERSION, dataset_hash=run.dataset_hash,
                observations_hash=digest(run.model_dump(mode='json')),
                adjudications_hash=digest([item.model_dump(mode='json') for item in adjudications]),
                dataset_name=dataset.name, dataset_version=dataset.version, mode=run.mode, split=run.split,
                selected_ids=run.selected_ids, repeats=run.repeats, metadata=run.metadata,
                gate=gate, scope='Selected cases only; synthetic contracts do not certify tax answers.',
                unmeasured_stages=sorted({'source','reference','relation','retrieval','context','calculator','tools','answer','safety','performance'} - {r['stage'] for r in rows if r['status'] not in {'incomplete','error'}}),
                coverage=dict(selected_cases=len(run.selected_ids), approved_cases=sum(cases[i].review.status == 'approved' for i in run.selected_ids),
                              dataset_cases=len(cases)), summaries=summaries, rows=rows)
