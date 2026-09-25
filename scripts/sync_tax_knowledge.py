"""Preview and sync versioned tax knowledge; review exact source assertions."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import close_pool
from app.services.graph.knowledge_service import audit_all, candidates, review, sync, sync_all, validate_all_sources


async def main(args):
    try:
        if args.command == 'sync':
            result = await sync(args.version_id, args.article, apply=args.apply)
        elif args.command == 'all':
            def progress(report):
                if report['completed'] % 25 == 0 or report['completed'] == report['selected']:
                    print(json.dumps(report, ensure_ascii=False), flush=True)
            result = await sync_all(apply=args.apply, limit=args.limit, progress=progress)
        elif args.command == 'audit':
            result = await audit_all()
        elif args.command == 'validate':
            def progress(report):
                if report['checked'] % 250 == 0 or report['checked'] == report['total']:
                    print(json.dumps(report, ensure_ascii=False), flush=True)
            result = await validate_all_sources(limit=args.limit, progress=progress)
        elif args.command == 'candidates':
            result = await candidates(args.version_id, args.article)
        else:
            result = await review(args.key, approve=args.approve, reviewer=args.reviewer)
        print(json.dumps(result, ensure_ascii=False, default=str))
    finally:
        await close_pool()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('sync', 'candidates'):
        command = commands.add_parser(name)
        command.add_argument('--version-id', type=int, required=True)
        command.add_argument('--article', help='Exact article number, e.g. 제1조의2')
        if name == 'sync':
            command.add_argument('--apply', action='store_true')
    command = commands.add_parser('all', help='Resume all completed historical versions')
    command.add_argument('--apply', action='store_true')
    command.add_argument('--limit', type=int, help='Maximum new snapshots in this run')
    commands.add_parser('audit', help='Read-only source/graph coverage audit')
    command = commands.add_parser('validate', help='Read-only source XML/body/hash audit')
    command.add_argument('--limit', type=int)
    command = commands.add_parser('review')
    command.add_argument('--key', required=True)
    command.add_argument('--reviewer', required=True)
    decision = command.add_mutually_exclusive_group(required=True)
    decision.add_argument('--approve', action='store_true')
    decision.add_argument('--reject', action='store_true')
    try:
        asyncio.run(main(parser.parse_args()))
    except Exception as error:
        print(f'Knowledge graph operation failed ({type(error).__name__}); check scope and source.', file=sys.stderr)
        raise SystemExit(1)
