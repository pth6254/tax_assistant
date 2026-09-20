"""Serial, read-only experiment collection and reproducible report artifacts."""
import json
from pathlib import Path
import platform
import subprocess
from datetime import datetime, timezone
import uuid

from evaluation.adapters import observe, close_live_clients
from evaluation.schema import Dataset, Run, Observation, Evidence, digest
from evaluation.scoring import score_run, score_case

ROOT = Path(__file__).resolve().parents[1]


class NoEligibleCases(ValueError):
    """No labels in the requested split have the required review status."""


def load_dataset(path):
    dataset = Dataset.model_validate_json(Path(path).read_text(encoding='utf-8'))
    for case in dataset.cases:
        for negative in case.counterexamples:
            result = score_case(case, Observation(case_id=case.id, payload=negative.payload))
            if result['status'] != 'fail':
                raise ValueError('Counterexample is not rejected by the grading rules: ' + case.id)
    return dataset


def code_metadata():
    paths = sorted([*ROOT.glob('app/**/*.py'), *ROOT.glob('evaluation/**/*.py'), ROOT/'config.py', ROOT/'requirements.txt'])
    fingerprint = digest({str(p.relative_to(ROOT)): digest(p.read_text(encoding='utf-8')) for p in paths})
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.SubprocessError):
        commit = 'unavailable'
    return {'code_hash': fingerprint, 'git_commit': commit, 'python': platform.python_version(),
            'started_at': datetime.now(timezone.utc).isoformat()}


async def source_snapshot(stages):
    """Hash only each selected stage's dependencies, never private user data."""
    if not stages & {'source', 'retrieval', 'calculator'}:
        return {}  # Fixed context/tool selection is bound by dataset/code/model metadata.
    from app.database import get_pool
    pool = await get_pool()
    result = {}
    if stages & {'source', 'retrieval'}:
        law = await pool.fetchrow('''
        SELECT count(*) AS rows,
        md5(string_agg(md5(concat_ws('|',id,law_name,article_no,article_title,article_text,
            law_type,tax_type,effective_date,amendment_date,is_current,embedding::text,embedding_v2::text)), '' ORDER BY id)) AS fingerprint
        FROM law_articles
        ''')
        result['laws'] = dict(law)
    # Fixed table names, not dataset-provided SQL.
    tables = (['law_article_clauses'] if 'retrieval' in stages else [])
    if 'calculator' in stages:
        tables += ['tax_brackets', 'tax_deductions']
    for table in tables:
        result[table] = await pool.fetchval(
            f"SELECT md5(string_agg(md5(row_to_json(t)::text),'' ORDER BY md5(row_to_json(t)::text))) FROM {table} t")
    if 'retrieval' not in stages:
        return result
    try:
        import config
        from app.services.graph.store import connect
        async with connect() as driver:
            records, _, _ = await driver.execute_query('''
                MATCH (s:TaxArticle)-[r:CITES]->(t:TaxArticle)
                RETURN s.key AS source, t.key AS target, properties(r) AS properties
                ORDER BY source, target, r.reference
            ''', database_=config.NEO4J_DATABASE, routing_='r')
            result['graph'] = {'edges': len(records), 'fingerprint': digest([dict(r) for r in records])}
    except Exception as error:
        result['graph'] = {'unavailable': type(error).__name__}
    return result


async def collect(dataset, *, mode='offline', split='dev', include_draft=False, stage=None,
                  limit=0, repeats=1, allow_generation=False, timeout=180):
    cases = [c for c in dataset.cases if c.review.status != 'retired'
             and (split == 'all' or c.split == split)
             and (include_draft or c.review.status == 'approved') and (stage is None or c.stage == stage)]
    cases = cases[:limit or None]
    if not cases:
        raise NoEligibleCases('No eligible cases; review labels or explicitly include drafts for diagnostics')
    metadata = code_metadata()
    metadata.update(allow_generation=allow_generation, timeout=timeout,
                    retrieval_scope='single-query, explicit input filter or ALL; no gold-derived filter',
                    source_stable=None)
    records = []
    try:
        if mode == 'live':
            import config
            metadata['runtime'] = {key: getattr(config, key) for key in (
                'LLM_PROVIDER', 'CHAT_MODEL', 'EMBEDDING_PROVIDER', 'EMBEDDING_MODEL',
                'EMBEDDING_VERSION', 'TOP_K', 'SIMILARITY_THRESHOLD', 'GRAPH_TIMEOUT_SEC', 'OLLAMA_NUM_CTX')}
            metadata['source_before'] = await source_snapshot({c.stage for c in cases})
        user_id = str(uuid.uuid4())
        for repeat in range(1, repeats+1):
            for case in cases:
                records.extend(await observe(case, mode, user_id, repeat, allow_generation, timeout))
                print(f'[{repeat}/{repeats}] {case.id}', flush=True)
        if mode == 'live':
            metadata['source_after'] = await source_snapshot({c.stage for c in cases})
            metadata['source_stable'] = metadata['source_before'] == metadata['source_after']
    finally:
        if mode == 'live':
            await close_live_clients()
    metadata['finished_at'] = datetime.now(timezone.utc).isoformat()
    return Run(dataset_hash=dataset.fingerprint(), split=split, mode=mode, selected_ids=[c.id for c in cases],
               repeats=repeats, metadata=metadata, observations=records)


