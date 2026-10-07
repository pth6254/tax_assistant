"""Automatic cards/evaluation commands, isolated from production request handling."""
import asyncio
from datetime import date, datetime
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from evaluation.card_schema import TAXES, TYPES


def configure(parser):
    commands = parser.add_subparsers(dest='auto_command', required=True)
    build = commands.add_parser('build', help='Official snapshots -> audited synthetic evaluation cards')
    build.add_argument('--output', required=True)
    build.add_argument('--as-of', type=date.fromisoformat,
                       default=datetime.now(ZoneInfo('Asia/Seoul')).date())
    build.add_argument('--taxes', nargs='+', choices=TAXES, default=list(TAXES))
    build.add_argument('--types', nargs='+', choices=TYPES, default=list(TYPES))
    build.add_argument('--resume', action='store_true')
    validate = commands.add_parser('validate', help='Recheck frozen cards, source files and hashes without model calls')
    validate.add_argument('--cards', required=True)
    run = commands.add_parser('run', help='Read-only real chat -> automatic judges -> optional LangSmith publication')
    run.add_argument('--cards', required=True)
    run.add_argument('--output', required=True)
    run.add_argument('--limit', type=int, default=0)
    run.add_argument('--split', choices=['dev', 'test', 'all'], default='all')
    run.add_argument('--types', nargs='+', choices=TYPES, default=[])
    run.add_argument('--taxes', nargs='+', choices=TAXES, default=[])
    run.add_argument('--timeout', type=float, default=420)
    run.add_argument('--resume', action='store_true')
    run.add_argument('--from-run', help='Rejudge validated stored observations; do not rerun production chat')
    run.add_argument('--publish', action='store_true', help='Automatically publish only generated public/synthetic artifacts')
    run.add_argument('--region', choices=['us', 'eu'], default='us')
    publish = commands.add_parser('publish', help='Publish an existing automatic run without re-running models')
    publish.add_argument('--cards', required=True)
    publish.add_argument('--run-dir', required=True)
    publish.add_argument('--region', choices=['us', 'eu'], default='us')
    compare = commands.add_parser('compare', help='Compare runs bound to the same frozen automatic cards')
    compare.add_argument('--baseline', required=True)
    compare.add_argument('--candidate', required=True)
    blocks = commands.add_parser('blocks', help='Tabulate withheld claims by release check and Judge verdict (no model calls)')
    blocks.add_argument('runs', nargs='+', help='experiment.json files or run directories')
    blocks.add_argument('--output', help='Also write the JSON report to this file')
    filters = commands.add_parser('filters', help='Inject known errors into stored clean claims and see which checks catch them')
    filters.add_argument('runs', nargs='+', help='experiment.json files or run directories')
    filters.add_argument('--cards', help='Card directory for the original questions (else plan request quotes)')
    filters.add_argument('--judge', action='store_true', help='Also run the claim Judge on seeds and mutants (model calls)')
    filters.add_argument('--output', help='Also write the JSON report to this file')
    pipeline = commands.add_parser('pipeline', help='Build, evaluate and optionally publish in one resumable command')
    pipeline.add_argument('--output', required=True)
    pipeline.add_argument('--as-of', type=date.fromisoformat,
                          default=datetime.now(ZoneInfo('Asia/Seoul')).date())
    pipeline.add_argument('--taxes', nargs='+', choices=TAXES, default=list(TAXES))
    pipeline.add_argument('--types', nargs='+', choices=TYPES, default=list(TYPES))
    pipeline.add_argument('--eval-types', nargs='+', choices=TYPES, default=[])
    pipeline.add_argument('--limit', type=int, default=0)
    pipeline.add_argument('--timeout', type=float, default=420)
    pipeline.add_argument('--resume', action='store_true')
    pipeline.add_argument('--publish', action='store_true')
    pipeline.add_argument('--region', choices=['us', 'eu'], default='us')


