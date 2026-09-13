"""Read an exact-date observed graph snapshot; does not infer legal applicability."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.graph.temporal_service import query_snapshot
from app.services.law.reference_parser import parse_law_reference

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--as-of', required=True, help='YYYY-MM-DD; exact recorded date only')
    p.add_argument('--law', required=True)
    p.add_argument('--article', required=True)
    args = p.parse_args()
    try:
        ref = parse_law_reference(args.article)
        result = asyncio.run(query_snapshot(args.as_of, args.law, ref.article_no))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as error:
        print('Temporal query failed: ' + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
