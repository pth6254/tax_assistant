"""Historical law archive CLI. See docs/LAW_HISTORY.md."""
import argparse
import asyncio
import json
import logging
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.database import close_pool
from app.services.law import history_service as service


async def main(args):
    try:
        if args.command=='discover':
            await service.discover(args.refresh)
        elif args.command=='collect':
            await service.collect(args.limit,args.retry_failed,args.refresh,args.version_id)
        elif args.command=='status':
            print(json.dumps(await service.status(),ensure_ascii=False,default=str,indent=2))
        elif args.command=='versions':
            print(json.dumps(await service.versions(args.law_id),ensure_ascii=False,default=str,indent=2))
        elif args.command=='show':
            print(json.dumps(await service.show(args.version_id),ensure_ascii=False,default=str,indent=2))
        else:
            print(await service.compare(args.left,args.right))
        if args.command in ('discover','collect'):
            state = await service.status()
            if state['runs'][0]['status'] != 'complete':
                return 2
        return 0
    finally:
        await close_pool()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('discover').add_argument('--refresh',action='store_true')
    collect=sub.add_parser('collect')
    collect.add_argument('--limit',type=int)
    collect.add_argument('--retry-failed',action='store_true')
    collect.add_argument('--refresh',action='store_true',help='Recheck complete bodies, preserving previous snapshots')
    collect.add_argument('--version-id',type=int,help='Only this archive version ID')
    sub.add_parser('status')
    sub.add_parser('versions').add_argument('--law-id',required=True)
    sub.add_parser('show').add_argument('--version-id',type=int,required=True)
    diff=sub.add_parser('diff')
    diff.add_argument('--left',type=int,required=True)
    diff.add_argument('--right',type=int,required=True)
    args=parser.parse_args()
    if getattr(args,'limit',None) is not None and args.limit<1:
        parser.error('--limit must be positive')
    logging.disable(logging.CRITICAL)
    try:
        sys.exit(asyncio.run(main(args)))
    except Exception as exc:
        print('ERROR: '+type(exc).__name__,file=sys.stderr)
        sys.exit(1)