async def execute(args):
    from langsmith import tracing_context
    from evaluation.adapters import close_live_clients
    from evaluation.auto_cards import build, load_cards
    from evaluation.auto_pipeline import run, validate_experiment
    from evaluation.auto_langsmith import publish_automatic
    from app.services.search.bm25_search_service import close_bm25_index
    try:
        # Public artifacts are sent exactly once by explicit SDK publishing, not
        # duplicated through ambient tracing of every generation/Judge call.
        with tracing_context(enabled=False):
            if args.auto_command == 'pipeline':
                if args.limit < 0 or not math.isfinite(args.timeout) or args.timeout <= 0:
                    raise ValueError('invalid_automatic_run_limits')
                output = Path(args.output)
                if not args.resume:
                    output.mkdir(parents=True, exist_ok=False)
                elif not output.is_dir():
                    raise FileNotFoundError('resume_directory_missing')
                cards_dir, run_dir = output / 'cards', output / 'run'
                result = await build(cards_dir, as_of=args.as_of, taxes=tuple(args.taxes),
                    case_types=tuple(args.types), resume=args.resume and cards_dir.exists())
                print(json.dumps({'card_build': result}, ensure_ascii=False))
                if not result['auto_validated']:
                    return 2
                result = await run(cards_dir, run_dir, limit=args.limit, case_types=tuple(args.eval_types),
                    timeout=args.timeout, resume=args.resume and run_dir.exists())
                print(json.dumps(result['summary'], ensure_ascii=False))
                if args.publish:
                    receipt = await asyncio.to_thread(publish_automatic, cards_dir, run_dir, region=args.region)
                    print(json.dumps({'langsmith': receipt['status'], 'dataset_id': receipt['dataset'],
                                      'experiments': receipt['projects']}, ensure_ascii=False))
                statuses = result['summary']['case_statuses']
                return 1 if statuses.get('fail') else 2 if statuses.get('incomplete') else 0
            if args.auto_command == 'build':
                result = await build(args.output, as_of=args.as_of, taxes=tuple(args.taxes),
                                     case_types=tuple(args.types), resume=args.resume)
                print(json.dumps(result, ensure_ascii=False))
                return 0 if result['auto_validated'] else 2
            if args.auto_command == 'validate':
                data = load_cards(args.cards)
                print(json.dumps({'cards': len(data.cards), 'hash': data.fingerprint(), 'human_approved': 0}))
                return 0
            if args.auto_command == 'run':
                if args.limit < 0 or not math.isfinite(args.timeout) or args.timeout <= 0:
                    raise ValueError('invalid_automatic_run_limits')
                result = await run(args.cards, args.output, limit=args.limit, split=args.split,
                                   case_types=tuple(args.types), taxes=tuple(args.taxes),
                                   timeout=args.timeout, resume=args.resume, from_run=args.from_run)
                print(json.dumps(result['summary'], ensure_ascii=False))
                if args.publish:
                    receipt = await asyncio.to_thread(publish_automatic, args.cards, args.output, region=args.region)
                    print(json.dumps({'langsmith': receipt['status'], 'dataset_id': receipt['dataset'],
                                      'experiments': receipt['projects']}, ensure_ascii=False))
                statuses = result['summary']['case_statuses']
                return 1 if statuses.get('fail') else 2 if statuses.get('incomplete') else 0
            if args.auto_command == 'publish':
                receipt = await asyncio.to_thread(publish_automatic, args.cards, args.run_dir, region=args.region)
                print(json.dumps({'langsmith': receipt['status'], 'dataset_id': receipt['dataset'],
                                  'experiments': receipt['projects']}, ensure_ascii=False))
                return 0
            baseline, candidate = [json.loads(Path(p).read_text(encoding='utf-8'))
                                   for p in (args.baseline, args.candidate)]
            for experiment in (baseline, candidate):
                validate_experiment(experiment, build_failures=experiment.get('build_failures', []))
            if (baseline['options']['dataset_hash'] != candidate['options']['dataset_hash']
                    or baseline['options']['selected_ids'] != candidate['options']['selected_ids']):
                raise ValueError('automatic_comparison_scope_changed')
            before = {(r['case_id'], i['criterion_id']): i['verdict']
                      for r in baseline['records'] for i in r['criteria']}
            after = {(r['case_id'], i['criterion_id']): i['verdict']
                     for r in candidate['records'] for i in r['criteria']}
            if before.keys() != after.keys():
                raise ValueError('automatic_comparison_criteria_changed')
            regressions = [list(k) for k in before if before[k] == 'pass' and after[k] != 'pass']
            improvements = [list(k) for k in before if before[k] != 'pass' and after[k] == 'pass']
            print(json.dumps({'regressions': regressions, 'improvements': improvements,
                              'baseline': baseline['summary'], 'candidate': candidate['summary']}, ensure_ascii=False))
            return 1 if regressions else 0
    finally:
        await close_bm25_index()
        await close_live_clients()


def main(args):
    if args.auto_command == 'filters':
        from evaluation.filter_value import filter_report
        report = asyncio.run(filter_report(args.runs, cards=args.cards, judge=args.judge))
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(text + chr(10), encoding='utf-8')
        print(text)
        return 0
    if args.auto_command == 'blocks':
        # Pure file analysis: no BM25 index, model client or tracing to open.
        from evaluation.block_report import block_report
        report = block_report(args.runs)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(text + '\n', encoding='utf-8')
        print(text)
        return 0
    return asyncio.run(execute(args))
