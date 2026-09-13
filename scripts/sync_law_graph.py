"""Explicitly scoped graph sync. Default is read-only preview."""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import close_pool
from app.services.graph.index_service import build_graph, load_articles
from app.services.graph.store import save_graph
from app.services.graph.temporal_service import save_snapshot


async def main(args):
    try:
        rows = await load_articles(args.law)
        if not rows:
            raise ValueError('No current articles found for the requested scope')
        nodes, edges, unresolved = build_graph(rows)
        print(f'articles={len(nodes)} resolved_citations={len(edges)} unresolved={unresolved}')
        if args.apply:
            await save_graph(nodes, edges)
            if args.all:
                print(await save_snapshot(nodes, edges))
            print('Graph synchronized; PostgreSQL and embeddings unchanged.')
        else:
            print('Preview only. Use --apply to write the graph.')
    finally:
        await close_pool()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--law', help='Exact law name; cross-law targets outside scope remain unresolved')
    scope.add_argument('--all', action='store_true', help='Explicitly select all current public laws')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        asyncio.run(main(args))
    except Exception as error:
        print(f'Graph sync failed ({type(error).__name__}); check configuration/connectivity.', file=sys.stderr)
        raise SystemExit(1)
