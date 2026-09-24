"""Derived history index CLI; all phases are resumable. No live-law overwrite."""
import argparse
import asyncio
import json
import logging
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.database import get_pool,close_pool
from app.services.embedding_service import close_http_client
from app.services.law import history_index as index


async def main(args):
    try:
        pool = await get_pool()
        if args.phase == 'status':
            print(json.dumps(await index.status(),default=str),flush=True)
            return 0
        async with pool.acquire() as conn:
            if not await conn.fetchval('SELECT pg_try_advisory_lock($1)',index.INDEX_LOCK):
                raise RuntimeError('HistoryIndexerAlreadyRunning')
            try:
                if args.phase in ('prepare','all'):
                    await index.prepare()
                if args.phase in ('graph','all'):
                    await index.graph()
                if args.phase in ('embed','all'):
                    await index.embed(args.limit,args.retry_failed,args.version_id)
                state = await index.status()
                print(json.dumps(state),flush=True)
                if args.phase == 'all' and (state['failed'] or state['embedded']!=state['chunks']
                    or state['unprepared'] or state['graph_snapshots']!=state['snapshots']):
                    return 2
                return 0
            finally:
                await conn.execute('SELECT pg_advisory_unlock($1)',index.INDEX_LOCK)
    finally:
        await close_http_client()
        await close_pool()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=['prepare','graph','embed','all','status'])
    p.add_argument('--limit',type=int)
    p.add_argument('--retry-failed',action='store_true')
    p.add_argument('--version-id',type=int)
    args=p.parse_args()
    if args.limit is not None and args.limit<1:
        p.error('limit must be positive')
    if args.version_id is not None and args.phase!='embed':
        p.error('--version-id requires embed')
    logging.disable(logging.CRITICAL)
    try:
        sys.exit(asyncio.run(main(args)))
    except Exception as exc:
        print('ERROR '+type(exc).__name__,flush=True)
        sys.exit(1)
