"""Evaluation commands: validate / run / suite / score / compare / langsmith."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

from evaluation.runner import collect, compare, load_dataset, write_artifacts, NoEligibleCases
from evaluation.schema import Run, Adjudication, Dataset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    validate = sub.add_parser('validate')
    validate.add_argument('--dataset', required=True)
    run = sub.add_parser('run')
    run.add_argument('--dataset', default='evaluation/datasets/contracts.json')
    run.add_argument('--mode', choices=['offline','live'], default='offline')
    run.add_argument('--split', choices=['dev','test','all'], default='dev')
    run.add_argument('--include-draft', action='store_true')
    run.add_argument('--stage')
    run.add_argument('--limit', type=int, default=0)
    run.add_argument('--repeat', type=int, default=1)
    run.add_argument('--timeout', type=float, default=180)
    run.add_argument('--allow-generation', action='store_true')
    run.add_argument('--output')
    suite = sub.add_parser('suite', parents=[], help='Run all selected datasets serially and emit a combined gate')
    suite.add_argument('--datasets', nargs='+', default=['evaluation/datasets/contracts.json', 'evaluation/datasets/retrieval.json', 'evaluation/datasets/components.json'])
    suite.add_argument('--mode', choices=['offline','live'], default='offline')
    suite.add_argument('--split', choices=['dev','test','all'], default='dev')
    suite.add_argument('--include-draft', action='store_true')
    suite.add_argument('--repeat', type=int, default=1)
    suite.add_argument('--timeout', type=float, default=180)
    suite.add_argument('--allow-generation', action='store_true')
    suite.add_argument('--output', required=True)
    score = sub.add_parser('score')
    score.add_argument('--dataset', required=True)
    score.add_argument('--observations', required=True)
    score.add_argument('--adjudications')
    score.add_argument('--output')
    comp = sub.add_parser('compare')
    comp.add_argument('--baseline', required=True)
    comp.add_argument('--candidate', required=True)
    smith = sub.add_parser('langsmith', help='Prepare a reviewed upload plan or explicitly publish it')
    smith_sub = smith.add_subparsers(dest='smith_command', required=True)
    prepare = smith_sub.add_parser('prepare')
    prepare.add_argument('--run-dir', required=True)
    prepare.add_argument('--output', required=True)
    prepare.add_argument('--include-content', action='store_true')
    prepare.add_argument('--annotation-queue', action='store_true')
    prepare.add_argument('--region', choices=['us', 'eu'], default='us')
    publish = smith_sub.add_parser('publish')
    publish.add_argument('--plan', required=True)
    publish.add_argument('--approved-sha256', required=True)
    publish.add_argument('--receipt', required=True)
    judge = sub.add_parser('judge', help='Advisory LLM review; never changes human gate')
    judge.add_argument('--run-dir', required=True)
    judge.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    if args.command == 'judge':
        from evaluation.judge import evaluate
        result = asyncio.run(evaluate(args.run_dir, args.output))
        print(json.dumps({'advisory_only': True, 'counts': result['counts'], 'output': args.output}))
        return 2
    if args.command == 'langsmith':
        from evaluation import langsmith_bridge as bridge
        from evaluation.schema import digest
        if args.smith_command == 'prepare':
            plan = bridge.prepare(args.run_dir, include_content=args.include_content,
                                  region=args.region, annotation_queue=args.annotation_queue)
            bridge.write_new(args.output, plan)
            print(json.dumps({'plan': args.output, 'sha256': digest(plan), 'content_included': plan['include_content'],
                              'records': len(plan['records']), 'uploaded': False}))
        else:
            plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
            receipt = bridge.publish(plan, approved_sha256=args.approved_sha256, receipt_path=args.receipt)
            print(json.dumps(receipt, ensure_ascii=False))
        return 0
    if args.command == 'suite':
        if args.repeat < 1 or args.timeout <= 0:
            parser.error('repeat >= 1 and timeout > 0 required')
        datasets = [load_dataset(path) for path in args.datasets]
        Dataset(name='suite-leakage-check', version='1', description='Cross-file split/ID validation',
                cases=[case for data in datasets for case in data.cases])
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=False)
        results = []
        for index, data in enumerate(datasets):
            try:
                observations = asyncio.run(collect(data, mode=args.mode, split=args.split,
                    include_draft=args.include_draft, repeats=args.repeat, allow_generation=args.allow_generation, timeout=args.timeout))
                report = write_artifacts(output/str(index), data, observations)
                results.append({'dataset':data.name,'gate':report['gate'],'report':f'{index}/report.md'})
            except NoEligibleCases:
                # A dataset with no reviewed cases is not a successful skip.
                results.append({'dataset':data.name,'gate':'incomplete','reason':'no_eligible_cases'})
            except Exception as error:
                results.append({'dataset':data.name,'gate':'fail','reason':'execution_error:'+type(error).__name__})
        gate = 'fail' if any(r['gate']=='fail' for r in results) else ('incomplete' if any(r['gate']=='incomplete' for r in results) else 'pass')
        summary = {'gate':gate,'scope':'Selected datasets/split only; not a deployment certificate','datasets':results}
        (output/'suite.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(summary,ensure_ascii=False))
        return {'pass':0,'fail':1,'incomplete':2}[gate]
    if args.command == 'compare':
        result = compare(json.loads(Path(args.baseline).read_text(encoding='utf-8')),
                         json.loads(Path(args.candidate).read_text(encoding='utf-8')))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result['regressions'] or result['candidate_gate'] != 'pass' else 0
    dataset = load_dataset(args.dataset)
    if args.command == 'validate':
        print(json.dumps(dict(name=dataset.name, hash=dataset.fingerprint(), cases=len(dataset.cases),
                             approved=sum(c.review.status=='approved' for c in dataset.cases),
                             draft=sum(c.review.status=='draft' for c in dataset.cases)), ensure_ascii=False))
        return 0
    adjudications = []
    if args.command == 'run':
        if args.limit < 0 or args.repeat < 1 or args.timeout <= 0:
            parser.error('limit >= 0, repeat >= 1, timeout > 0 required')
        observations = asyncio.run(collect(dataset, mode=args.mode, split=args.split, include_draft=args.include_draft,
                                          stage=args.stage, limit=args.limit, repeats=args.repeat,
                                          allow_generation=args.allow_generation, timeout=args.timeout))
    else:
        observations = Run.model_validate_json(Path(args.observations).read_text(encoding='utf-8'))
        if args.adjudications:
            adjudications = [Adjudication.model_validate(r) for r in json.loads(Path(args.adjudications).read_text(encoding='utf-8'))]
    output = args.output or ('evaluation/runs/' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    report = write_artifacts(output, dataset, observations, adjudications)
    print(json.dumps({'gate': report['gate'], 'report': str(Path(output)/'report.md'), 'coverage': report['coverage']}, ensure_ascii=False))
    return {'pass': 0, 'fail': 1, 'incomplete': 2}[report['gate']]


def entrypoint(argv=None):
    """Shared exit-code and safe error handling for the executable entry point."""
    try:
        return main(argv)
    except NoEligibleCases:
        print('Evaluation incomplete: no eligible reviewed cases. Drafts are diagnostics only.', file=sys.stderr)
        return 2
    except Exception as error:
        print('Evaluation failed: ' + type(error).__name__, file=sys.stderr)
        return 3