def write_artifacts(directory, dataset, run, adjudications=()):
    report = score_run(dataset, run, adjudications)
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=False)  # Never overwrite a prior run.
    for name, value in [('dataset.json', dataset.model_dump(mode='json')),
                        ('observations.json', run.model_dump(mode='json')), ('report.json', report),
                        ('adjudications.json', [item.model_dump(mode='json') for item in adjudications])]:
        (path/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    queue = []
    evidence_queue, queued = [], set()
    for obs in run.observations:
        case = next(c for c in dataset.cases if c.id == obs.case_id)
        if case.stage == 'retrieval':
            judged = {j.evidence.key(): j for j in case.judgments}
            for doc in obs.payload.get('results', []):
                try:
                    evidence = Evidence.model_validate(doc)
                    evidence.key()
                except ValueError:
                    continue  # Already an explicit invalid_observation error in report.
                key = evidence.key()
                current = judged.get(key, judged.get((*key[:2], '')))
                if (current is None or case.review.status != 'approved') and (case.id, key) not in queued:
                    queued.add((case.id, key))
                    evidence_queue.append(dict(case_id=case.id, evidence=evidence.model_dump(),
                                               proposed_label=current.label if current else None,
                                               label=None, reason='', confusion='none', reviewer=''))
        if case.rubric:
            queue.append(dict(case_id=obs.case_id, variant=obs.variant, repeat=obs.repeat,
                              payload_hash=digest(obs.payload), reviewer='', reviewed_on=None,
                              criteria={r.id: {'passed': None, 'rationale': '', 'evidence': ''} for r in case.rubric}))
    (path/'review_queue.json').write_text(json.dumps(queue, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (path/'evidence_review_queue.json').write_text(json.dumps(evidence_queue, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    lines = ['# Evaluation report', '', f"Gate: **{report['gate']}** (selected scope only)", '',
             'Synthetic contracts are not tax-answer correctness. Draft labels do not pass a release gate.', '',
             '| Stage | Variant | Basis | Review | Pass / Fail / Incomplete / Error |',
             '|---|---|---|---|---|']
    for summary in report['summaries']:
        counts = ' / '.join(str(summary['statuses'].get(s, 0)) for s in ('pass','fail','incomplete','error'))
        lines.append(f"| {summary['stage']} | {summary['variant']} | {summary['basis']} | {summary['review_status']} | {counts} |")
    lines += ['', 'Unmeasured stages: ' + ', '.join(report['unmeasured_stages']), '', '## Cases needing attention', '']
    for row in report['rows']:
        if row['status'] != 'pass' or row['review_status'] != 'approved':
            lines.append(f"- {row['case_id']} / {row['variant']} / #{row['repeat']}: {row['status']} ({', '.join(row['reasons'])}); labels={row['review_status']}")
    (path/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return report


def compare(baseline, candidate):
    for field in ('dataset_hash','scorer_version','split','mode','selected_ids','repeats'):
        if baseline[field] != candidate[field]:
            raise ValueError('Incomparable runs: ' + field)
    key = lambda r: (r['case_id'], r['variant'], r['repeat'])
    old = {key(r): r for r in baseline['rows']}
    new = {key(r): r for r in candidate['rows']}
    if old.keys() != new.keys():
        raise ValueError('Run coverage mismatch')
    regressions, changes = [], []
    for identity in old:
        before, after = old[identity], new[identity]
        worsened = before['status'] == 'pass' and after['status'] != 'pass'
        deltas = {}
        for metric in ('recall_at_k', 'recall_all', 'judged_precision', 'hard_negative_count', 'unjudged_count'):
            a, b = before['metrics'].get(metric), after['metrics'].get(metric)
            if a is not None and b is not None:
                deltas[metric] = b-a
                worsened |= b > a if metric.endswith('count') else b < a
        changes.append(dict(case_id=identity[0], variant=identity[1], repeat=identity[2], deltas=deltas))
        if worsened:
            regressions.append(identity)
    return dict(regressions=regressions, changes=changes,
                candidate_gate=candidate['gate'], baseline_gate=baseline['gate'],
                source_changed=baseline['metadata'].get('source_before') != candidate['metadata'].get('source_before'),
                warning='Dataset consistency is enforced; inspect runtime/source differences before causal claims.')
