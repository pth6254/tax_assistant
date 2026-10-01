"""Explicit same-version original/index repair with per-row durable rollback.

preview is read-only. apply consumes the fixed plan, defaults to a 20-row pilot,
and can resume. Graph sync is separate; live graph admission checks source keys.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'

from app.database import close_pool, get_pool
from app.services.embedding_service import close_http_client, embed_texts_for_storage
from app.services.law.index_repair import (
    SOURCE_FIELDS, apply_repair, prepare_repair, repair_candidates, restore_backup,
)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def summary(items):
    from collections import Counter
    return dict(Counter(item['kind'] for item in items))


async def main(args):
    pool = await get_pool()
    path = Path(args.plan)
    state_path = path.with_suffix('.state.json')
    try:
        if args.command == 'preview':
            async with pool.acquire() as conn:
                candidates, rejected = await repair_candidates(
                    conn, clauses=args.include_clauses, core_only=args.scope == 'core')
            items = []
            for candidate in candidates:
                items.append(candidate | {
                    'before': {k: candidate['before'][k] for k in SOURCE_FIELDS},
                    'after': {k: candidate['after'][k] for k in SOURCE_FIELDS}})
            plan = {'version': 1, 'scope': args.scope, 'run_id': str(uuid4()),
                    'items': items, 'rejected': rejected}
            if args.graph_backup:
                from app.services.graph.store import graph_backup
                write_json(path.parent / 'graph-before.json', await graph_backup())
            write_json(path, plan)
            print(json.dumps({'preview': True, 'candidates': len(items), 'kinds': summary(items),
                              'rejected': len(rejected)}, ensure_ascii=False), flush=True)
            return
        raw = path.read_text(encoding='utf-8')
        plan = json.loads(raw)
        if plan.get('version') != 1:
            raise ValueError('unsupported_repair_plan_version')
        plan_hash = hashlib.sha256(raw.encode()).hexdigest()
        state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {
            'run_id': plan['run_id'], 'plan_hash': plan_hash, 'items': {}}
        if state['plan_hash'] != plan_hash or state['run_id'] != plan['run_id']:
            raise ValueError('repair_plan_changed')
        if args.command == 'rollback':
            for item in reversed(plan['items']):
                key = str(item['before']['id'])
                if state['items'].get(key, {}).get('status') != 'applied':
                    continue
                backup = json.loads((path.parent / f'backup-{key}.json').read_text(encoding='utf-8'))
                async with pool.acquire() as conn:
                    await restore_backup(conn, backup, item['after']['content_hash'], plan['run_id'])
                state['items'][key]['status'] = 'rolled_back'
                write_json(state_path, state)
                print(json.dumps({'article_id': int(key), 'status': 'rolled_back'}), flush=True)
            return
        selected = plan['items'] if args.limit == 0 else plan['items'][:args.limit]
        for item in selected:
            key = str(item['before']['id'])
            if state['items'].get(key, {}).get('status') == 'applied':
                continue
            # Recheck the immutable archive and the fixed source identity before
            # spending embedding time; never choose a newer replacement version.
            async with pool.acquire() as conn:
                from app.services.law.source_recovery import recover_article
                current = await conn.fetchrow('SELECT * FROM law_articles WHERE id=$1', item['before']['id'])
                if current and current['index_metadata'].get('repair_run_id') == plan['run_id']:
                    if (current['content_hash'] != item['after']['content_hash']
                            or not (path.parent / f'backup-{key}.json').exists()):
                        raise ValueError('repair_checkpoint_conflict')
                    state['items'][key] = {'status': 'applied', 'recovered_checkpoint': True}
                    write_json(state_path, state)
                    continue
                if not current or any(current[k] != item['before'][k] for k in SOURCE_FIELDS):
                    raise ValueError('repair_plan_stale')
                restored = await recover_article(current, conn)
                if (restored['content_hash'] != item['after']['content_hash']
                        or restored['article_text'] != item['after']['article_text']):
                    raise ValueError('repair_archive_changed')
            prepared = await prepare_repair(item, embed_texts_for_storage, plan['run_id'])
            backup_path = path.parent / f'backup-{key}.json'
            def persist(backup):
                if backup_path.exists():
                    old = json.loads(backup_path.read_text(encoding='utf-8'))
                    if old['article']['content_hash'] != item['before']['content_hash']:
                        raise ValueError('repair_backup_conflict')
                write_json(backup_path, backup)
            async with pool.acquire() as conn:
                await apply_repair(conn, prepared, persist)
            state['items'][key] = {'status': 'applied', 'after_hash': item['after']['content_hash'],
                                   'clauses': len(prepared.clauses)}
            write_json(state_path, state)
            print(json.dumps({'article_id': int(key), 'status': 'applied', 'kind': item['kind'],
                              'clauses': len(prepared.clauses)}, ensure_ascii=False), flush=True)
        print(json.dumps({'completed': len(state['items']), 'total_plan': len(plan['items'])}), flush=True)
    finally:
        await close_http_client()
        await close_pool()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('preview', 'apply', 'rollback'))
    parser.add_argument('--plan', required=True)
    parser.add_argument('--scope', choices=('core', 'all'), default='core')
    parser.add_argument('--include-clauses', action='store_true')
    parser.add_argument('--graph-backup', action='store_true', help='Back up only current TaxArticle/CITES data')
    parser.add_argument('--limit', type=int, default=20, help='0 explicitly applies the complete fixed plan')
    args = parser.parse_args()
    if args.limit < 0:
        parser.error('--limit must be non-negative')
    asyncio.run(main(args))
