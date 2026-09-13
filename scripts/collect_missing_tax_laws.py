"""Preview 14 required subordinate laws; --apply collects only missing names.

No embeddings or graph writes. Partial failures exit nonzero; inspect row counts
before retrying because presence alone does not certify complete collection.
"""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import close_pool
from app.services.law.coverage_service import missing_subordinate_laws
from app.services.law.ingestion_service import ingest_law


async def main(apply=False):
    try:
        targets = await missing_subordinate_laws()
        print(json.dumps({'missing': [t['law_name'] for t in targets]}, ensure_ascii=False), flush=True)
        if not apply:
            print('Preview only; use --apply to collect missing originals without embeddings.')
            return 0
        failures = 0
        for target in targets:
            try:
                result = await ingest_law(**target, embed=False)
                print(json.dumps(result, ensure_ascii=False), flush=True)
                if not result['total_articles'] or result['failed_count']:
                    failures += 1
            except Exception as error:
                failures += 1
                print(json.dumps({'law_name': target['law_name'], 'error_type': type(error).__name__}, ensure_ascii=False), flush=True)
        remaining = await missing_subordinate_laws()
        print(json.dumps({'failures': failures, 'remaining_missing': [t['law_name'] for t in remaining]}, ensure_ascii=False), flush=True)
        return int(bool(failures or remaining))
    finally:
        await close_pool()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    # HTTP exception logs can include API credentials in request URLs.
    logging.disable(logging.CRITICAL)
    try:
        raise SystemExit(asyncio.run(main(args.apply)))
    except Exception as error:
        print('Collection failed: ' + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
