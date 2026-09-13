"""Verify one law/decree/rule family using official purpose clauses."""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.graph.family_service import prepare_family, save_family, stored_families


async def main(args):
    if args.all:
        names, unmatched = await stored_families()
    else:
        names, unmatched = [args.law], []
    print(json.dumps({'families': names, 'unmatched_stored_laws': unmatched}, ensure_ascii=False), flush=True)
    failed = []
    for name in names:
        try:
            members, links = await prepare_family(name)
            if args.apply:
                await save_family(members, links)
            print(json.dumps({'family': name, 'applied': args.apply,
                              'members': [{'name': m['law_name'], 'id': m['law_id']} for m in members],
                              'links': links}, ensure_ascii=False), flush=True)
        except Exception as error:
            failed.append(name)
            print(json.dumps({'family': name, 'error_type': type(error).__name__}, ensure_ascii=False), flush=True)
    print(json.dumps({'failed': failed, 'unmatched': unmatched}, ensure_ascii=False), flush=True)
    if failed:
        raise RuntimeError('Some families require review')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    scope = p.add_mutually_exclusive_group(required=True)
    scope.add_argument('--law')
    scope.add_argument('--all', action='store_true')
    p.add_argument('--apply', action='store_true')
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(main(p.parse_args()))
    except Exception as error:
        print('Family sync failed: ' + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
