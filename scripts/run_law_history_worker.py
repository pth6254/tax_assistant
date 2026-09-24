"""Opt-in resumable collection followed by a full read-only integrity audit."""
import asyncio
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.database import close_pool
from app.services.law.history_service import collect, status
from evaluation.history_audit import main as audit


async def main():
    try:
        await collect()
        state = await status()
        incomplete = any(c['pending'] or c['failed'] or c['discovery_status'] != 'complete'
                         or c['expected_count'] != c['listed'] for c in state['coverage'])
        if not state['coverage'] or incomplete:
            print('INCOMPLETE: inspect coverage/errors before retrying failed records', flush=True)
            return 2
        print('COLLECTION COMPLETE: starting full read-only audit', flush=True)
        result = await audit('/reports')
        print('AUDIT PASSED' if result['passed'] else 'AUDIT FAILED: inspect report', flush=True)
        return 0 if result['passed'] else 2
    finally:
        await close_pool()


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:
        print('WORKER ERROR: '+type(exc).__name__, flush=True)
        sys.exit(1)
